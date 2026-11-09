"""Säkerhetsgranskningens rättelser: CSV, gränser, webhook-hemlighet, nycklar och data-API:t."""
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from starlette.requests import Request

from app.api.v1 import csv_upload
from app.config import settings
from app.database import get_db
from app.dependencies import require_data_access
from app.main import create_app
from app.models.api_key import ApiKeyORM
from app.models.connection import ConnectionORM
from app.models.data_record import DataRecordORM
from app.models.execution_log import ExecutionLogORM
from app.models.flow import FlowORM
from app.models.flow_step import FlowStepORM
from app.models.user import UserORM
from app.models.webhook_endpoint import WebhookEndpointORM
from app.ratelimit import client_address, limiter
from app.services.auth_service import create_access_token, hash_password


@compiles(JSONB, "sqlite")
def _jsonb_i_sqlite(type_, compiler, **kw):
    return "JSON"


ADMIN = {"X-Api-Key": "test-admin-key"}
TABELLER = [UserORM, ConnectionORM, FlowORM, FlowStepORM, DataRecordORM, ExecutionLogORM,
            WebhookEndpointORM, ApiKeyORM]


@pytest.fixture
async def sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/s.db")
    async with engine.begin() as c:
        for t in TABELLER:
            await c.run_sync(t.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(sessions):
    async def db():
        async with sessions() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_db] = db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _flöde(sessions, connector_type: str) -> uuid.UUID:
    async with sessions() as s:
        conn = ConnectionORM(id=uuid.uuid4(), name="k", connector_type=connector_type, config={},
                             auth_type="none", status="active")
        flow = FlowORM(id=uuid.uuid4(), name="f", connection_id=conn.id, enabled=True)
        s.add(conn)
        await s.flush()
        s.add(flow)
        await s.commit()
        return flow.id


def _fil(innehåll: bytes = b"external_id;namn\n1;a\n2;b\n"):
    return {"file": ("d.csv", innehåll, "text/csv")}


# ── CSV ──────────────────────────────────────────────────────────────────────

async def test_csv_upload_and_replace_need_admin(client, sessions):
    flow_id = await _flöde(sessions, "csv")
    viewer = {"Authorization": "Bearer " + create_access_token(str(uuid.uuid4()), "v", "viewer")}
    r = await client.post("/api/v1/csv/upload", files=_fil(), data={"name": "x"}, headers=viewer)
    assert r.status_code == 403
    r = await client.post(f"/api/v1/csv/replace/{flow_id}", files=_fil(), headers=viewer)
    assert r.status_code == 403


async def test_csv_replace_only_csv_flows(client, sessions):
    annan = await _flöde(sessions, "rest_api")
    r = await client.post(f"/api/v1/csv/replace/{annan}", files=_fil(), headers=ADMIN)
    assert r.status_code == 400
    csv = await _flöde(sessions, "csv")
    r = await client.post(f"/api/v1/csv/replace/{csv}", files=_fil(), headers=ADMIN)
    assert r.status_code == 200 and r.json()["total_records"] == 2


async def test_csv_too_large(client, monkeypatch):
    monkeypatch.setattr(csv_upload, "MAX_UPLOAD_BYTES", 100)
    monkeypatch.setattr(csv_upload, "_CHUNK", 16)
    r = await client.post("/api/v1/csv/preview", files=_fil(b"a;b\n" + b"1;2\n" * 50), headers=ADMIN)
    assert r.status_code == 413
    r = await client.post("/api/v1/csv/preview", files=_fil(), headers=ADMIN)
    assert r.status_code == 200


# ── Webhook ──────────────────────────────────────────────────────────────────

