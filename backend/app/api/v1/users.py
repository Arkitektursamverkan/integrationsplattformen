"""Authentication and user management endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin_auth, get_current_user
from app.models.user import UserORM
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

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserORM).where(UserORM.username == body.username, UserORM.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

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
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"message": "Password updated"}


# ── Setup: create first admin user ────────────────────────────────────────────

@router.get("/setup")
async def setup_needed(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    """Whether the first admin still has to be created. Public, so the login
    page can send a fresh installation straight to the setup page."""
    count = (await db.execute(select(func.count(UserORM.id)))).scalar() or 0
    return {"needed": count == 0}


@router.post("/setup", response_model=TokenResponse)
async def initial_setup(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create the first admin user. Only works when no users exist."""
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
