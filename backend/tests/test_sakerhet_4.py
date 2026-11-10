"""Säkerhetsgranskningens fjärde omgång (låga fynd): tokenversion, Entra-
koppling och gäster, engångskoden, dolda hemligheter för läsare,
kroppsstorlek, inaktiverade flöden och transformstegens gränser."""
import time
import uuid
from datetime import datetime, timezone

import pytest

from app.config import Settings, settings
from app.kroppsgrans import MAX_BODY_BYTES
from app.models.connection import ConnectionORM
from app.models.execution_log import ExecutionLogORM
from app.models.flow import FlowORM
from app.models.user import UserORM
from app.services import entra, maskering, transform_engine
from app.services.auth_service import create_access_token, create_refresh_token, hash_password
from app.services.transform_engine import TransformError, apply_operation

from tests.test_entra import JWKS, _token  # noqa: F401
from tests.test_entra import db  # noqa: F401 (fixtur)
from tests.test_sakerhet_2 import ADMIN, _flöde, client, sessions  # noqa: F401 (fixturer)


async def _användare(sessions, namn="anna", lösenord="gammalt-lösenord", roll="viewer") -> UserORM:
    async with sessions() as s:
        u = UserORM(id=uuid.uuid4(), username=namn, password_hash=hash_password(lösenord),
                    role=roll, is_active=True)
        s.add(u)
        await s.commit()
        return u


def _bärare(token: str) -> dict:
    return {"Authorization": "Bearer " + token}


# ── 1. Tokenversion ──────────────────────────────────────────────────────────

async def test_password_change_revokes_tokens(client, sessions):
    """REGRESSION: token utfärdade före ett lösenordsbyte fortsatte gälla."""
    await _användare(sessions)
    r = await client.post("/api/v1/auth/login", json={"username": "anna", "password": "gammalt-lösenord"})
    gamla = r.json()
    assert (await client.get("/api/v1/auth/me", headers=_bärare(gamla["access_token"]))).status_code == 200

    r = await client.put("/api/v1/auth/me/password", headers=_bärare(gamla["access_token"]),
                         json={"current_password": "gammalt-lösenord", "new_password": "nytt-lösenord"})
    assert r.status_code == 200
    nya = r.json()

    assert (await client.get("/api/v1/auth/me", headers=_bärare(gamla["access_token"]))).status_code == 401
    assert (await client.get("/api/v1/flows", headers=_bärare(gamla["access_token"]))).status_code == 401
    assert (await client.post("/api/v1/auth/refresh",
                              json={"refresh_token": gamla["refresh_token"]})).status_code == 401
    # Den som bytte får nya token och fortsätter.
    assert (await client.get("/api/v1/auth/me", headers=_bärare(nya["access_token"]))).status_code == 200
    assert (await client.post("/api/v1/auth/refresh",
                              json={"refresh_token": nya["refresh_token"]})).status_code == 200


async def test_logout_everywhere(client, sessions):
    await _användare(sessions)
    t = (await client.post("/api/v1/auth/login",
                           json={"username": "anna", "password": "gammalt-lösenord"})).json()
    assert (await client.post("/api/v1/auth/me/logout-all", headers=_bärare(t["access_token"]))).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=_bärare(t["access_token"]))).status_code == 401


