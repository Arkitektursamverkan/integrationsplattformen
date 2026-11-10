"""Tokenversion per användare.

Bäddas in i plattformens token (fältet tv) och jämförs vid varje begäran.
Höjs vid lösenordsbyte och "logga ut överallt", så att utfärdade token slutar
gälla. Befintliga token saknar fältet och läses som 0 – de gäller tills de
går ut.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"


def upgrade():
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("users", "token_version")
