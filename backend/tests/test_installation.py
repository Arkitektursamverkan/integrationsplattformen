"""Entra-uppgifterna ur portalen (services/installation.py) – utan databas."""
import asyncio

import httpx
import pytest

from app.config import settings
from app.services import entra, installation

FÄLT = list(installation.FÄLT)

SVAR = {
    "portal_url": "https://portal.example.org",
    "arkitekten_url": None,
    "entra": {
        "tenant_id": "tenant-p",
        "client_id": "client-p",
        "api_scope": "api://client-p/access_as_user",
        "bootstrap_admin_emails": ["a@example.org", "b@example.org"],
    },
}


@pytest.fixture(autouse=True)
def _ren_miljö(monkeypatch):
    """Varje test börjar med tomma Entra-fält och okänd egen miljö."""
    for f in FÄLT:
        monkeypatch.setattr(settings, f, "")
    monkeypatch.setattr(settings, "PORTAL_URL", "")
    monkeypatch.setattr(settings, "PORTAL_INSTALLATION_SECRET", "")
    monkeypatch.setattr(settings, "POST_EXEC_WEBHOOK_SECRET", "")
    monkeypatch.setattr(installation, "_ur_miljön", None)


def _transport(svar_för):
    """MockTransport som svarar med svar_för(request) och sparar anropen."""
    anrop = []

    def handler(request: httpx.Request) -> httpx.Response:
        anrop.append(request)
        return svar_för(request)

    return httpx.MockTransport(handler), anrop


@pytest.mark.parametrize("rå,väntat", [
    ("portal-api-abc:10000", "http://portal-api-abc:10000/api/v1"),
    ("portal-api:8000/", "http://portal-api:8000/api/v1"),
    ("http://portal-api:8000/api/v1", "http://portal-api:8000/api/v1"),
    ("https://portal.example.org/api/v1/", "https://portal.example.org/api/v1"),
    ("https://portal.example.org", "https://portal.example.org/api/v1"),
    ("", None),
    ("ftp://portal:21", None),
    ("http://portal:8000/api/v1?x=1", None),
])
def test_api_adress(rå, väntat):
    assert installation.api_adress(rå) == väntat


async def test_hämtning_fyller_tomma_fält():
    transport, anrop = _transport(lambda r: httpx.Response(200, json=SVAR))
    settings.POST_EXEC_WEBHOOK_SECRET = "hemlig"
    svar = await installation.hämta("http://portal:8000/api/v1", transport)
    ändrade = installation.tillämpa(svar)

    assert sorted(ändrade) == sorted(FÄLT)
    assert settings.ENTRA_TENANT_ID == "tenant-p"
    assert settings.ENTRA_CLIENT_ID == "client-p"
    assert settings.ENTRA_API_SCOPE == "api://client-p/access_as_user"
    assert settings.BOOTSTRAP_ADMIN_EMAILS == "a@example.org,b@example.org"
    assert settings.bootstrap_admin_emails_list == ["a@example.org", "b@example.org"]
    # Läses vid anropet: Entra räknas nu som inställt.
    assert entra.konfigurerad()
    assert entra.scope() == "api://client-p/access_as_user"
    # Rätt adress och hemligheten (POST_EXEC_WEBHOOK_SECRET som reserv).
    assert str(anrop[0].url) == "http://portal:8000/api/v1/installation"
    assert anrop[0].headers["X-Installation-Secret"] == "hemlig"


async def test_egen_hemlighet_går_före_webhookens():
    transport, anrop = _transport(lambda r: httpx.Response(200, json=SVAR))
    settings.POST_EXEC_WEBHOOK_SECRET = "webhook"
    settings.PORTAL_INSTALLATION_SECRET = "egen"
    await installation.hämta("http://portal/api/v1", transport)
    assert anrop[0].headers["X-Installation-Secret"] == "egen"


async def test_miljöns_värden_vinner_även_vid_senare_hämtning():
    settings.ENTRA_TENANT_ID = "tenant-egen"
    settings.BOOTSTRAP_ADMIN_EMAILS = "egen@example.org"
    installation.tillämpa(SVAR)
    assert settings.ENTRA_TENANT_ID == "tenant-egen"
    assert settings.BOOTSTRAP_ADMIN_EMAILS == "egen@example.org"
    assert settings.ENTRA_CLIENT_ID == "client-p"

    # Portalen byter värden: portalens fält följer med, miljöns gör det inte –
    # fast settings nu har värden i alla fält.
    nytt = {"entra": {"tenant_id": "tenant-ny", "client_id": "client-ny", "api_scope": "",
                      "bootstrap_admin_emails": ["ny@example.org"]}}
    ändrade = installation.tillämpa(nytt)
    assert settings.ENTRA_TENANT_ID == "tenant-egen"
    assert settings.BOOTSTRAP_ADMIN_EMAILS == "egen@example.org"
    assert settings.ENTRA_CLIENT_ID == "client-ny"
    assert settings.ENTRA_API_SCOPE == ""
    assert sorted(ändrade) == ["ENTRA_API_SCOPE", "ENTRA_CLIENT_ID"]


