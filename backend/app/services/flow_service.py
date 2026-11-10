"""Flow execution service — orchestrates: fetch -> transform -> store."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone

import anyio
import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings

from app.connectors.base import BaseConnector
from app.connectors.registry import get_connector_class
from app.models.connection import ConnectionORM
from app.models.data_record import DataRecordORM
from app.models.execution_log import ExecutionLogORM
from app.models.flow import FlowORM
from app.models.flow_step import FlowStepORM
from app.services.crypto_service import decrypt_credentials
from app.services.transform_engine import apply_operations

log = structlog.get_logger(__name__)

MAX_RETRIES = 3


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    reraise=True,
    before_sleep=lambda retry_state: log.warning(
        "flow.fetch_retry",
        attempt=retry_state.attempt_number,
        wait=retry_state.next_action.sleep if retry_state.next_action else 0,
    ),
)
async def _fetch_with_retry(connector: "BaseConnector") -> list[dict]:
    """Fetch data from connector with exponential backoff on transient errors."""
    return await connector.fetch()


def _checksum(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


class FlowDisabled(Exception):
    """Flödet är inaktiverat och körs inte av webhook eller schema."""


# Ett inaktiverat flöde körs bara när en administratör startar det för hand
# (trigger_type="manual") – t.ex. för att prova det innan det slås på.
_KÖRS_ÄVEN_INAKTIVERAT = {"manual"}


async def execute_flow(db: AsyncSession, flow_id: uuid.UUID, trigger_type: str = "manual") -> ExecutionLogORM:
    """Execute a flow: fetch data, apply transforms, upsert records.

    Ett inaktiverat flöde (enabled=False) ger FlowDisabled för webhook och
    schema; en manuell körning (bara administratörer) går, och loggas."""
    flow = (await db.execute(select(FlowORM).where(FlowORM.id == flow_id))).scalar_one_or_none()
    if flow is not None and not flow.enabled:
        if trigger_type not in _KÖRS_ÄVEN_INAKTIVERAT:
            log.info("flow.disabled_skipped", flow_id=str(flow_id), trigger=trigger_type)
            raise FlowDisabled(f"Flow {flow_id} is disabled")
        log.warning("flow.disabled_manual_run", flow_id=str(flow_id), trigger=trigger_type)

    now = datetime.now(timezone.utc)

    # Create execution log
    execution = ExecutionLogORM(
        id=uuid.uuid4(),
        flow_id=flow_id,
        trigger_type=trigger_type,
        status="running",
        started_at=now,
    )
    db.add(execution)
    await db.flush()

    try:
        # Load flow with steps
        result = await db.execute(
            select(FlowORM).where(FlowORM.id == flow_id)
        )
        flow = result.scalar_one_or_none()
        if not flow:
            raise ValueError(f"Flow {flow_id} not found")

        # Load connection
        result = await db.execute(
            select(ConnectionORM).where(ConnectionORM.id == flow.connection_id)
        )
        connection = result.scalar_one_or_none()
        if not connection:
            raise ValueError(f"Connection {flow.connection_id} not found")

        # Decrypt credentials
        credentials = {}
        if connection.credentials_encrypted:
            credentials = decrypt_credentials(connection.credentials_encrypted)

        # Instantiate connector
        connector_cls = get_connector_class(connection.connector_type)
        connector: BaseConnector = connector_cls(
            connection_config=connection.config,
            credentials=credentials,
        )

        # Fetch raw data
        log.info("flow.fetch_start", flow_id=str(flow_id), connector=connection.connector_type)
        if connection.connector_type == "csv":
            # CSV flows: always re-process from the ORIGINAL uploaded data
            existing_data = await db.execute(
                select(DataRecordORM).where(
                    DataRecordORM.flow_id == flow_id,
                    DataRecordORM.source_type == "csv_original",
                )
            )
            records = [r.data for r in existing_data.scalars().all()]
            if not records:
                # Fallback: if no originals exist (old data before this feature), use csv records
                existing_data = await db.execute(
                    select(DataRecordORM).where(
                        DataRecordORM.flow_id == flow_id,
                        DataRecordORM.source_type == "csv",
                    )
                )
                records = [r.data for r in existing_data.scalars().all()]
        else:
            records = await _fetch_with_retry(connector)
        log.info("flow.fetch_done", flow_id=str(flow_id), record_count=len(records))

        # Load and apply steps in order
        steps_result = await db.execute(
            select(FlowStepORM)
            .where(FlowStepORM.flow_id == flow_id)
            .order_by(FlowStepORM.step_order)
        )
        steps = steps_result.scalars().all()

        # I en tråd: ett steg med en användares regex eller mall får inte
        # hänga händelseloopen (och därmed alla andra anrop).
        stegen = [(step.step_type, step.config) for step in steps]
        records = await anyio.to_thread.run_sync(apply_operations, records, stegen)

        source_type = connection.connector_type

        if connection.connector_type == "csv":
            # CSV flows: replace all working records (keep csv_original intact)
            old_working = await db.execute(
                select(DataRecordORM).where(
                    DataRecordORM.flow_id == flow_id,
                    DataRecordORM.source_type == "csv",
                )
            )
            for old in old_working.scalars().all():
                await db.delete(old)
            await db.flush()

            created = 0
            updated = 0
            for record_data in records:
                external_id = str(record_data.get("external_id", str(uuid.uuid4())))
                cs = _checksum(record_data)
                db.add(DataRecordORM(
                    id=uuid.uuid4(), flow_id=flow_id, source_type="csv",
                    external_id=external_id, data=record_data, checksum=cs, version=1,
                ))
                created += 1
        else:
            # Non-CSV flows: upsert + prune
            created = 0
            updated = 0
            for record_data in records:
                external_id = str(record_data.get("external_id", str(uuid.uuid4())))
                cs = _checksum(record_data)

                existing_result = await db.execute(
                    select(DataRecordORM).where(
                        DataRecordORM.flow_id == flow_id,
                        DataRecordORM.source_type == source_type,
                        DataRecordORM.external_id == external_id,
                    )
                )
                existing = existing_result.scalar_one_or_none()

                if existing:
                    if existing.checksum != cs:
                        existing.data = record_data
                        existing.checksum = cs
                        existing.version += 1
                        existing.updated_at = now
                        updated += 1
                else:
                    db.add(DataRecordORM(
                        id=uuid.uuid4(), flow_id=flow_id, source_type=source_type,
                        external_id=external_id, data=record_data, checksum=cs, version=1,
                    ))
                    created += 1

            # Prune: remove records no longer in result set
            current_external_ids = {str(r.get("external_id", "")) for r in records}
            existing_result = await db.execute(
                select(DataRecordORM).where(
                    DataRecordORM.flow_id == flow_id,
                    DataRecordORM.source_type == source_type,
                )
            )
            pruned = 0
            for existing in existing_result.scalars().all():
                if existing.external_id not in current_external_ids:
                    await db.delete(existing)
                    pruned += 1
            if pruned:
                log.info("flow.pruned", flow_id=str(flow_id), pruned=pruned)

        # Update execution log
        execution.status = "success"
        execution.finished_at = datetime.now(timezone.utc)
        execution.records_processed = len(records)
        execution.records_created = created
        execution.records_updated = updated

        await db.commit()
        log.info("flow.execute_done", flow_id=str(flow_id), created=created, updated=updated)

        # Fire post-execution webhook if configured
        if flow.post_exec_webhook_url:
            await _send_post_exec_webhook(
                flow.post_exec_webhook_url,
                flow_id=flow_id,
                flow_name=flow.name,
                trigger_type=trigger_type,
                records_processed=len(records),
                records_created=created,
                records_updated=updated,
            )

    except Exception as e:
        execution.status = "error"
        execution.finished_at = datetime.now(timezone.utc)
        execution.error_message = str(e)
        await db.commit()
        log.error("flow.execute_error", flow_id=str(flow_id), error=str(e))
        await _send_failure_alert(flow_id, trigger_type, str(e))

    return execution


async def _send_failure_alert(flow_id: uuid.UUID, trigger_type: str, error: str) -> None:
    """Send a webhook notification when a flow execution fails."""
    url = settings.ALERT_WEBHOOK_URL
    if not url:
        return
    payload = {
        "event": "flow.execution.failed",
        "flow_id": str(flow_id),
        "trigger_type": trigger_type,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
        log.info("alert.sent", flow_id=str(flow_id), url=url)
    except Exception as exc:
        log.warning("alert.failed", flow_id=str(flow_id), error=str(exc))


def webhook_signatur(body: bytes, timestamp: int | None = None) -> dict[str, str]:
    """Huvudena som signerar webhooken efter en körning.

    Hemligheten (POST_EXEC_WEBHOOK_SECRET) skickas aldrig – adressen styrs av
    den som administrerar flödet, och en hemlighet i klartext vore läst av
    vem som helst den pekar på. I stället:
      X-Webhook-Timestamp: unix-sekunder
      X-Webhook-Signature: sha256=<hex HMAC-SHA256(hemligheten, "<timestamp>." + kroppen)>
    Mottagaren (Arkitekturportalens /sync/webhook) räknar om signaturen över
    den råa kroppen och godtar bara en färsk tidsstämpel. Utan hemlighet: inga huvuden.
    """
    secret = settings.POST_EXEC_WEBHOOK_SECRET
    if not secret:
        return {}
    ts = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode("utf-8"), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Webhook-Timestamp": str(ts), "X-Webhook-Signature": f"sha256={digest}"}


async def _send_post_exec_webhook(
    url: str,
    flow_id: uuid.UUID,
    flow_name: str,
    trigger_type: str,
    records_processed: int,
    records_created: int,
    records_updated: int,
) -> None:
    """Notify a consumer (e.g. EA App) after a successful flow execution."""
    payload = {
        "event": "flow.execution.success",
        "flow_id": str(flow_id),
        "flow_name": flow_name,
        "trigger_type": trigger_type,
        "records_processed": records_processed,
        "records_created": records_created,
        "records_updated": records_updated,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Kroppen serialiseras en gång: det som signeras är exakt det som skickas.
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", **webhook_signatur(body)}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, content=body, headers=headers)
        log.info("post_exec_webhook.sent", flow_id=str(flow_id), url=url, status=resp.status_code)
    except Exception as exc:
        log.warning("post_exec_webhook.failed", flow_id=str(flow_id), url=url, error=str(exc))
