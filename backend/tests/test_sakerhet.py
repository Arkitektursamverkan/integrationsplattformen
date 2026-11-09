"""Inloggning krävs för förvaltningens läsningar, och första kontot kräver engångskoden."""
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_db
from app.main import create_app
from app.models.user import UserORM


@pytest.fixture
async def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/s.db")
    async with engine.begin() as c:
        await c.run_sync(UserORM.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def db():
        async with sessions() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_db] = db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


@pytest.mark.parametrize("väg", ["/connections", "/flows", "/schedules", "/executions", "/webhooks",
                                 "/connections/00000000-0000-0000-0000-000000000000"])
async def test_reads_need_login(client, väg):
    r = await client.get("/api/v1" + väg)
    assert r.status_code in (401, 403), r.text


KONTO = {"username": "forsta", "password": "langtlosenord"}


@pytest.fixture
def produktion(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ENTRA_TENANT_ID", "")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_EMAILS", "")


async def test_setup_without_configured_code_refused(client, produktion, monkeypatch):
    monkeypatch.setattr(settings, "SETUP_CODE", "")
    assert (await client.get("/api/v1/auth/setup")).json() == {"needed": True, "code_required": True}
    assert (await client.post("/api/v1/auth/setup", json=KONTO)).status_code == 403


async def test_setup_needs_the_right_code(client, produktion, monkeypatch):
    monkeypatch.setattr(settings, "SETUP_CODE", "hemlig-kod")
    assert (await client.post("/api/v1/auth/setup", json={**KONTO, "setup_code": "fel"})).status_code == 403
    r = await client.post("/api/v1/auth/setup", json={**KONTO, "setup_code": "hemlig-kod"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    # Bara en gång.
    assert (await client.post("/api/v1/auth/setup", json={**KONTO, "setup_code": "hemlig-kod"})).status_code == 400


async def test_setup_closed_with_entra_and_bootstrap(client, produktion, monkeypatch):
    monkeypatch.setattr(settings, "ENTRA_TENANT_ID", "t")
    monkeypatch.setattr(settings, "ENTRA_CLIENT_ID", "c")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_EMAILS", "anna@example.org")
    monkeypatch.setattr(settings, "SETUP_CODE", "hemlig-kod")
    assert (await client.get("/api/v1/auth/setup")).json()["needed"] is False
    assert (await client.post("/api/v1/auth/setup", json={**KONTO, "setup_code": "hemlig-kod"})).status_code == 403


def test_production_is_the_default():
    from app.config import Settings
    assert Settings.model_fields["APP_ENV"].default == "production"
