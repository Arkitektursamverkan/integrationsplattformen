"""DATABASE_URL in the forms docker compose and managed databases give it."""
import pytest

from app.config import Settings, asyncpg_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgresql+asyncpg://u:p@plattform-db:5432/integration_db",
         "postgresql+asyncpg://u:p@plattform-db:5432/integration_db"),
        # Render's connectionString
        ("postgresql://u:p@dpg-abc-a/integration_db", "postgresql+asyncpg://u:p@dpg-abc-a/integration_db"),
        ("postgres://u:p@host:5432/integration_db", "postgresql+asyncpg://u:p@host:5432/integration_db"),
        ("postgresql://u:p@host/db?sslmode=require", "postgresql+asyncpg://u:p@host/db?ssl=require"),
        ("sqlite+aiosqlite:///test.db", "sqlite+aiosqlite:///test.db"),
    ],
)
def test_asyncpg_url(raw, expected):
    assert asyncpg_url(raw) == expected


def test_settings_accept_a_managed_database_url():
    s = Settings(DATABASE_URL="postgresql://u:p@dpg-abc-a/integration_db")
    assert s.DATABASE_URL == "postgresql+asyncpg://u:p@dpg-abc-a/integration_db"
