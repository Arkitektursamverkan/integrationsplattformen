"""Pydantic schemas for Flow and FlowStep CRUD operations."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FlowStepCreate(BaseModel):
    step_order: int = 0
    step_type: str = Field(..., max_length=30)
    config: dict = Field(default_factory=dict)


class FlowStepRead(BaseModel):
    id: uuid.UUID
    flow_id: uuid.UUID
    step_order: int
    step_type: str
    config: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FlowCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    connection_id: uuid.UUID
    enabled: bool = True
    flow_definition: dict | None = None
    post_exec_webhook_url: str | None = Field(None, max_length=500)
    steps: list[FlowStepCreate] = Field(default_factory=list)


class FlowUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    enabled: bool | None = None
    flow_definition: dict | None = None
    post_exec_webhook_url: str | None = None
    steps: list[FlowStepCreate] | None = None


class FlowRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    connection_id: uuid.UUID
    enabled: bool
    flow_definition: dict | None
    post_exec_webhook_url: str | None = None
    steps: list[FlowStepRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FlowSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    connection_id: uuid.UUID
    enabled: bool
    post_exec_webhook_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
