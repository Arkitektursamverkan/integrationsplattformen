"""API key management endpoints."""
from __future__ import annotations

import secrets
import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin_key
from app.models.api_key import ApiKeyORM
from app.schemas.auth import ApiKeyCreate, ApiKeyCreated, ApiKeyRead

router = APIRouter()


@router.get("", response_model=list[ApiKeyRead], dependencies=[Depends(require_admin_key)])
async def list_api_keys(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApiKeyORM).order_by(ApiKeyORM.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=ApiKeyCreated, status_code=201, dependencies=[Depends(require_admin_key)])
async def create_api_key(body: ApiKeyCreate, db: AsyncSession = Depends(get_db)):
    # Generate a random API key
    raw_key = secrets.token_urlsafe(32)
    prefix = raw_key[:8]
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    api_key = ApiKeyORM(
        id=uuid.uuid4(),
        name=body.name,
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    db.add(api_key)
    await db.commit()

    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=prefix,
        scopes=api_key.scopes,
    )


@router.delete("/{key_id}", status_code=204, dependencies=[Depends(require_admin_key)])
async def delete_api_key(key_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApiKeyORM).where(ApiKeyORM.id == key_id))
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(api_key)
    await db.commit()
