"""Pydantic schemas for Schedule CRUD operations."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ScheduleCreate(BaseModel):
    flow_id: uuid.UUID
    cron_expression: str = Field(..., max_length=100)
    timezone: str = Field(default="UTC", max_length=50)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    cron_expression: str | None = Field(None, max_length=100)
    timezone: str | None = None
    enabled: bool | None = None


class ScheduleRead(BaseModel):
    id: uuid.UUID
    flow_id: uuid.UUID
    cron_expression: str
    timezone: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
