"""Pydantic schemas for ExecutionLog responses."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ExecutionLogRead(BaseModel):
    id: uuid.UUID
    flow_id: uuid.UUID
    trigger_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    records_processed: int
    records_created: int
    records_updated: int
    error_message: str | None
    details: dict | None

    model_config = {"from_attributes": True}


class ExecutionLogList(BaseModel):
    executions: list[ExecutionLogRead]
    total: int
    page: int
    page_size: int
