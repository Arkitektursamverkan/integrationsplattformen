"""Flow model — a configured data pipeline definition."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class FlowORM(Base, TimestampMixin):
    __tablename__ = "flows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    flow_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    post_exec_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    connection = relationship("ConnectionORM", back_populates="flows")
    steps = relationship("FlowStepORM", back_populates="flow", cascade="all, delete-orphan", order_by="FlowStepORM.step_order")
    schedules = relationship("ScheduleORM", back_populates="flow", cascade="all, delete-orphan")
    webhook_endpoints = relationship("WebhookEndpointORM", back_populates="flow", cascade="all, delete-orphan")
    data_records = relationship("DataRecordORM", back_populates="flow", cascade="all, delete-orphan")
    execution_logs = relationship("ExecutionLogORM", back_populates="flow", cascade="all, delete-orphan")