async def test_entra_null_lämnar_tomt():
    assert installation.tillämpa({"portal_url": None, "arkitekten_url": None, "entra": None}) == []
    assert all(getattr(settings, f) == "" for f in FÄLT)
    assert not entra.konfigurerad()


async def test_entra_null_senare_tömmer_portalens_men_inte_miljöns():
    settings.ENTRA_API_SCOPE = "api://egen/scope"
    installation.tillämpa(SVAR)
    installation.tillämpa({"entra": None})
    assert settings.ENTRA_TENANT_ID == ""
    assert settings.ENTRA_CLIENT_ID == ""
    assert settings.ENTRA_API_SCOPE == "api://egen/scope"


async def test_felaktigt_svar_ändrar_inget():
    installation.tillämpa(SVAR)
    with pytest.raises(ValueError):
        installation.tillämpa({"entra": {"tenant_id": 5, "client_id": "x"}})
    assert settings.ENTRA_TENANT_ID == "tenant-p"
    assert settings.ENTRA_CLIENT_ID == "client-p"


@pytest.mark.parametrize("svar", [
    httpx.Response(401, json={"detail": "nej"}),
    httpx.Response(500),
    httpx.Response(302, headers={"Location": "http://annan.example.org/installation"}),
    httpx.Response(200, json=["inte", "ett", "objekt"]),
])
async def test_felsvar_ger_undantag(svar):
    transport, anrop = _transport(lambda r: svar)
    with pytest.raises((RuntimeError, TypeError)):
        await installation.hämta("http://portal/api/v1", transport)
    # En omdirigering följs inte.
    assert len(anrop) == 1


async def test_fel_och_timeout_ger_omförsök_utan_krasch(monkeypatch):
    försök = []

    def svar_för(request):
        försök.append(1)
        if len(försök) == 1:
            raise httpx.ConnectTimeout("timeout", request=request)
        if len(försök) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json=SVAR)

    transport, _ = _transport(svar_för)
    väntetider = []
    riktig_sleep = asyncio.sleep

    async def sov(s):
        väntetider.append(s)
        if len(väntetider) >= 4:
            raise asyncio.CancelledError
        await riktig_sleep(0)

    monkeypatch.setattr(installation.asyncio, "sleep", sov)
    settings.POST_EXEC_WEBHOOK_SECRET = "hemlig"
    with pytest.raises(asyncio.CancelledError):
        await installation.kör("http://portal/api/v1", transport, fel=10, ok=300)
    # Två misslyckanden (10 s), sedan lyckat (300 s) och nästa hämtning.
    assert väntetider[:3] == [10, 10, 300]
    assert settings.ENTRA_TENANT_ID == "tenant-p"


def test_starta_kräver_adress_och_hemlighet():
    assert installation.starta() is None
    settings.PORTAL_URL = "portal:8000"
    assert installation.starta() is None  # ingen hemlighet
    settings.PORTAL_URL = "ftp://portal"
    settings.POST_EXEC_WEBHOOK_SECRET = "hemlig"
    assert installation.starta() is None  # ogiltig adress


def test_starta_behövs_inte_när_miljön_har_allt():
    for f in FÄLT:
        setattr(settings, f, "x")
    settings.PORTAL_URL = "portal:8000"
    settings.POST_EXEC_WEBHOOK_SECRET = "hemlig"
    assert installation.starta() is None


async def test_starta_kör_i_bakgrunden(monkeypatch):
    settings.PORTAL_URL = "portal:8000"
    settings.POST_EXEC_WEBHOOK_SECRET = "hemlig"
    adresser = []

    async def kör(adress):
        adresser.append(adress)

    monkeypatch.setattr(installation, "kör", kör)
    uppgift = installation.starta()
    assert uppgift is not None
    await uppgift
    assert adresser == ["http://portal:8000/api/v1"]


async def test_jwks_cache_följer_tenanten(monkeypatch):
    hämtade = []

    async def hämta():
        hämtade.append(settings.ENTRA_TENANT_ID)
        return {"keys": [{"kid": settings.ENTRA_TENANT_ID}]}

    monkeypatch.setattr(entra, "_hämta", hämta)
    monkeypatch.setattr(entra, "_jwks", None)
    monkeypatch.setattr(entra, "_senast_tvingad", None)
    settings.ENTRA_TENANT_ID = "t1"
    assert (await entra._nycklar())["keys"][0]["kid"] == "t1"
    assert (await entra._nycklar())["keys"][0]["kid"] == "t1"
    settings.ENTRA_TENANT_ID = "t2"
    assert (await entra._nycklar())["keys"][0]["kid"] == "t2"
    assert hämtade == ["t1", "t2"]
