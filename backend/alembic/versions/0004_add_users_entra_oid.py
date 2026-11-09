"""Add entra_oid to users table.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"


def upgrade():
    op.add_column("users", sa.Column("entra_oid", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_users_entra_oid", "users", ["entra_oid"])


def downgrade():
    op.drop_constraint("uq_users_entra_oid", "users", type_="unique")
    op.drop_column("users", "entra_oid")