async def test_webhook_secret_required(client, sessions, monkeypatch):
    flow_id = await _flöde(sessions, "rest_api")
    async with sessions() as s:
        s.add(WebhookEndpointORM(id=uuid.uuid4(), flow_id=flow_id, path_token="med", secret="hemligt"))
        s.add(WebhookEndpointORM(id=uuid.uuid4(), flow_id=flow_id, path_token="utan", secret=None))
        await s.commit()

    class Körning:
        status, id, records_processed = "success", uuid.uuid4(), 0

    async def kör(db, flow_id, trigger_type):
        return Körning()

    from app.services import flow_service
    monkeypatch.setattr(flow_service, "execute_flow", kör)
    url = "/api/v1/webhooks/receive/"
    assert (await client.post(url + "med", json={})).status_code == 401
    assert (await client.post(url + "med", json={}, headers={"X-Webhook-Secret": "fel"})).status_code == 401
    assert (await client.post(url + "med", json={}, headers={"X-Webhook-Secret": "hemligt"})).status_code == 200
    assert (await client.post(url + "utan", json={})).status_code == 200


# ── Gränser ──────────────────────────────────────────────────────────────────

@pytest.fixture
def gränser_på():
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


async def test_login_rate_limited(client, gränser_på):
    for _ in range(10):
        r = await client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
        assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
    assert r.status_code == 429


def _anrop(xff: str | None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": ("10.0.0.1", 1234)})


def test_forwarded_for_only_when_trusted(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", False)
    assert client_address(_anrop("1.2.3.4, 10.0.0.9")) == "10.0.0.1"
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    assert client_address(_anrop("1.2.3.4, 10.0.0.9")) == "1.2.3.4"
    assert client_address(_anrop(None)) == "10.0.0.1"


# ── Nycklar ──────────────────────────────────────────────────────────────────

async def test_consumer_keys_sharing_a_prefix(sessions):
    async with sessions() as s:
        s.add(ApiKeyORM(name="a", key_hash=hash_password("abcdefgh-ett"), key_prefix="abcdefgh", scopes=[]))
        s.add(ApiKeyORM(name="b", key_hash=hash_password("abcdefgh-två"), key_prefix="abcdefgh", scopes=[],
                        expires_at=datetime.now() + timedelta(days=1)))
        s.add(ApiKeyORM(name="c", key_hash=hash_password("abcdefgh-gammal"), key_prefix="abcdefgh", scopes=[],
                        expires_at=datetime.now() - timedelta(days=1)))
        await s.commit()
        assert (await require_data_access(x_api_key="abcdefgh-ett", credentials=None, db=s)).name == "a"
        # SQLite ger tider utan tidszon – jämförs som UTC.
        assert (await require_data_access(x_api_key="abcdefgh-två", credentials=None, db=s)).name == "b"
        with pytest.raises(Exception) as e:
            await require_data_access(x_api_key="abcdefgh-gammal", credentials=None, db=s)
        assert e.value.status_code == 401
        with pytest.raises(Exception) as e:
            await require_data_access(x_api_key="test-admin-kex", credentials=None, db=s)
        assert e.value.status_code == 401
        assert await require_data_access(x_api_key="test-admin-key", credentials=None, db=s) is None


# ── Data-API:t ───────────────────────────────────────────────────────────────

async def test_data_api_hides_csv_originals(client, sessions):
    flow_id = await _flöde(sessions, "csv")
    async with sessions() as s:
        for typ, värde in (("csv_original", "original"), ("csv", "arbetskopia")):
            s.add(DataRecordORM(id=uuid.uuid4(), flow_id=flow_id, source_type=typ, external_id="1",
                                data={"v": värde}, checksum="x", version=1))
        await s.commit()
    r = await client.get(f"/api/v1/data/{flow_id}/records/by-external/1", headers=ADMIN)
    assert r.status_code == 200 and r.json()["data"] == {"v": "arbetskopia"}
    r = await client.get(f"/api/v1/data/{flow_id}/changes", params={"since": "2000-01-01T00:00:00"}, headers=ADMIN)
    assert r.status_code == 200
    assert [x["data"]["v"] for x in r.json()["records"]] == ["arbetskopia"] and r.json()["total"] == 1
