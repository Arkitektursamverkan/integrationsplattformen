"""Pydantic schemas for API key management."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["data:read"])
    expires_at: datetime | None = None


class ApiKeyRead(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    enabled: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreated(BaseModel):
    """Returned once on creation — the only time the full key is visible."""
    id: uuid.UUID
    name: str
    key: str
    key_prefix: str
    scopes: list[str]
