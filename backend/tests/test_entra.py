"""Entra-inloggningen: vilka token som godtas och vilka konton som släpps in."""
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.user import UserORM
from app.services import entra

TENANT, CLIENT = "tenant-1", "client-1"
_privat = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_pem = _privat.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
)
_publik = jwk.construct(_pem, "RS256").public_key().to_dict()
JWKS = {"keys": [{**_publik, "kid": "k1", "use": "sig"}]}


def _token(**ändra) -> str:
    claims = {"aud": f"api://{CLIENT}", "iss": f"https://sts.windows.net/{TENANT}/",
              "exp": int(time.time()) + 600, "preferred_username": "Anna@Example.org", "name": "Anna",
              "oid": "oid-anna", "scp": "access_as_user"}
    claims.update(ändra)
    return jwt.encode(claims, _pem, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture(autouse=True)
def _entra(monkeypatch):
    monkeypatch.setattr(settings, "ENTRA_TENANT_ID", TENANT)
    monkeypatch.setattr(settings, "ENTRA_CLIENT_ID", CLIENT)
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_EMAILS", "anna@example.org")


async def test_valid_token():
    claims = await entra.verifiera(_token(), JWKS)
    assert claims["name"] == "Anna"


async def test_v2_audience_accepted():
    await entra.verifiera(_token(aud=CLIENT, iss=f"https://login.microsoftonline.com/{TENANT}/v2.0"), JWKS)


@pytest.mark.parametrize("ändra", [
    {"aud": "api://annan-app"},
    {"iss": "https://sts.windows.net/annan-tenant/"},
    {"exp": int(time.time()) - 10},
    {"scp": None},  # id-token: samma aud och iss, men inget scp
    {"scp": "User.Read"},
])
async def test_rejected(ändra):
    with pytest.raises(entra.EntraError):
        await entra.verifiera(_token(**ändra), JWKS)


@pytest.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/u.db")
    async with engine.begin() as c:
        await c.run_sync(UserORM.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_bootstrap_address_becomes_admin(db):
    u = await entra.användare(db, {"preferred_username": "Anna@Example.org", "name": "Anna", "oid": "oid-anna"})
    assert (u.username, u.email, u.role, u.entra_oid) == ("anna@example.org", "anna@example.org", "admin", "oid-anna")
    # Andra gången: samma konto.
    assert (await entra.användare(db, {"preferred_username": "anna@example.org", "oid": "oid-anna"})).id == u.id


async def test_unknown_address_refused(db):
    with pytest.raises(entra.EntraForbidden):
        await entra.användare(db, {"preferred_username": "okand@example.org", "oid": "oid-x"})


async def test_existing_account_linked_by_email(db):
    db.add(UserORM(username="bertil", email="Bertil@example.org", password_hash="x", role="viewer"))
    await db.commit()
    u = await entra.användare(db, {"preferred_username": "bertil@example.org", "oid": "oid-bertil"})
    assert (u.username, u.role, u.entra_oid) == ("bertil", "viewer", "oid-bertil")
    # Kopplat: hittas på oid även när e-posten i Entra har bytts.
    assert (await entra.användare(db, {"preferred_username": "b@example.org", "oid": "oid-bertil"})).id == u.id


async def test_linked_account_not_taken_over_by_email(db):
    db.add(UserORM(username="bertil", email="bertil@example.org", password_hash="x",
                   role="viewer", entra_oid="oid-bertil"))
    await db.commit()
    with pytest.raises(entra.EntraForbidden):
        await entra.användare(db, {"preferred_username": "bertil@example.org", "oid": "oid-annan"})


async def test_unverified_email_claim_ignored(db):
    db.add(UserORM(username="bertil", email="bertil@example.org", password_hash="x", role="admin"))
    await db.commit()
    with pytest.raises(entra.EntraError):
        await entra.användare(db, {"email": "bertil@example.org", "oid": "oid-x"})


async def test_token_without_oid_refused(db):
    with pytest.raises(entra.EntraError):
        await entra.användare(db, {"preferred_username": "anna@example.org"})


async def test_unknown_kid_refetches_at_most_once_a_minute(monkeypatch):
    hämtningar = []

    async def hämta():
        hämtningar.append(1)
        return {"keys": []}

    monkeypatch.setattr(entra, "_hämta", hämta)
    monkeypatch.setattr(entra, "_jwks", None)
    monkeypatch.setattr(entra, "_senast_tvingad", None)
    for _ in range(3):
        with pytest.raises(entra.EntraError):
            await entra.verifiera(_token())
    # Första anropet: hämtning + en tvingad. Sedan bara cachen.
    assert len(hämtningar) == 2