async def test_old_tokens_without_version_still_valid(client, sessions):
    """Token utfärdade före uppgraderingen saknar tv och gäller tills de går ut."""
    u = await _användare(sessions)
    from jose import jwt
    from datetime import datetime, timedelta, timezone
    gammal = jwt.encode({"sub": str(u.id), "username": "anna", "role": "viewer", "type": "access",
                         "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                        settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    assert (await client.get("/api/v1/auth/me", headers=_bärare(gammal))).status_code == 200
    # Men inte efter att versionen höjts.
    async with sessions() as s:
        rad = await s.get(UserORM, u.id)
        rad.token_version = 1
        await s.commit()
    assert (await client.get("/api/v1/auth/me", headers=_bärare(gammal))).status_code == 401
    assert (await client.get("/api/v1/auth/me",
                             headers=_bärare(create_access_token(str(u.id), "anna", "viewer", 1)))).status_code == 200
    assert (await client.post("/api/v1/auth/refresh",
                              json={"refresh_token": create_refresh_token(str(u.id))})).status_code == 401


# ── 2. Entra ─────────────────────────────────────────────────────────────────

@pytest.fixture
def _entra(monkeypatch):
    monkeypatch.setattr(settings, "ENTRA_TENANT_ID", "tenant-1")
    monkeypatch.setattr(settings, "ENTRA_CLIENT_ID", "client-1")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_EMAILS", "anna@example.org")


async def test_local_account_with_password_not_linked(db, _entra):
    """REGRESSION: ett lokalt konto med lösenord kopplades till vilket Entra-konto
    som helst med samma preferred_username."""
    db.add(UserORM(username="bertil", email="bertil@example.org",
                   password_hash=hash_password("lösenordet"), role="admin"))
    await db.commit()
    with pytest.raises(entra.EntraForbidden, match="lokalt konto"):
        await entra.användare(db, {"preferred_username": "bertil@example.org", "oid": "oid-b"})


async def test_account_without_password_linked(db, _entra):
    db.add(UserORM(username="bertil", email="bertil@example.org",
                   password_hash=entra.INGET_LÖSENORD, role="viewer"))
    await db.commit()
    u = await entra.användare(db, {"preferred_username": "bertil@example.org", "oid": "oid-b"})
    assert (u.username, u.entra_oid) == ("bertil", "oid-b")


@pytest.mark.parametrize("claims", [
    {"acct": 1},
    {"idp": "https://sts.windows.net/annan-tenant/"},
    {"idp": "live.com"},
    {"tid": "annan-tenant"},
    {"upn": "anna_example.org#EXT#@tenant.onmicrosoft.com"},
])
async def test_guests_refused(db, _entra, claims):
    """REGRESSION: B2B-gäster släpptes in om e-posten stämde."""
    with pytest.raises(entra.EntraForbidden, match="Gäst"):
        await entra.användare(db, {"preferred_username": "anna@example.org", "oid": "oid-a", **claims})


async def test_member_not_guest(_entra):
    assert not entra.är_gäst({"tid": "tenant-1", "idp": "https://sts.windows.net/tenant-1/", "acct": 0})
    assert not entra.är_gäst({"preferred_username": "anna@example.org"})


async def test_bootstrap_only_without_admin(db, _entra, monkeypatch):
    """REGRESSION: BOOTSTRAP_ADMIN_EMAILS gjorde adressen till admin även när
    installationen redan hade administratörer."""
    db.add(UserORM(username="chef", email="chef@example.org", password_hash="x", role="admin",
                   is_active=True, entra_oid="oid-chef"))
    db.add(UserORM(username="anna", email="anna@example.org", password_hash=entra.INGET_LÖSENORD,
                   role="viewer", is_active=True))
    await db.commit()
    u = await entra.användare(db, {"preferred_username": "anna@example.org", "oid": "oid-a"})
    assert u.role == "viewer"
    # Och ingen ny administratör skapas.
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_EMAILS", "anna@example.org,ny@example.org")
    with pytest.raises(entra.EntraForbidden):
        await entra.användare(db, {"preferred_username": "ny@example.org", "oid": "oid-ny"})


async def test_required_scope_configurable(monkeypatch, _entra):
    # Standard: samma som förut (access_as_user).
    await entra.verifiera(_token(), JWKS)
    monkeypatch.setattr(settings, "ENTRA_REQUIRED_SCOPE", "Plattform.Access")
    with pytest.raises(entra.EntraError, match="Plattform.Access"):
        await entra.verifiera(_token(), JWKS)
    await entra.verifiera(_token(scp="access_as_user Plattform.Access"), JWKS)


async def test_user_without_password_cannot_log_in_locally(client, sessions):
    r = await client.post("/api/v1/auth/users", headers=ADMIN,
                          json={"username": "bertil", "email": "bertil@example.org"})
    assert r.status_code == 201
    r = await client.post("/api/v1/auth/login", json={"username": "bertil", "password": "!entra"})
    assert r.status_code == 401


# ── 4. Engångskoden ──────────────────────────────────────────────────────────

async def test_setup_code_non_ascii(client, monkeypatch):
    """REGRESSION: en engångskod med å/ä/ö gav 500 (compare_digest på str)."""
    monkeypatch.setattr(settings, "SETUP_CODE", "kod")
    r = await client.post("/api/v1/auth/setup", json={"username": "admin", "password": "lösenordet",
                                                     "setup_code": "fel-kod-åäö"})
    assert r.status_code == 403
    monkeypatch.setattr(settings, "SETUP_CODE", "kåd")
    r = await client.post("/api/v1/auth/setup", json={"username": "admin", "password": "lösenordet",
                                                     "setup_code": "kåd"})
    assert r.status_code == 200


# ── 5. Hemligheter för läsare ────────────────────────────────────────────────

async def _koppling_och_flöde(sessions):
    async with sessions() as s:
        conn = ConnectionORM(id=uuid.uuid4(), name="k", connector_type="generic_rest",
                             config={"url": "https://api.example.org/x", "headers": {"X-Api-Key": "hemlig"},
                                     "api_token": "t0k3n", "Authorization": "Bearer abc", "data_path": "items"},
                             auth_type="none", status="active")
        flow = FlowORM(id=uuid.uuid4(), name="f", connection_id=conn.id, enabled=True,
                       post_exec_webhook_url="https://mottagare.example.org/hook/HEMLIG?key=abc")
        s.add(conn)
        await s.flush()
        s.add(flow)
        s.add(ExecutionLogORM(id=uuid.uuid4(), flow_id=flow.id, trigger_type="manual", status="error",
                              started_at=datetime.now(timezone.utc),
                              error_message="Client error for url https://u:p@api.example.org/x?api_key=hemlig "
                                            + "x" * 1000))
        await s.commit()
        return conn.id, flow.id


async def test_viewer_does_not_see_secrets(client, sessions):
    """REGRESSION: läsare såg huvuden, nycklar och webhookadressen i klartext."""
    conn_id, flow_id = await _koppling_och_flöde(sessions)
    u = await _användare(sessions, "läsare")
    läsare = _bärare(create_access_token(str(u.id), "läsare", "viewer"))

    k = (await client.get(f"/api/v1/connections/{conn_id}", headers=läsare)).json()
    assert k["config"]["headers"] == {"X-Api-Key": maskering.MASK}
    assert k["config"]["api_token"] == maskering.MASK
    assert k["config"]["Authorization"] == maskering.MASK
    assert k["config"]["url"] == "https://api.example.org/x"
    assert k["config"]["data_path"] == "items"
    lista = (await client.get("/api/v1/connections", headers=läsare)).json()
    assert "hemlig" not in str(lista)

    f = (await client.get(f"/api/v1/flows/{flow_id}", headers=läsare)).json()
    assert f["post_exec_webhook_url"] == "https://mottagare.example.org/…"
    assert "HEMLIG" not in str((await client.get("/api/v1/flows", headers=läsare)).json())

    e = (await client.get("/api/v1/executions", headers=läsare)).json()["executions"][0]
    assert "hemlig" not in e["error_message"] and "u:p" not in e["error_message"]
    assert len(e["error_message"]) <= maskering.FEL_MAX + 1

    # Administratören ser allt.
    k = (await client.get(f"/api/v1/connections/{conn_id}", headers=ADMIN)).json()
    assert k["config"]["headers"] == {"X-Api-Key": "hemlig"}
    f = (await client.get(f"/api/v1/flows/{flow_id}", headers=ADMIN)).json()
    assert f["post_exec_webhook_url"].endswith("?key=abc")
    e = (await client.get("/api/v1/executions", headers=ADMIN)).json()["executions"][0]
    assert "api_key=hemlig" in e["error_message"]


async def test_masked_values_not_saved(client, sessions):
    """En config med masken kvar skriver inte över det sparade värdet."""
    conn_id, flow_id = await _koppling_och_flöde(sessions)
    maskerad = maskering.maskera_config({"url": "https://api.example.org/x", "headers": {"X-Api-Key": "hemlig"},
                                         "api_token": "t0k3n", "Authorization": "Bearer abc",
                                         "data_path": "ny"})
    r = await client.put(f"/api/v1/connections/{conn_id}", headers=ADMIN, json={"config": maskerad})
    assert r.status_code == 200
    config = r.json()["config"]
    assert config["headers"] == {"X-Api-Key": "hemlig"}
    assert config["api_token"] == "t0k3n"
    assert config["data_path"] == "ny"
    r = await client.put(f"/api/v1/flows/{flow_id}", headers=ADMIN,
                         json={"post_exec_webhook_url": "https://mottagare.example.org/…"})
    assert r.json()["post_exec_webhook_url"].endswith("?key=abc")


def test_mask_helpers():
    assert maskering.maskera_url("not a url") == maskering.MASK
    assert maskering.maskera_url("http://h:8000/a?b") == "http://h:8000/…"
    assert maskering.känslig_nyckel("Client_Secret") and maskering.känslig_nyckel("PASSWORD")
    assert not maskering.känslig_nyckel("url")


# ── 6. Kroppsstorlek ─────────────────────────────────────────────────────────

async def test_body_too_large_by_content_length(client):
    """REGRESSION: formuläret lästes in innan storleken prövades."""
    r = await client.post("/api/v1/csv/preview", headers={**ADMIN, "Content-Length": str(MAX_BODY_BYTES + 1)},
                          content=b"x")
    assert r.status_code == 413


async def test_body_too_large_streamed():
    from app import kroppsgrans

    async def strömma():
        for _ in range(10):
            yield b"y" * 500

    from app.main import create_app
    import httpx
    # Middlewaren får gränsen när appen byggs, så den provas här med en liten.
    liten = kroppsgrans.Kroppsgräns(create_app(), max_bytes=1000)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=liten), base_url="http://t") as c:
        r = await c.post("/api/v1/auth/login", content=strömma(),
                         headers={"Content-Type": "application/json"})
        assert r.status_code == 413, r.text
        r = await c.post("/api/v1/auth/refresh", json={"refresh_token": "x"})
        assert r.status_code == 401


