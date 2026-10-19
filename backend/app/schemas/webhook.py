"""Pydantic schemas for Webhook endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WebhookEndpointCreate(BaseModel):
    flow_id: uuid.UUID
    secret: str | None = None
    enabled: bool = True


class WebhookEndpointRead(BaseModel):
    id: uuid.UUID
    flow_id: uuid.UUID
    path_token: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
