"""Pydantic schemas for API key management."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    # data:read = läsa data-API:t. flow:<uuid> (valfritt, flera går) begränsar
    # nyckeln till de flödena; utan flow:-scope gäller den alla flöden.
    scopes: list[str] = Field(default_factory=lambda: ["data:read"])
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def kända_scopes(cls, scopes: list[str]) -> list[str]:
        ut: list[str] = []
        for scope in scopes:
            scope = scope.strip()
            if scope.startswith("flow:"):
                try:
                    scope = f"flow:{uuid.UUID(scope[5:])}"
                except ValueError:
                    raise ValueError(f"flow:-scope needs a flow id (uuid): {scope!r}")
            elif scope != "data:read":
                raise ValueError(f"Unknown scope {scope!r} – use data:read and optionally flow:<uuid>")
            if scope not in ut:
                ut.append(scope)
        return ut


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
