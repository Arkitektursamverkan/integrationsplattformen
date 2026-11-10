"""Konsumentnycklar utan scopes får data:read.

Scopes verkställs från och med nu, och data-API:t kräver data:read. En nyckel
som skapats med en tom lista har hittills kunnat läsa allt – den får scopet,
så att den fungerar som förut.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.execute("""UPDATE api_keys SET scopes = '["data:read"]'::jsonb WHERE scopes = '[]'::jsonb""")


def downgrade():
    # Vilka nycklar som var tomma går inte att veta; scopet är ofarligt kvar.
    pass
