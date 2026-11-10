"""Entra-uppgifterna ur Arkitekturportalen (Render-automatiken).

Med PORTAL_URL och en hemlighet hämtar plattformen portalens
GET /installation i bakgrunden – var 10:e sekund tills det lyckas, sedan var
5:e minut – och fyller ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_API_SCOPE och
BOOTSTRAP_ADMIN_EMAILS i det delade settings-objektet.

Egna miljövariabler vinner alltid: de fält som hade ett värde när uppgiften
startade rörs aldrig. Övriga fält följer portalen – en senare hämtning kan
ändra dem, och entra=null tömmer dem. Allt som använder fälten
(services/entra.py, /auth/config, /auth/setup) läser settings vid anropet.
"""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

# Fältet i settings → nyckeln i svarets "entra".
FÄLT: dict[str, str] = {
    "ENTRA_TENANT_ID": "tenant_id",
    "ENTRA_CLIENT_ID": "client_id",
    "ENTRA_API_SCOPE": "api_scope",
    "BOOTSTRAP_ADMIN_EMAILS": "bootstrap_admin_emails",
}

INTERVALL_FEL = 10.0
INTERVALL_OK = 300.0
_TIMEOUT = httpx.Timeout(10.0)

# Fälten som hade ett eget värde i miljön när uppgiften startade.
_ur_miljön: frozenset[str] | None = None


def ur_miljön() -> frozenset[str]:
    """De Entra-fält som kom ur plattformens egen miljö. Bestäms en gång, före
    första hämtningen – därefter kan settings innehålla portalens värden."""
    global _ur_miljön
    if _ur_miljön is None:
        _ur_miljön = frozenset(f for f in FÄLT if str(getattr(settings, f) or "").strip())
    return _ur_miljön


def api_adress(raw: str) -> str | None:
    """Portalens API-adress ur PORTAL_URL. värd:port (Render hostport) blir
    http://värd:port/api/v1; en adress utan sökväg får /api/v1. None = ogiltig."""
    v = (raw or "").strip().rstrip("/")
    if not v:
        return None
    if "://" not in v:
        v = "http://" + v
    try:
        delar = urlsplit(v)
    except ValueError:
        return None
    if delar.scheme not in ("http", "https") or not delar.hostname or delar.query or delar.fragment:
        return None
    if not delar.path:
        v += "/api/v1"
    return v


def hemlighet() -> str:
    return settings.PORTAL_INSTALLATION_SECRET or settings.POST_EXEC_WEBHOOK_SECRET


async def hämta(adress: str, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    """Portalens svar på GET /installation. Fel och oväntade svar ger undantag.

    Adressen är installatörens, men en omdirigering följs ändå inte –
    hemligheten ska bara till den adress som är inställd."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False, transport=transport) as c:
        r = await c.get(
            f"{adress}/installation",
            headers={"X-Installation-Secret": hemlighet(), "Accept": "application/json"},
        )
    if r.status_code != 200:
        raise RuntimeError(f"portalen svarade {r.status_code}")
    svar = r.json()
    if not isinstance(svar, dict):
        raise TypeError("portalens svar är inte ett objekt")
    return svar


def _värde(rå: Any) -> str:
    if rå is None:
        return ""
    if isinstance(rå, list):
        return ",".join(str(e).strip() for e in rå if isinstance(e, str) and e.strip())
    if isinstance(rå, str):
        return rå.strip()
    raise ValueError("oväntad typ i portalens entra")


def tillämpa(svar: dict[str, Any]) -> list[str]:
    """Fyll de fält som inte kom ur miljön med portalens värden. Returnerar
    namnen på de fält som ändrades."""
    entra = svar.get("entra")
    if entra is not None and not isinstance(entra, dict):
        raise ValueError("portalens entra är varken null eller ett objekt")
    # Läs alla värden först, så att ett felaktigt svar inte ändrar något.
    nya = {fält: _värde((entra or {}).get(nyckel)) for fält, nyckel in FÄLT.items()}
    egna = ur_miljön()
    ändrade = []
    for fält, värde in nya.items():
        if fält in egna:
            continue
        if getattr(settings, fält) != värde:
            setattr(settings, fält, värde)
            ändrade.append(fält)
    return ändrade


async def kör(adress: str, transport: httpx.AsyncBaseTransport | None = None,
              fel: float = INTERVALL_FEL, ok: float = INTERVALL_OK) -> None:
    """Hämta tills uppgiften avbryts. Ett fel stoppar aldrig plattformen."""
    lyckats = False
    while True:
        try:
            svar = await hämta(adress, transport)
            ändrade = tillämpa(svar)
            if ändrade or not lyckats:
                # Bara fältnamn – aldrig värden (e-postadresser) eller hemligheten.
                log.info("portal.installation_hamtad", entra=svar.get("entra") is not None,
                         andrade=ändrade, egna=sorted(ur_miljön()))
            lyckats = True
            vänta = ok
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 – en portal som inte svarar får inte stoppa plattformen
            vänta = fel if not lyckats else ok
            log.warning("portal.installation_misslyckades", adress=adress,
                        error=f"{type(e).__name__}: {e}", nytt_forsok_s=vänta)
        await asyncio.sleep(vänta)


def starta() -> asyncio.Task[None] | None:
    """Starta hämtningen i bakgrunden, om PORTAL_URL är satt. None = ingen."""
    if not settings.PORTAL_URL.strip():
        return None
    adress = api_adress(settings.PORTAL_URL)
    if adress is None:
        log.warning("portal.url_ogiltig", note="PORTAL_URL ska vara http(s)://värd[:port][/sökväg] eller värd:port")
        return None
    if not hemlighet():
        log.warning("portal.hemlighet_saknas",
                    note="PORTAL_INSTALLATION_SECRET och POST_EXEC_WEBHOOK_SECRET är tomma – inget hämtas")
        return None
    egna = ur_miljön()
    if egna == set(FÄLT):
        log.info("portal.installation_behovs_inte", note="alla Entra-fält är satta i miljön")
        return None
    return asyncio.create_task(kör(adress), name="portal-installation")
