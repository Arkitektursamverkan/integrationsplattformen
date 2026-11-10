"""Authentication and user management endpoints."""
from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services import entra, inloggningssparr
from app.dependencies import require_admin_auth, get_current_user
from app.models.user import UserORM
from app.ratelimit import limiter
from app.services.auth_service import (
    hash_password, verify_password, create_access_token, create_refresh_token, decode_token,
)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    username: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    email: str | None = None
    full_name: str | None = None
    role: str = Field(default="viewer")


class UserResponse(BaseModel):
    id: str
    username: str
    email: str | None
    full_name: str | None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_manual(cls, user: UserORM) -> "UserResponse":
        return cls(id=str(user.id), username=user.username, email=user.email,
                   full_name=user.full_name, role=user.role, is_active=user.is_active)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


# ── Auth endpoints ────────────────────────────────────────────────────────────

# Password guessing: a few attempts a minute per client.
_LOGIN_LIMIT = "10/minute"

# Jämförs när användaren inte finns, så att svaret tar lika lång tid och inte
# avslöjar vilka namn som finns.
_ATTRAPP_HASH = hash_password("ingen-användare")


@router.post("/login", response_model=TokenResponse)
@limiter.limit(_LOGIN_LIMIT)
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Spärr per användarnamn, utöver gränsen per adress: gissning mot ett
    # konto från många adresser.
    kvar = inloggningssparr.spärrad_i(body.username)
    if kvar:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed logins for this user – try again later",
            headers={"Retry-After": str(kvar)},
        )
    result = await db.execute(
        select(UserORM).where(UserORM.username == body.username, UserORM.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    # bcrypt tar en kvarts sekund: i en tråd, så att andra anrop inte väntar.
    ok = await run_in_threadpool(verify_password, body.password, user.password_hash if user else _ATTRAPP_HASH)
    if not user or not ok:
        inloggningssparr.misslyckades(body.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    inloggningssparr.lyckades(body.username)

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.username, user.role),
        refresh_token=create_refresh_token(str(user.id)),
        role=user.role,
        username=user.username,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: dict, db: AsyncSession = Depends(get_db)):
    token = body.get("refresh_token", "")
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(UserORM).where(UserORM.id == user_id, UserORM.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.username, user.role),
        refresh_token=create_refresh_token(str(user.id)),
        role=user.role,
        username=user.username,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: UserORM = Depends(get_current_user)):
    return UserResponse.from_orm_manual(user)


@router.put("/me/password")
async def change_password(body: ChangePasswordRequest, user: UserORM = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not await run_in_threadpool(verify_password, body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = await run_in_threadpool(hash_password, body.new_password)
    await db.commit()
    return {"message": "Password updated"}


# ── Setup: create first admin user ────────────────────────────────────────────

def _setup_closed_for_entra() -> bool:
    """With Entra and BOOTSTRAP_ADMIN_EMAILS the first admin is whoever of those
    signs in with Microsoft – the setup form is not needed, so it is closed."""
    return entra.konfigurerad() and bool(settings.bootstrap_admin_emails_list)


@router.get("/setup")
async def setup_needed(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    """Whether the first admin still has to be created, and whether that takes
    the one-time code. Public, so the login page can send a fresh installation
    straight to the setup page."""
    if _setup_closed_for_entra():
        return {"needed": False, "code_required": False}
    count = (await db.execute(select(func.count(UserORM.id)))).scalar() or 0
    return {"needed": count == 0, "code_required": settings.setup_code_required()}


# ── Entra ─────────────────────────────────────────────────────────────────────

@router.get("/config")
async def auth_config() -> dict:
    """Public: what the login page should offer."""
    if not entra.konfigurerad():
        return {"entra": None}
    return {"entra": {"tenant_id": settings.ENTRA_TENANT_ID,
                      "client_id": settings.ENTRA_CLIENT_ID,
                      "scope": entra.scope()}}


class EntraLoginRequest(BaseModel):
    access_token: str


@router.post("/entra", response_model=TokenResponse)
@limiter.limit(_LOGIN_LIMIT)
async def login_entra(request: Request, body: EntraLoginRequest, db: AsyncSession = Depends(get_db)):
    """Exchange an Entra access token for the platform's own tokens."""
    try:
        claims = await entra.verifiera(body.access_token)
        user = await entra.användare(db, claims)
    except entra.EntraForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    except entra.EntraError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.username, user.role),
        refresh_token=create_refresh_token(str(user.id)),
        role=user.role,
        username=user.username,
    )


class SetupRequest(RegisterRequest):
    setup_code: str | None = None


@router.post("/setup", response_model=TokenResponse)
@limiter.limit(_LOGIN_LIMIT)
async def initial_setup(request: Request, body: SetupRequest, db: AsyncSession = Depends(get_db)):
    """Create the first admin user. Only works when no users exist, and – in
    production – with the installation's one-time SETUP_CODE."""
    if _setup_closed_for_entra():
        raise HTTPException(status_code=403, detail="Log in with Microsoft – the first admin comes from BOOTSTRAP_ADMIN_EMAILS.")
    if settings.setup_code_required():
        if not settings.SETUP_CODE:
            raise HTTPException(status_code=403, detail="SETUP_CODE is not set – the first admin cannot be created without it.")
        if not hmac.compare_digest((body.setup_code or "").strip(), settings.SETUP_CODE):
            raise HTTPException(status_code=403, detail="Wrong setup code.")
    count = (await db.execute(select(func.count(UserORM.id)))).scalar() or 0
    if count > 0:
        raise HTTPException(status_code=400, detail="Setup already completed. Users exist.")

    user = UserORM(
        id=uuid.uuid4(),
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.username, user.role),
        refresh_token=create_refresh_token(str(user.id)),
        role=user.role,
        username=user.username,
    )


# ── User management (admin only) ─────────────────────────────────────────────

@router.get("/users", response_model=list[UserResponse], dependencies=[Depends(require_admin_auth)])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserORM).order_by(UserORM.created_at))
    return [UserResponse.from_orm_manual(u) for u in result.scalars().all()]


@router.post("/users", response_model=UserResponse, status_code=201, dependencies=[Depends(require_admin_auth)])
async def create_user(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(UserORM).where(UserORM.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = UserORM(
        id=uuid.uuid4(),
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return UserResponse.from_orm_manual(user)


@router.delete("/users/{user_id}", status_code=204, dependencies=[Depends(require_admin_auth)])
async def delete_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserORM).where(UserORM.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