# ── 7. Inaktiverade flöden ───────────────────────────────────────────────────

async def test_disabled_flow_not_run_by_webhook(client, sessions):
    """REGRESSION: ett inaktiverat flöde kördes ändå via webhook och schema."""
    from app.models.webhook_endpoint import WebhookEndpointORM
    from app.services import flow_service
    flow_id = await _flöde(sessions, "csv")
    async with sessions() as s:
        (await s.get(FlowORM, flow_id)).enabled = False
        s.add(WebhookEndpointORM(id=uuid.uuid4(), flow_id=flow_id, path_token="tok", secret=None))
        await s.commit()
    assert (await client.post("/api/v1/webhooks/receive/tok", json={})).status_code == 409
    async with sessions() as s:
        with pytest.raises(flow_service.FlowDisabled):
            await flow_service.execute_flow(s, flow_id, trigger_type="schedule")
        # En administratör kan köra det för hand.
        körning = await flow_service.execute_flow(s, flow_id, trigger_type="manual")
        assert körning.status == "success"


# ── 8. Transformstegens gränser ──────────────────────────────────────────────

@pytest.mark.parametrize("mall", ["{namn:>100000}", "{namn:.5000}", "{namn:{bredd}}", "{namn.__class__}"])
def test_template_limits(mall):
    """REGRESSION: en mall med enorm bredd tog minne och tid."""
    with pytest.raises(TransformError):
        apply_operation([{"namn": "a", "bredd": "999999999"}], "add_column",
                        {"column": "x", "mode": "template", "template": mall})


