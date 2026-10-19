"""Add post_exec_webhook_url to flows table.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    op.add_column("flows", sa.Column("post_exec_webhook_url", sa.String(500), nullable=True))


def downgrade():
    op.drop_column("flows", "post_exec_webhook_url")
