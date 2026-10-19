"""FastAPI dependency injection: database sessions and authentication."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.api_key import ApiKeyORM
from app.models.user import UserORM
from app.services.auth_service import decode_token

# Optional bearer token — doesn't auto-reject if missing
_bearer_scheme = HTTPBearer(auto_error=False)


# ── JWT authentication (for UI users) ────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
    db: AsyncSession = Depends(get_db),
) -> UserORM:
    """Extract and validate the JWT token, return the current user."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    result = await db.execute(select(UserORM).where(UserORM.id == user_id, UserORM.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def require_admin(user: UserORM = Depends(get_current_user)) -> UserORM:
    """Require the current user to have the admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# ── API key or JWT authentication (for management endpoints) ─────────────────

async def require_auth(
    x_api_key: Annotated[str | None, Header()] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
    db: AsyncSession = Depends(get_db),
) -> UserORM | None:
    """Accept either admin API key OR JWT token for management endpoints.

    This allows both the UI (JWT) and MCP server/scripts (API key) to work.
    """
    # Try admin API key first
    if x_api_key and x_api_key == settings.ADMIN_API_KEY:
        return None  # Admin key accepted, no user object

    # Try JWT token
    if credentials:
        try:
            payload = decode_token(credentials.credentials)
            if payload.get("type") != "access":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(select(UserORM).where(UserORM.id == user_id, UserORM.is_active.is_(True)))
                user = result.scalar_one_or_none()
                if user:
                    return user
        except JWTError:
            pass

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required (JWT token or X-Api-Key)")


async def require_admin_auth(
    x_api_key: Annotated[str | None, Header()] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
    db: AsyncSession = Depends(get_db),
) -> UserORM | None:
    """Require admin API key or admin-role JWT token."""
    # Admin API key
    if x_api_key and x_api_key == settings.ADMIN_API_KEY:
        return None

    # JWT with admin role
    if credentials:
        try:
            payload = decode_token(credentials.credentials)
            if payload.get("type") == "access" and payload.get("role") == "admin":
                user_id = payload.get("sub")
                if user_id:
                    result = await db.execute(select(UserORM).where(UserORM.id == user_id, UserORM.is_active.is_(True)))
                    user = result.scalar_one_or_none()
                    if user and user.role == "admin":
                        return user
        except JWTError:
            pass

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


# ── Consumer API key OR admin auth (for data endpoints) ──────────────────────

async def require_data_access(
    x_api_key: Annotated[str | None, Header()] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyORM | UserORM | None:
    """Accept admin API key, JWT token, or consumer API key for data endpoints."""
    # Admin API key
    if x_api_key and x_api_key == settings.ADMIN_API_KEY:
        return None

    # JWT token (any role can read data)
    if credentials:
        try:
            payload = decode_token(credentials.credentials)
            if payload.get("type") == "access":
                user_id = payload.get("sub")
                if user_id:
                    result = await db.execute(select(UserORM).where(UserORM.id == user_id, UserORM.is_active.is_(True)))
                    user = result.scalar_one_or_none()
                    if user:
                        return user
        except JWTError:
            pass

    # Consumer API key
    if x_api_key:
        prefix = x_api_key[:8]
        result = await db.execute(
            select(ApiKeyORM).where(ApiKeyORM.key_prefix == prefix, ApiKeyORM.enabled.is_(True))
        )
        api_key = result.scalar_one_or_none()
        if api_key and bcrypt.checkpw(x_api_key.encode(), api_key.key_hash.encode()):
            if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")
            return api_key

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


# ── Legacy aliases (for backwards compatibility during migration) ─────────────

require_admin_key = require_admin_auth
require_consumer_key = require_data_access
