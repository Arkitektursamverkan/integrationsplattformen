"""User model — platform users with roles."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserORM(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Entra-kontots oid, satt vid första Microsoft-inloggningen.
    entra_oid: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    # Bäddas in i utfärdade token (tv) och jämförs vid varje begäran; höjs vid
    # lösenordsbyte och "logga ut överallt", så att gamla token slutar gälla.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
