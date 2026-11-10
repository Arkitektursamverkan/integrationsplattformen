"""Säkerhetsgranskningens tredje omgång: X-Forwarded-For, inloggningsspärr,
nycklarnas scopes, sparade uppgifter vid ny adress och SSRF-spärren."""
import uuid

import httpx
import pytest
from starlette.requests import Request

from app.api.v1 import users
from app.config import settings
from app.connectors import natverk
from app.connectors.registry import get_connector_class
from app.models.api_key import ApiKeyORM
from app.models.data_record import DataRecordORM
from app.ratelimit import client_address
from app.services import inloggningssparr
from app.services.auth_service import hash_password
from app.models.user import UserORM

from tests.test_sakerhet_2 import ADMIN, _flöde, client, sessions  # noqa: F401 (fixturer)


# ── X-Forwarded-For ──────────────────────────────────────────────────────────

def _anrop(*xff: str) -> Request:
    headers = [(b"x-forwarded-for", v.encode()) for v in xff]
    return Request({"type": "http", "headers": headers, "client": ("10.0.0.1", 1234)})


def test_forwarded_for_counts_from_the_right(monkeypatch):
    """REGRESSION: det första ledet, som anroparen själv kan skriva, avgjorde gränsen."""
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    # Anroparen skickar ett påhittat led; nginx lägger till den riktiga adressen.
    assert client_address(_anrop("6.6.6.6, 1.2.3.4")) == "1.2.3.4"
    assert client_address(_anrop("6.6.6.6", "1.2.3.4")) == "1.2.3.4"
    # Två proxyer (t.ex. plattformens proxy framför nginx).
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 2)
    assert client_address(_anrop("6.6.6.6, 1.2.3.4, 10.9.9.9")) == "1.2.3.4"
    # Färre led än proxyer: det yttersta.
    assert client_address(_anrop("1.2.3.4")) == "1.2.3.4"
    # Ett nonsensvärde i inställningen betyder en proxy.
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)
    assert client_address(_anrop("6.6.6.6, 1.2.3.4")) == "1.2.3.4"


def test_trusted_proxy_count_at_least_one():
    from app.config import Settings
    assert Settings(TRUSTED_PROXY_COUNT=0).TRUSTED_PROXY_COUNT == 1
    assert Settings(TRUSTED_PROXY_COUNT=3).TRUSTED_PROXY_COUNT == 3


# ── Inloggning ───────────────────────────────────────────────────────────────

async def _användare(sessions, namn: str, lösenord: str) -> None:
    async with sessions() as s:
        s.add(UserORM(id=uuid.uuid4(), username=namn, password_hash=hash_password(lösenord),
                      role="viewer", is_active=True))
        await s.commit()


async def _logga_in(client, namn, lösenord):
    return await client.post("/api/v1/auth/login", json={"username": namn, "password": lösenord})


async def test_login_locked_per_username(client, sessions, monkeypatch):
    """REGRESSION: gissning mot ett konto stoppades bara per adress."""
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 10)
    await _användare(sessions, "anna", "rätt-lösenord")
    await _användare(sessions, "bertil", "rätt-lösenord")
    for i in range(10):
        # Skiftläget spelar ingen roll för räkningen.
        r = await _logga_in(client, "anna" if i % 2 else "Anna", "fel")
        assert r.status_code == 401
    r = await _logga_in(client, "anna", "rätt-lösenord")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    # Andra konton påverkas inte.
    assert (await _logga_in(client, "bertil", "rätt-lösenord")).status_code == 200


async def test_login_lock_resets(client, sessions, monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 3)
    await _användare(sessions, "cecilia", "rätt-lösenord")
    for _ in range(2):
        assert (await _logga_in(client, "cecilia", "fel")).status_code == 401
    # En lyckad inloggning nollställer räknaren.
    assert (await _logga_in(client, "cecilia", "rätt-lösenord")).status_code == 200
    for _ in range(2):
        assert (await _logga_in(client, "cecilia", "fel")).status_code == 401
    assert (await _logga_in(client, "cecilia", "rätt-lösenord")).status_code == 200

    # Spärren släpper när försöken fallit ur fönstret.
    nu = [1000.0]
    monkeypatch.setattr(inloggningssparr.time, "monotonic", lambda: nu[0])
    for _ in range(3):
        assert (await _logga_in(client, "cecilia", "fel")).status_code == 401
    assert (await _logga_in(client, "cecilia", "rätt-lösenord")).status_code == 429
    nu[0] += settings.LOGIN_FAILURE_WINDOW_SECONDS + 1
    assert (await _logga_in(client, "cecilia", "rätt-lösenord")).status_code == 200


