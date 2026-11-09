"""Data API — serves stored records to consuming applications."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_consumer_key
from app.models.api_key import ApiKeyORM
from app.models.data_record import DataRecordORM
from app.models.execution_log import ExecutionLogORM
from app.models.flow import FlowORM
from app.models.connection import ConnectionORM
from app.ratelimit import limiter
from app.schemas.data import DataRecordList, DataRecordRead, DataSourceSummary

router = APIRouter()

# Exclude internal csv_original records from all data queries
_VISIBLE = DataRecordORM.source_type != "csv_original"


@router.get("/sources", response_model=list[DataSourceSummary])
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKeyORM = Depends(require_consumer_key),
):
    """List available data sources (flows with records)."""
    result = await db.execute(
        select(FlowORM, ConnectionORM)
        .join(ConnectionORM, FlowORM.connection_id == ConnectionORM.id)
        .where(FlowORM.enabled.is_(True))
    )
    rows = result.all()

    sources = []
    for flow, connection in rows:
        count_result = await db.execute(
            select(func.count(DataRecordORM.id)).where(DataRecordORM.flow_id == flow.id, _VISIBLE)
        )
        record_count = count_result.scalar() or 0

        last_exec_result = await db.execute(
            select(ExecutionLogORM)
            .where(ExecutionLogORM.flow_id == flow.id, ExecutionLogORM.status == "success")
            .order_by(ExecutionLogORM.finished_at.desc())
            .limit(1)
        )
        last_exec = last_exec_result.scalar_one_or_none()

        sources.append(DataSourceSummary(
            flow_id=flow.id,
            flow_name=flow.name,
            connector_type=connection.connector_type,
            record_count=record_count,
            last_sync=last_exec.finished_at if last_exec else None,
            status="active" if record_count > 0 else "empty",
        ))
    return sources


@router.get("/{flow_id}/records", response_model=DataRecordList)
@limiter.limit("120/minute")
async def list_records(
    request: Request,
    flow_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKeyORM = Depends(require_consumer_key),
):
    count_result = await db.execute(
        select(func.count(DataRecordORM.id)).where(DataRecordORM.flow_id == flow_id, _VISIBLE)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(DataRecordORM)
        .where(DataRecordORM.flow_id == flow_id, _VISIBLE)
        .order_by(DataRecordORM.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return DataRecordList(
        records=result.scalars().all(),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{flow_id}/records/by-external/{external_id}", response_model=DataRecordRead)
async def get_record_by_external_id(
    flow_id: uuid.UUID,
    external_id: str,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKeyORM = Depends(require_consumer_key),
):
    result = await db.execute(
        select(DataRecordORM).where(
            DataRecordORM.flow_id == flow_id,
            DataRecordORM.external_id == external_id,
            _VISIBLE,
        )
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.get("/{flow_id}/changes", response_model=DataRecordList)
async def list_changes(
    flow_id: uuid.UUID,
    since: datetime = Query(..., description="ISO datetime — return records updated after this time"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKeyORM = Depends(require_consumer_key),
):
    """Return records changed since a given timestamp (delta sync)."""
    base_query = select(DataRecordORM).where(
        DataRecordORM.flow_id == flow_id,
        DataRecordORM.updated_at > since,
        _VISIBLE,
    )
    count_result = await db.execute(
        select(func.count(DataRecordORM.id)).where(
            DataRecordORM.flow_id == flow_id,
            DataRecordORM.updated_at > since, _VISIBLE,
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        base_query.order_by(DataRecordORM.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return DataRecordList(
        records=result.scalars().all(),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{flow_id}/summary")
async def get_flow_summary(
    flow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKeyORM = Depends(require_consumer_key),
):
    count_result = await db.execute(
        select(func.count(DataRecordORM.id)).where(DataRecordORM.flow_id == flow_id, _VISIBLE)
    )
    record_count = count_result.scalar() or 0

    last_exec_result = await db.execute(
        select(ExecutionLogORM)
        .where(ExecutionLogORM.flow_id == flow_id, ExecutionLogORM.status == "success")
        .order_by(ExecutionLogORM.finished_at.desc())
        .limit(1)
    )
    last_exec = last_exec_result.scalar_one_or_none()

    return {
        "flow_id": str(flow_id),
        "record_count": record_count,
        "last_sync": last_exec.finished_at.isoformat() if last_exec and last_exec.finished_at else None,
        "status": "active" if record_count > 0 else "empty",
    }
