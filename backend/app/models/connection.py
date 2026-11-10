"""Connection model — configured external system credentials and settings."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ConnectionORM(Base, TimestampMixin):
    __tablename__ = "connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    auth_type: Mapped[str] = mapped_column(String(30), nullable=False, default="none")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    last_tested_at: Mapped[None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    flows = relationship("FlowORM", back_populates="connection", cascade="all, delete-orphan")

    @property
    def has_credentials(self) -> bool:
        return self.credentials_encrypted is not None