async def test_login_unknown_user_counts_too(client):
    for _ in range(settings.LOGIN_MAX_FAILURES):
        assert (await _logga_in(client, "finns-inte", "x")).status_code == 401
    assert (await _logga_in(client, "finns-inte", "x")).status_code == 429


async def test_password_check_runs_in_a_thread(client, sessions, monkeypatch):
    """REGRESSION: bcrypt i event-loopen höll alla andra anrop medan den räknade."""
    await _användare(sessions, "david", "rätt-lösenord")
    körda = []
    original = users.run_in_threadpool

    async def spion(func, *args):
        körda.append(func.__name__)
        return await original(func, *args)

    monkeypatch.setattr(users, "run_in_threadpool", spion)
    assert (await _logga_in(client, "david", "rätt-lösenord")).status_code == 200
    assert (await _logga_in(client, "finns-inte", "x")).status_code == 401
    assert körda == ["verify_password", "verify_password"]


# ── Nycklarnas scopes ────────────────────────────────────────────────────────

async def _nyckel(sessions, *scopes: str) -> dict:
    rå = "k" + uuid.uuid4().hex
    async with sessions() as s:
        s.add(ApiKeyORM(name="n", key_hash=hash_password(rå), key_prefix=rå[:8], scopes=list(scopes)))
        await s.commit()
    return {"X-Api-Key": rå}


async def _post(sessions, flow_id, external_id="1"):
    async with sessions() as s:
        s.add(DataRecordORM(id=uuid.uuid4(), flow_id=flow_id, source_type="rest_api", external_id=external_id,
                            data={"v": 1}, checksum="x", version=1))
        await s.commit()


async def test_data_read_scope_required(client, sessions):
    """REGRESSION: scopes sparades men verkställdes aldrig."""
    await _flöde(sessions, "rest_api")
    utan = await _nyckel(sessions)
    r = await client.get("/api/v1/data/sources", headers=utan)
    assert r.status_code == 403
    med = await _nyckel(sessions, "data:read")
    assert (await client.get("/api/v1/data/sources", headers=med)).status_code == 200
    # Ett flow:-scope utan data:read räcker inte.
    flow_id = await _flöde(sessions, "rest_api")
    bara_flöde = await _nyckel(sessions, f"flow:{flow_id}")
    assert (await client.get(f"/api/v1/data/{flow_id}/records", headers=bara_flöde)).status_code == 403


async def test_flow_scopes_limit_the_key(client, sessions):
    a = await _flöde(sessions, "rest_api")
    b = await _flöde(sessions, "rest_api")
    await _post(sessions, a)
    await _post(sessions, b)
    alla = await _nyckel(sessions, "data:read")
    bara_a = await _nyckel(sessions, "data:read", f"flow:{a}")

    r = await client.get("/api/v1/data/sources", headers=alla)
    assert {x["flow_id"] for x in r.json()} == {str(a), str(b)}
    r = await client.get("/api/v1/data/sources", headers=bara_a)
    assert [x["flow_id"] for x in r.json()] == [str(a)]

    vägar = ["records", "records/by-external/1", "changes?since=2000-01-01T00:00:00", "summary"]
    for väg in vägar:
        assert (await client.get(f"/api/v1/data/{a}/{väg}", headers=bara_a)).status_code == 200, väg
        assert (await client.get(f"/api/v1/data/{b}/{väg}", headers=bara_a)).status_code == 403, väg
        assert (await client.get(f"/api/v1/data/{b}/{väg}", headers=alla)).status_code == 200, väg
        # Administratörsnyckeln begränsas inte.
        assert (await client.get(f"/api/v1/data/{b}/{väg}", headers=ADMIN)).status_code == 200, väg


async def test_malformed_flow_scope_gives_no_flows(client, sessions):
    a = await _flöde(sessions, "rest_api")
    trasig = await _nyckel(sessions, "data:read", "flow:inte-ett-uuid")
    assert (await client.get("/api/v1/data/sources", headers=trasig)).json() == []
    assert (await client.get(f"/api/v1/data/{a}/records", headers=trasig)).status_code == 403


