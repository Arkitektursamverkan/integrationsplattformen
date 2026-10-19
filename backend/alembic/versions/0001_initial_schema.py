"""Initial schema — all core tables for the integration platform.

Revision ID: 0001
Revises:
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── connections ────────────────────────────────────────────────────────
    op.create_table(
        "connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("connector_type", sa.String(50), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("credentials_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("auth_type", sa.String(30), nullable=False, server_default="none"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── flows ─────────────────────────────────────────────────────────────
    op.create_table(
        "flows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("flow_definition", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── flow_steps ────────────────────────────────────────────────────────
    op.create_table(
        "flow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("step_type", sa.String(30), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── schedules ─────────────────────────────────────────────────────────
    op.create_table(
        "schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── webhook_endpoints ─────────────────────────────────────────────────
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path_token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("secret", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── data_records ──────────────────────────────────────────────────────
    op.create_table(
        "data_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("flow_id", "source_type", "external_id", name="uq_data_record_source"),
    )

    # ── execution_logs ────────────────────────────────────────────────────
    op.create_table(
        "execution_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
    )

    # ── api_keys ──────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("key_prefix", sa.String(8), nullable=False),
        sa.Column("scopes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("execution_logs")
    op.drop_table("data_records")
    op.drop_table("webhook_endpoints")
    op.drop_table("schedules")
    op.drop_table("flow_steps")
    op.drop_table("flows")
    op.drop_table("connections")
