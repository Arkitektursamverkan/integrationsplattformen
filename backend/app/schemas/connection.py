"""Pydantic schemas for Connection CRUD operations."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConnectionCreate(BaseModel):
    name: str = Field(..., max_length=255)
    connector_type: str = Field(..., max_length=50)
    description: str | None = None
    config: dict = Field(default_factory=dict)
    credentials: dict | None = None
    auth_type: str = Field(default="none", max_length=30)


class ConnectionUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    config: dict | None = None
    credentials: dict | None = None
    auth_type: str | None = None
    status: str | None = None


class ConnectionRead(BaseModel):
    id: uuid.UUID
    name: str
    connector_type: str
    description: str | None
    config: dict
    auth_type: str
    status: str
    last_tested_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Om inloggningsuppgifter finns sparade (själva uppgifterna visas aldrig).
    has_credentials: bool = False
    # Bara i svaret på en ändring: uppgifterna tömdes eftersom adressens värd
    # eller certifikatprövningen ändrades – de måste anges igen.
    credentials_cleared: bool = False

    model_config = {"from_attributes": True}