async def test_create_key_validates_scopes(client):
    flow_id = uuid.uuid4()
    r = await client.post("/api/v1/api-keys", json={"name": "a", "scopes": ["data:read", f"flow:{flow_id}"]},
                          headers=ADMIN)
    assert r.status_code == 201 and r.json()["scopes"] == ["data:read", f"flow:{flow_id}"]
    r = await client.post("/api/v1/api-keys", json={"name": "b"}, headers=ADMIN)
    assert r.status_code == 201 and r.json()["scopes"] == ["data:read"]
    for fel in (["admin"], ["flow:nej"], ["data:write"]):
        r = await client.post("/api/v1/api-keys", json={"name": "c", "scopes": fel}, headers=ADMIN)
        assert r.status_code == 422, fel


# ── Sparade uppgifter när adressen ändras ────────────────────────────────────

async def _koppling(client, config: dict) -> str:
    r = await client.post("/api/v1/connections", headers=ADMIN, json={
        "name": "k", "connector_type": "2c8", "config": config, "credentials": {"api_key": "hemlig"},
        "auth_type": "api_key",
    })
    assert r.status_code == 201 and r.json()["has_credentials"] is True
    return r.json()["id"]


async def _ändra(client, conn_id: str, **body):
    r = await client.put(f"/api/v1/connections/{conn_id}", headers=ADMIN, json=body)
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize("ny", [
    {"mode": "api", "base_url": "https://annan.example"},           # ny värd
    {"mode": "api", "base_url": "http://a.example"},                # nytt schema
    {"mode": "api", "base_url": "https://a.example:8443"},          # ny port
    {"mode": "api", "base_url": "https://a.example", "verify_ssl": False},  # certifikatet prövas inte
    {"mode": "api", "url": "https://a.example", "base_url": "https://a.example"},  # url tillkommer
])
async def test_credentials_cleared_on_new_target(client, ny):
    """REGRESSION: sparade uppgifter skickades till vilken ny adress som helst."""
    conn_id = await _koppling(client, {"mode": "api", "base_url": "https://a.example"})
    svar = await _ändra(client, conn_id, config=ny)
    assert svar["credentials_cleared"] is True and svar["has_credentials"] is False


async def test_credentials_kept_on_same_target(client):
    conn_id = await _koppling(client, {"mode": "api", "base_url": "https://a.example", "verify_ssl": True})
    svar = await _ändra(client, conn_id, config={"mode": "api", "base_url": "https://A.example:443/",
                                                  "verify_ssl": "true", "repository_id": "r"})
    assert svar["credentials_cleared"] is False and svar["has_credentials"] is True
    # Bara namnet ändras: config skickas inte alls.
    svar = await _ändra(client, conn_id, name="nytt namn")
    assert svar["credentials_cleared"] is False and svar["has_credentials"] is True


async def test_new_credentials_with_new_target(client):
    conn_id = await _koppling(client, {"mode": "api", "base_url": "https://a.example"})
    svar = await _ändra(client, conn_id, config={"mode": "api", "base_url": "https://b.example"},
                        credentials={"api_key": "ny"})
    assert svar["credentials_cleared"] is False and svar["has_credentials"] is True
    # Tomma värden räknas inte som nya uppgifter.
    svar = await _ändra(client, conn_id, config={"mode": "api", "base_url": "https://c.example"},
                        credentials={"api_key": ""})
    assert svar["credentials_cleared"] is True and svar["has_credentials"] is False


# ── SSRF ─────────────────────────────────────────────────────────────────────

_DNS = {
    "publik.example": {"93.184.216.34"},
    "intern.example": {"10.0.0.5"},
    "blandad.example": {"93.184.216.34", "10.0.0.5"},
    "x.intern.example": {"10.0.0.6"},
    "flodestjanst": {"172.18.0.4"},
    "arkitekten": {"172.18.0.5"},
}


@pytest.fixture
def spärr(monkeypatch):
    import ipaddress

    async def slå_upp(värd, port):
        try:
            return {ipaddress.ip_address(värd)}
        except ValueError:
            pass
        if värd not in _DNS:
            raise natverk.SpärradAdress(f"{värd} kan inte slås upp")
        return {ipaddress.ip_address(a) for a in _DNS[värd]}

    monkeypatch.setattr(natverk, "_slå_upp", slå_upp)
    monkeypatch.setattr(settings, "CONNECTOR_BLOCK_INTERNAL", "true")
    monkeypatch.setattr(settings, "CONNECTOR_ALLOWED_HOSTS", "")
    monkeypatch.setattr(settings, "ARKITEKTEN_URL", "")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://127.1.2.3:8000/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.1.2.3/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://100.64.0.1/",
    "http://0.0.0.0/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[fe80::1]/",
    "http://[fd00::1]/",
    "http://224.0.0.1/",
    "http://240.0.0.1/",
    "http://intern.example/",
    "http://blandad.example/",          # en intern adress räcker
    "http://okänd.example/",           # kan inte slås upp
    "ftp://publik.example/",
    "file:///etc/passwd",
])
async def test_internal_targets_blocked(spärr, url):
    """REGRESSION: en koppling kunde anropa metadatatjänsten och interna tjänster."""
    with pytest.raises(natverk.SpärradAdress):
        await natverk.kontrollera_url(url)


