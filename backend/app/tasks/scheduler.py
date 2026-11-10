"""APScheduler integration — runs flows on cron schedules."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session
from app.models.execution_log import ExecutionLogORM
from app.models.schedule import ScheduleORM

log = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _parse_cron(expression: str, tz: str = "UTC") -> CronTrigger:
    """Parse a 5-field cron expression into an APScheduler CronTrigger."""
    parts = expression.strip().split()
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week,
            timezone=tz,
        )
    if len(parts) == 6:
        second, minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            second=second, minute=minute, hour=hour, day=day, month=month,
            day_of_week=day_of_week, timezone=tz,
        )
    raise ValueError(f"Invalid cron expression: {expression}")


async def _run_scheduled_flow(schedule_id: str, flow_id: str) -> None:
    """Execute a flow triggered by the scheduler."""
    from app.services.flow_service import FlowDisabled, execute_flow

    log.info("scheduler.trigger", schedule_id=schedule_id, flow_id=flow_id)
    async with async_session() as db:
        try:
            import uuid
            try:
                execution = await execute_flow(db, uuid.UUID(flow_id), trigger_type="schedule")
            except FlowDisabled:
                # Inaktiverat flöde: schemat står kvar men kör inget.
                return
            log.info(
                "scheduler.done",
                schedule_id=schedule_id,
                flow_id=flow_id,
                status=execution.status,
                records=execution.records_processed,
            )

            # Update last_run_at on the schedule
            result = await db.execute(
                select(ScheduleORM).where(ScheduleORM.id == uuid.UUID(schedule_id))
            )
            schedule = result.scalar_one_or_none()
            if schedule:
                schedule.last_run_at = datetime.now(timezone.utc)
                # Compute next_run_at from the scheduler job
                job = _scheduler.get_job(schedule_id) if _scheduler else None
                if job and job.next_run_time:
                    schedule.next_run_at = job.next_run_time
                await db.commit()

        except Exception as e:
            log.error("scheduler.error", schedule_id=schedule_id, flow_id=flow_id, error=str(e))


def _add_schedule_job(schedule: ScheduleORM) -> None:
    """Add or replace a job for a schedule."""
    if not _scheduler:
        return
    job_id = str(schedule.id)
    try:
        trigger = _parse_cron(schedule.cron_expression, schedule.timezone)
    except ValueError as e:
        log.warning("scheduler.invalid_cron", schedule_id=job_id, error=str(e))
        return

    _scheduler.add_job(
        _run_scheduled_flow,
        trigger=trigger,
        id=job_id,
        args=[job_id, str(schedule.flow_id)],
        replace_existing=True,
        name=f"flow-{schedule.flow_id}",
    )
    log.info("scheduler.job_added", schedule_id=job_id, cron=schedule.cron_expression)


async def _load_schedules() -> None:
    """Load all enabled schedules from DB and register them with APScheduler."""
    async with async_session() as db:
        result = await db.execute(
            select(ScheduleORM).where(ScheduleORM.enabled.is_(True))
        )
        schedules = result.scalars().all()
        for schedule in schedules:
            _add_schedule_job(schedule)

        # Update next_run_at for all loaded schedules
        for schedule in schedules:
            job = _scheduler.get_job(str(schedule.id)) if _scheduler else None
            if job and job.next_run_time:
                schedule.next_run_at = job.next_run_time
        await db.commit()

        log.info("scheduler.loaded", count=len(schedules))


async def _prune_execution_logs() -> None:
    """Delete execution logs older than the configured retention period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.EXECUTION_LOG_RETENTION_DAYS)
    async with async_session() as db:
        result = await db.execute(
            delete(ExecutionLogORM).where(ExecutionLogORM.started_at < cutoff)
        )
        count = result.rowcount
        await db.commit()
        if count:
            log.info("scheduler.logs_pruned", deleted=count, retention_days=settings.EXECUTION_LOG_RETENTION_DAYS)


async def start_scheduler() -> None:
    """Start the scheduler and load existing schedules."""
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    log.info("scheduler.started")
    await _load_schedules()

    # Daily log retention cleanup at 03:00
    _scheduler.add_job(
        _prune_execution_logs,
        CronTrigger(hour=3, minute=0),
        id="__log_retention__",
        replace_existing=True,
        name="execution-log-retention",
    )


async def shutdown_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler.stopped")


def sync_schedule(schedule: ScheduleORM) -> None:
    """Add or update a schedule job. Call after CRUD operations.
    Also updates next_run_at on the ORM object (caller must commit).
    """
    if not _scheduler:
        return
    if schedule.enabled:
        _add_schedule_job(schedule)
        job = _scheduler.get_job(str(schedule.id))
        if job and job.next_run_time:
            schedule.next_run_at = job.next_run_time
    else:
        remove_schedule(str(schedule.id))
        schedule.next_run_at = None


def remove_schedule(schedule_id: str) -> None:
    """Remove a schedule job. Call after delete."""
    if not _scheduler:
        return
    try:
        _scheduler.remove_job(schedule_id)
        log.info("scheduler.job_removed", schedule_id=schedule_id)
    except Exception:
        pass  # Job may not exist
