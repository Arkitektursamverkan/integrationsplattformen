"""Inloggning med Entra – samma app-registrering som portalen och Arkitekten.

Webben loggar in med MSAL och skickar sin Entra-åtkomsttoken hit en gång;
plattformen kontrollerar den och svarar med sina vanliga tokens. Resten av
plattformen ser ingen skillnad mellan ett Entra-konto och ett lokalt.

Vem som släpps in: ett konto som redan är kopplat till Entra-kontot (oid), ett
okopplat konto med samma e-post (det kopplas), eller en adress i BOOTSTRAP_ADMIN_EMAILS (blir administratör).
Övriga får nej – plattformen är ett verktyg för de som sköter integrationerna,
inte för hela organisationen.
"""
from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

import httpx
import structlog
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import UserORM
from app.services.auth_service import hash_password

log = structlog.get_logger(__name__)


class EntraError(Exception):
    """Token som inte godtas. Meddelandet visas för användaren."""


class EntraForbidden(EntraError):
    """Giltig token, men kontot får inte använda plattformen."""


def konfigurerad() -> bool:
    return bool(settings.ENTRA_TENANT_ID and settings.ENTRA_CLIENT_ID)


def scope() -> str:
    """Samma förval som portalens webb (40-ea-config.sh)."""
    return settings.ENTRA_API_SCOPE or f"api://{settings.ENTRA_CLIENT_ID}/access_as_user"


def _utgivare() -> set[str]:
    t = settings.ENTRA_TENANT_ID
    return {f"https://login.microsoftonline.com/{t}/v2.0", f"https://sts.windows.net/{t}/"}


def _mottagare() -> set[str]:
    c = settings.ENTRA_CLIENT_ID
    # v1-token har api://<id>, v2-token själva id:t.
    return {f"api://{c}", c}


_jwks: tuple[float, dict[str, Any]] | None = None
_JWKS_TTL = 3600.0
# En token med okänt kid tvingar fram en ny hämtning – högst så här ofta, så
# att påhittade kid inte kan få oss att fråga Microsoft vid varje anrop.
_TVINGAD_MINST = 60.0
_senast_tvingad: float | None = None


async def _hämta() -> dict[str, Any]:
    url = f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/discovery/v2.0/keys"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url)
        r.raise_for_status()
    return r.json()


async def _nycklar(tvinga: bool = False) -> dict[str, Any]:
    global _jwks, _senast_tvingad
    nu = time.monotonic()
    if _jwks and not tvinga and nu - _jwks[0] < _JWKS_TTL:
        return _jwks[1]
    if _jwks and tvinga and _senast_tvingad is not None and nu - _senast_tvingad < _TVINGAD_MINST:
        return _jwks[1]
    if tvinga:
        _senast_tvingad = nu
    _jwks = (nu, await _hämta())
    return _jwks[1]


async def verifiera(token: str, nycklar: dict[str, Any] | None = None) -> dict[str, Any]:
    """Claims ur en giltig Entra-åtkomsttoken till den här app-registreringen."""
    if not konfigurerad():
        raise EntraError("Entra är inte inställt i plattformen")
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except JWTError as e:
        raise EntraError(f"Felaktig token: {e}") from e
    jwks = nycklar or await _nycklar()
    nyckel = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if nyckel is None and nycklar is None:
        # Microsoft byter nycklar: hämta på nytt en gång innan vi ger upp.
        jwks = await _nycklar(tvinga=True)
        nyckel = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if nyckel is None:
        raise EntraError("Okänd signeringsnyckel")
    try:
        claims = jwt.decode(token, nyckel, algorithms=["RS256"], options={"verify_aud": False})
    except JWTError as e:
        raise EntraError(f"Ogiltig token: {e}") from e
    if claims.get("aud") not in _mottagare():
        raise EntraError("Token är inte utfärdad till den här appen")
    if claims.get("iss") not in _utgivare():
        raise EntraError("Token kommer från fel organisation")
    # Bara en åtkomsttoken till plattformens scope – inte en id-token, som har
    # samma mottagare och utgivare men inget scp.
    if _scopenamn() not in str(claims.get("scp", "")).split():
        raise EntraError("Token saknar behörigheten " + _scopenamn())
    return claims


def _scopenamn() -> str:
    """Sista delen av scope(), t.ex. access_as_user."""
    return scope().rstrip("/").rsplit("/", 1)[-1]


def _epost(claims: dict[str, Any]) -> str:
    # Inte claimet email: det kan sättas av användaren och är inte verifierat.
    return (claims.get("preferred_username") or claims.get("upn") or "").strip().lower()


async def användare(db: AsyncSession, claims: dict[str, Any]) -> UserORM:
    """Plattformens konto för en Entra-inloggning – kopplat, skapat eller nekat."""
    epost = _epost(claims)
    if not epost:
        raise EntraError("Token saknar e-postadress")
    oid = str(claims.get("oid") or "").strip()
    if not oid:
        raise EntraError("Token saknar oid")
    # Först kontot som redan är kopplat till det här Entra-kontot; annars ett
    # okopplat konto med samma e-post (det kopplas nu). Ett konto som redan är
    # kopplat till ett annat Entra-konto tas aldrig över via e-posten.
    rad = (await db.execute(
        select(UserORM).where(UserORM.entra_oid == oid).limit(1)
    )).scalar_one_or_none()
    if rad is None:
        rad = (await db.execute(
            select(UserORM)
            .where(func.lower(UserORM.email) == epost, UserORM.entra_oid.is_(None))
            .limit(1)
        )).scalar_one_or_none()
    är_admin = epost in settings.bootstrap_admin_emails_list
    if rad is None:
        if not är_admin:
            raise EntraForbidden(
                f"{epost} har inget konto i Integrationsplattformen. "
                "Be en administratör lägga till dig med den e-postadressen."
            )
        användarnamn = epost
        if (await db.execute(select(UserORM.id).where(UserORM.username == användarnamn))).first():
            användarnamn = f"{epost}-{secrets.token_hex(3)}"
        rad = UserORM(
            id=uuid.uuid4(), username=användarnamn, email=epost,
            # Inget användbart lösenord: kontot loggar in via Entra.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            full_name=claims.get("name"), role="admin", is_active=True, entra_oid=oid,
        )
        db.add(rad)
        log.info("entra.user_created", email=epost)
    else:
        if not rad.is_active:
            raise EntraForbidden("Kontot är avstängt i Integrationsplattformen")
        if rad.entra_oid is None:
            rad.entra_oid = oid
            log.info("entra.user_linked", user=rad.username)
        if är_admin and rad.role != "admin":
            rad.role = "admin"
        if claims.get("name") and not rad.full_name:
            rad.full_name = claims["name"]
    await db.commit()
    await db.refresh(rad)
    return rad