async def test_public_targets_allowed(spärr):
    await natverk.kontrollera_url("https://publik.example/api")
    await natverk.kontrollera_url("http://93.184.216.34:8080/")


async def test_allowed_hosts(spärr, monkeypatch):
    monkeypatch.setattr(settings, "CONNECTOR_ALLOWED_HOSTS", "arkitekten, *.intern.example, 10.20.0.0/16, 10.0.0.5")
    await natverk.kontrollera_url("http://arkitekten:8200/")
    await natverk.kontrollera_url("http://ARKITEKTEN:8200/")
    await natverk.kontrollera_url("http://x.intern.example/")
    await natverk.kontrollera_url("http://10.20.1.1/")
    await natverk.kontrollera_url("http://intern.example/")  # 10.0.0.5 står i listan
    with pytest.raises(natverk.SpärradAdress):
        await natverk.kontrollera_url("http://10.21.1.1/")
    with pytest.raises(natverk.SpärradAdress):
        await natverk.kontrollera_url("http://127.0.0.1/")


async def test_arkitekten_url_always_allowed(spärr, monkeypatch):
    monkeypatch.setattr(settings, "ARKITEKTEN_URL", "flodestjanst")
    await natverk.kontrollera_url("http://flodestjanst:8200/api/flows")
    with pytest.raises(natverk.SpärradAdress):
        await natverk.kontrollera_url("http://arkitekten:8200/")


def test_block_on_in_production_by_default(monkeypatch):
    monkeypatch.setattr(settings, "CONNECTOR_BLOCK_INTERNAL", "auto")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert natverk.spärr_på() is True
    monkeypatch.setattr(settings, "APP_ENV", "development")
    assert natverk.spärr_på() is False
    monkeypatch.setattr(settings, "CONNECTOR_BLOCK_INTERNAL", "true")
    assert natverk.spärr_på() is True
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "CONNECTOR_BLOCK_INTERNAL", "false")
    assert natverk.spärr_på() is False


async def test_client_checks_each_request_and_does_not_follow_redirects(spärr):
    sedda: list[str] = []

    def svar(request: httpx.Request) -> httpx.Response:
        sedda.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/"})

    async with natverk.klient(transport=httpx.MockTransport(svar), follow_redirects=True) as c:
        with pytest.raises(natverk.SpärradAdress):
            await c.get("http://127.0.0.1/")
        assert sedda == []
        r = await c.get("https://publik.example/")
        assert r.status_code == 302
        assert sedda == ["https://publik.example/"]
        # Omdirigeringen följs inte – och skulle stoppas av kroken om den gjorde det.
        with pytest.raises(natverk.SpärradAdress):
            await c.get(r.headers["Location"])
    assert sedda == ["https://publik.example/"]


@pytest.mark.parametrize("typ,config", [
    ("generic_rest", {"url": "http://169.254.169.254/latest/meta-data/"}),
    ("2c8", {"mode": "api", "base_url": "http://127.0.0.1:9", "repository_id": "r"}),
    ("arkitekten", {"base_url": "http://10.0.0.5:8200"}),
])
async def test_connectors_refuse_internal_targets(spärr, typ, config):
    connector = get_connector_class(typ)(connection_config=config, credentials={})
    with pytest.raises(natverk.SpärradAdress):
        await connector.fetch()
    assert await connector.test_connection() is False


async def test_test_endpoint_reports_blocked_target(client, spärr):
    r = await client.post("/api/v1/connections", headers=ADMIN, json={
        "name": "k", "connector_type": "generic_rest", "config": {"url": "http://169.254.169.254/latest/"},
    })
    r = await client.post(f"/api/v1/connections/{r.json()['id']}/test", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["success"] is False and "intern" in r.json()["error"]
