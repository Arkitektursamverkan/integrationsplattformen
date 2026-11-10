"""CSV upload endpoint — upload a CSV file as a data source."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

import anyio
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.csv_connector import parse_csv
from app.database import get_db
from app.dependencies import require_admin_auth, require_auth
from app.models.connection import ConnectionORM
from app.models.data_record import DataRecordORM
from app.models.execution_log import ExecutionLogORM
from app.models.flow import FlowORM
from app.services.transform_engine import apply_operations
from app.models.flow_step import FlowStepORM

log = structlog.get_logger(__name__)

router = APIRouter()

# Larger files are refused (413) – the whole file is parsed in memory.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_CHUNK = 1024 * 1024


async def _read_limited(file: UploadFile) -> bytes:
    """The uploaded file, read in chunks and refused above MAX_UPLOAD_BYTES."""
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _checksum(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


@router.post("/preview", dependencies=[Depends(require_auth)])
async def preview_csv(
    file: UploadFile = File(...),
    delimiter: str = Form("auto"),
):
    """Preview a CSV file: parse and return the first rows and detected columns."""
    content = await _read_limited(file)
    try:
        records = parse_csv(content, delimiter=delimiter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    # Collect all columns
    columns = []
    if records:
        seen = set()
        for rec in records:
            for key in rec:
                if key not in seen:
                    seen.add(key)
                    sample = str(rec[key])[:100] if rec[key] else ""
                    columns.append({"name": key, "sample": sample})

    return {
        "total_rows": len(records),
        "columns": columns,
        "preview": records[:10],
    }


@router.post("/upload", dependencies=[Depends(require_admin_auth)])
async def upload_csv(
    file: UploadFile = File(...),
    name: str = Form(..., description="Name for the data source"),
    description: str = Form("", description="Optional description"),
    delimiter: str = Form("auto"),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV file: creates a connection + flow + stores all records.

    This is a one-step operation: the CSV becomes immediately available
    in the Data Explorer and Data API.
    """
    content = await _read_limited(file)
    try:
        records = parse_csv(content, delimiter=delimiter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    if not records:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no valid rows")

    now = datetime.now(timezone.utc)

    # Create a CSV connection
    conn = ConnectionORM(
        id=uuid.uuid4(),
        name=f"CSV: {name}",
        connector_type="csv",
        description=description or f"Uploaded from {file.filename}",
        config={"delimiter": delimiter, "filename": file.filename},
        auth_type="none",
        status="active",
    )
    db.add(conn)
    await db.flush()

    # Create a flow (no transform steps — passthrough)
    flow = FlowORM(
        id=uuid.uuid4(),
        name=name,
        description=description or f"CSV data from {file.filename}",
        connection_id=conn.id,
        enabled=True,
    )
    db.add(flow)
    await db.flush()

    # Create execution log
    execution = ExecutionLogORM(
        id=uuid.uuid4(),
        flow_id=flow.id,
        trigger_type="csv_upload",
        status="running",
        started_at=now,
    )
    db.add(execution)

    # Store original records (preserved for re-processing) + working copies
    created = 0
    for record in records:
        external_id = str(record.get("external_id", str(uuid.uuid4())))
        cs = _checksum(record)

        # Original copy — never modified by pipeline stages
        db.add(DataRecordORM(
            id=uuid.uuid4(),
            flow_id=flow.id,
            source_type="csv_original",
            external_id=external_id,
            data=record,
            checksum=cs,
            version=1,
        ))

        # Working copy — this is what the Data Explorer and Data API show
        db.add(DataRecordORM(
            id=uuid.uuid4(),
            flow_id=flow.id,
            source_type="csv",
            external_id=external_id,
            data=record,
            checksum=cs,
            version=1,
        ))
        created += 1

    execution.status = "success"
    execution.finished_at = datetime.now(timezone.utc)
    execution.records_processed = len(records)
    execution.records_created = created
    execution.records_updated = 0

    await db.commit()

    log.info("csv.uploaded", name=name, filename=file.filename, records=created, flow_id=str(flow.id))

    return {
        "connection_id": str(conn.id),
        "flow_id": str(flow.id),
        "name": name,
        "filename": file.filename,
        "total_records": created,
        "columns": list(records[0].keys()) if records else [],
    }


@router.post("/replace/{flow_id}", dependencies=[Depends(require_admin_auth)])
async def replace_csv_data(
    flow_id: uuid.UUID,
    file: UploadFile = File(...),
    delimiter: str = Form("auto"),
    db: AsyncSession = Depends(get_db),
):
    """Replace the data in an existing CSV flow with a new file upload."""
    # Verify flow exists
    result = await db.execute(select(FlowORM).where(FlowORM.id == flow_id))
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    # Only a CSV source's records may be replaced by a file.
    connector_type = (await db.execute(
        select(ConnectionORM.connector_type).where(ConnectionORM.id == flow.connection_id)
    )).scalar_one_or_none()
    if connector_type != "csv":
        raise HTTPException(status_code=400, detail="Flow is not a CSV data source")

    content = await _read_limited(file)
    try:
        records = parse_csv(content, delimiter=delimiter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    if not records:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    now = datetime.now(timezone.utc)

    # Delete all existing records (both original and working)
    existing = await db.execute(select(DataRecordORM).where(DataRecordORM.flow_id == flow_id))
    for rec in existing.scalars().all():
        await db.delete(rec)

    # Create execution log
    execution = ExecutionLogORM(
        id=uuid.uuid4(),
        flow_id=flow_id,
        trigger_type="csv_upload",
        status="running",
        started_at=now,
    )
    db.add(execution)

    # Store originals + working copies
    # Apply transform steps to working copies
    steps_result = await db.execute(
        select(FlowStepORM).where(FlowStepORM.flow_id == flow_id).order_by(FlowStepORM.step_order)
    )
    steps = steps_result.scalars().all()
    import copy
    transformed = copy.deepcopy(records)
    # I en tråd – se flow_service.execute_flow.
    transformed = await anyio.to_thread.run_sync(
        apply_operations, transformed, [(step.step_type, step.config) for step in steps]
    )

    created = 0
    for record in records:
        external_id = str(record.get("external_id", str(uuid.uuid4())))
        cs = _checksum(record)
        db.add(DataRecordORM(
            id=uuid.uuid4(), flow_id=flow_id, source_type="csv_original",
            external_id=external_id, data=record, checksum=cs, version=1,
        ))

    for record in transformed:
        external_id = str(record.get("external_id", str(uuid.uuid4())))
        cs = _checksum(record)
        db.add(DataRecordORM(
            id=uuid.uuid4(), flow_id=flow_id, source_type="csv",
            external_id=external_id, data=record, checksum=cs, version=1,
        ))
        created += 1

    execution.status = "success"
    execution.finished_at = datetime.now(timezone.utc)
    execution.records_processed = len(records)
    execution.records_created = created

    await db.commit()

    return {
        "flow_id": str(flow_id),
        "filename": file.filename,
        "total_records": created,
    }