def test_template_still_works():
    ut = apply_operation([{"namn": "a"}], "add_column", {"column": "x", "mode": "template", "template": "<{namn:>5}>"})
    assert ut[0]["x"] == "<    a>"


def test_regex_length_limited():
    lång = "a" * (transform_engine.MAX_REGEX_LÄNGD + 1)
    for steg, config in [("replace", {"field": "f", "find": lång, "use_regex": True}),
                         ("substring", {"field": "f", "regex": lång}),
                         ("filter", {"filters": [{"field": "f", "operator": "regex", "value": lång}]})]:
        with pytest.raises(TransformError):
            apply_operation([{"f": "abc"}], steg, config)
    assert apply_operation([{"f": "abc"}], "substring", {"field": "f", "regex": "b(c)"})[0]["f"] == "c"


async def test_transform_runs_in_thread(sessions, monkeypatch):
    """Stegen körs utanför händelseloopen."""
    import threading
    from app.services import flow_service
    huvudtråd = threading.get_ident()
    trådar = []

    def spion(records, steps):
        trådar.append(threading.get_ident())
        return records

    monkeypatch.setattr(flow_service, "apply_operations", spion)
    flow_id = await _flöde(sessions, "csv")
    async with sessions() as s:
        await flow_service.execute_flow(s, flow_id, trigger_type="manual")
    assert trådar and trådar[0] != huvudtråd


# ── 12. Standardlösenordet i DATABASE_URL ────────────────────────────────────

def test_default_database_password_is_weak():
    s = Settings(DATABASE_URL="postgresql+asyncpg://integration_user:integration_pass@db:5432/integration_db",
                 ENCRYPTION_KEY="k" * 32, ADMIN_API_KEY="k" * 32, JWT_SECRET="k" * 32)
    assert s.weak_secrets() == ["DATABASE_URL"]
    s = Settings(DATABASE_URL="postgresql://integration_user:" + "p" * 20 + "@db/integration_db",
                 ENCRYPTION_KEY="k" * 32, ADMIN_API_KEY="k" * 32, JWT_SECRET="k" * 32)
    assert s.weak_secrets() == []
