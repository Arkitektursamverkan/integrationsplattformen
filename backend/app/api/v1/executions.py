"""Execution log endpoints — view flow run history."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.execution_log import ExecutionLogORM
from app.dependencies import require_auth
from app.schemas.execution import ExecutionLogList, ExecutionLogRead
from app.services.maskering import rensa_felmeddelande, är_admin

router = APIRouter()


def _för(principal, execution) -> ExecutionLogRead:
    """Felmeddelandet kortat och utan frågesträngar för alla utom administratörer."""
    läst = ExecutionLogRead.model_validate(execution)
    if är_admin(principal) or not läst.error_message:
        return läst
    return läst.model_copy(update={"error_message": rensa_felmeddelande(läst.error_message)})


@router.get("", response_model=ExecutionLogList)
async def list_executions(
    flow_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_auth),
):
    query = select(ExecutionLogORM)
    count_query = select(func.count(ExecutionLogORM.id))

    if flow_id:
        query = query.where(ExecutionLogORM.flow_id == flow_id)
        count_query = count_query.where(ExecutionLogORM.flow_id == flow_id)
    if status:
        query = query.where(ExecutionLogORM.status == status)
        count_query = count_query.where(ExecutionLogORM.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(ExecutionLogORM.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ExecutionLogList(
        executions=[_för(principal, e) for e in result.scalars().all()],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{execution_id}", response_model=ExecutionLogRead)
async def get_execution(execution_id: uuid.UUID, db: AsyncSession = Depends(get_db), principal=Depends(require_auth)):
    result = await db.execute(
        select(ExecutionLogORM).where(ExecutionLogORM.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return _för(principal, execution)
