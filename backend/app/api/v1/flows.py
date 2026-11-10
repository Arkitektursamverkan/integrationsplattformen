"""CRUD endpoints for integration flows + manual execution trigger."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import require_admin_key, require_auth
from app.models.flow import FlowORM
from app.models.flow_step import FlowStepORM
from app.schemas.execution import ExecutionLogRead
from app.schemas.flow import FlowCreate, FlowRead, FlowSummary, FlowUpdate
from app.services.maskering import MASK, maskera_url, är_admin

router = APIRouter()


def _dold_webhook(principal, läst):
    """Webhookadressen efter körning kan bära en nyckel: en läsare ser bara
    schema och värd."""
    if är_admin(principal) or not läst.post_exec_webhook_url:
        return läst
    return läst.model_copy(update={"post_exec_webhook_url": maskera_url(läst.post_exec_webhook_url)})


@router.get("", response_model=list[FlowSummary])
async def list_flows(db: AsyncSession = Depends(get_db), principal=Depends(require_auth)):
    result = await db.execute(select(FlowORM).order_by(FlowORM.created_at.desc()))
    return [_dold_webhook(principal, FlowSummary.model_validate(f)) for f in result.scalars().all()]


@router.get("/{flow_id}", response_model=FlowRead)
async def get_flow(flow_id: uuid.UUID, db: AsyncSession = Depends(get_db), principal=Depends(require_auth)):
    result = await db.execute(
        select(FlowORM).where(FlowORM.id == flow_id).options(selectinload(FlowORM.steps))
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return _dold_webhook(principal, FlowRead.model_validate(flow))


@router.post("", response_model=FlowRead, status_code=201, dependencies=[Depends(require_admin_key)])
async def create_flow(body: FlowCreate, db: AsyncSession = Depends(get_db)):
    flow = FlowORM(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        connection_id=body.connection_id,
        enabled=body.enabled,
        flow_definition=body.flow_definition,
        post_exec_webhook_url=body.post_exec_webhook_url,
    )
    db.add(flow)
    await db.flush()

    for step_data in body.steps:
        step = FlowStepORM(
            id=uuid.uuid4(),
            flow_id=flow.id,
            step_order=step_data.step_order,
            step_type=step_data.step_type,
            config=step_data.config,
        )
        db.add(step)

    await db.commit()

    # Reload with steps
    result = await db.execute(
        select(FlowORM).where(FlowORM.id == flow.id).options(selectinload(FlowORM.steps))
    )
    return result.scalar_one()


@router.put("/{flow_id}", response_model=FlowRead, dependencies=[Depends(require_admin_key)])
async def update_flow(flow_id: uuid.UUID, body: FlowUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FlowORM).where(FlowORM.id == flow_id).options(selectinload(FlowORM.steps))
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    if body.name is not None:
        flow.name = body.name
    if body.description is not None:
        flow.description = body.description
    if body.enabled is not None:
        flow.enabled = body.enabled
    if body.flow_definition is not None:
        flow.flow_definition = body.flow_definition
    # En dold adress (…) som skickas tillbaka ändrar inget.
    if body.post_exec_webhook_url is not None and not body.post_exec_webhook_url.endswith("/…") \
            and body.post_exec_webhook_url != MASK:
        flow.post_exec_webhook_url = body.post_exec_webhook_url or None

    # Replace steps if provided
    if body.steps is not None:
        for step in flow.steps:
            await db.delete(step)
        await db.flush()
        for step_data in body.steps:
            step = FlowStepORM(
                id=uuid.uuid4(),
                flow_id=flow.id,
                step_order=step_data.step_order,
                step_type=step_data.step_type,
                config=step_data.config,
            )
            db.add(step)

    await db.commit()

    result = await db.execute(
        select(FlowORM).where(FlowORM.id == flow.id).options(selectinload(FlowORM.steps))
    )
    return result.scalar_one()


@router.delete("/{flow_id}", status_code=204, dependencies=[Depends(require_admin_key)])
async def delete_flow(flow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FlowORM).where(FlowORM.id == flow_id))
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    await db.delete(flow)
    await db.commit()


@router.post("/{flow_id}/execute", response_model=ExecutionLogRead, dependencies=[Depends(require_admin_key)])
async def execute_flow_endpoint(flow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.services.flow_service import execute_flow
    execution = await execute_flow(db, flow_id, trigger_type="manual")
    return execution
