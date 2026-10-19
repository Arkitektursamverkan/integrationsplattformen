"""CRUD endpoints for flow schedules."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin_key
from app.models.schedule import ScheduleORM
from app.schemas.schedule import ScheduleCreate, ScheduleRead, ScheduleUpdate
from app.tasks.scheduler import sync_schedule, remove_schedule

router = APIRouter()


@router.get("", response_model=list[ScheduleRead])
async def list_schedules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScheduleORM).order_by(ScheduleORM.created_at.desc()))
    return result.scalars().all()


@router.get("/{schedule_id}", response_model=ScheduleRead)
async def get_schedule(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScheduleORM).where(ScheduleORM.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.post("", response_model=ScheduleRead, status_code=201, dependencies=[Depends(require_admin_key)])
async def create_schedule(body: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    schedule = ScheduleORM(
        id=uuid.uuid4(),
        flow_id=body.flow_id,
        cron_expression=body.cron_expression,
        timezone=body.timezone,
        enabled=body.enabled,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    sync_schedule(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.put("/{schedule_id}", response_model=ScheduleRead, dependencies=[Depends(require_admin_key)])
async def update_schedule(
    schedule_id: uuid.UUID, body: ScheduleUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ScheduleORM).where(ScheduleORM.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if body.cron_expression is not None:
        schedule.cron_expression = body.cron_expression
    if body.timezone is not None:
        schedule.timezone = body.timezone
    if body.enabled is not None:
        schedule.enabled = body.enabled

    await db.commit()
    await db.refresh(schedule)
    sync_schedule(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/{schedule_id}", status_code=204, dependencies=[Depends(require_admin_key)])
async def delete_schedule(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScheduleORM).where(ScheduleORM.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(schedule)
    await db.commit()
    remove_schedule(str(schedule_id))
