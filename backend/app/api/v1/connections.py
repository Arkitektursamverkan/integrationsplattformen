"""CRUD endpoints for external system connections."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import get_connector_class, list_connector_types
from app.database import get_db
from app.dependencies import require_admin_key
from app.models.connection import ConnectionORM
from app.schemas.connection import ConnectionCreate, ConnectionRead, ConnectionUpdate
from app.services.crypto_service import decrypt_credentials, encrypt_credentials

router = APIRouter()


@router.get("", response_model=list[ConnectionRead])
async def list_connections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConnectionORM).order_by(ConnectionORM.created_at.desc()))
    return result.scalars().all()


@router.get("/types")
async def list_types():
    """List available connector types."""
    return {"connector_types": list_connector_types()}


@router.get("/{connection_id}", response_model=ConnectionRead)
async def get_connection(connection_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConnectionORM).where(ConnectionORM.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.post("", response_model=ConnectionRead, status_code=201, dependencies=[Depends(require_admin_key)])
async def create_connection(body: ConnectionCreate, db: AsyncSession = Depends(get_db)):
    encrypted = None
    if body.credentials:
        encrypted = encrypt_credentials(body.credentials)

    conn = ConnectionORM(
        id=uuid.uuid4(),
        name=body.name,
        connector_type=body.connector_type,
        description=body.description,
        config=body.config,
        credentials_encrypted=encrypted,
        auth_type=body.auth_type,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn


@router.put("/{connection_id}", response_model=ConnectionRead, dependencies=[Depends(require_admin_key)])
async def update_connection(
    connection_id: uuid.UUID, body: ConnectionUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ConnectionORM).where(ConnectionORM.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if body.name is not None:
        conn.name = body.name
    if body.description is not None:
        conn.description = body.description
    if body.config is not None:
        conn.config = body.config
    if body.credentials is not None and len(body.credentials) > 0:
        # Only update credentials if non-empty values were actually provided
        has_values = any(v for v in body.credentials.values() if v)
        if has_values:
            conn.credentials_encrypted = encrypt_credentials(body.credentials)
    if body.auth_type is not None:
        conn.auth_type = body.auth_type
    if body.status is not None:
        conn.status = body.status

    await db.commit()
    await db.refresh(conn)
    return conn


@router.delete("/{connection_id}", status_code=204, dependencies=[Depends(require_admin_key)])
async def delete_connection(connection_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConnectionORM).where(ConnectionORM.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()


@router.post("/{connection_id}/test", dependencies=[Depends(require_admin_key)])
async def test_connection(connection_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConnectionORM).where(ConnectionORM.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    credentials = {}
    if conn.credentials_encrypted:
        credentials = decrypt_credentials(conn.credentials_encrypted)

    from datetime import datetime, timezone
    try:
        connector_cls = get_connector_class(conn.connector_type)
        connector = connector_cls(connection_config=conn.config, credentials=credentials)
        ok = await connector.test_connection()
        conn.status = "active" if ok else "error"
        conn.last_tested_at = datetime.now(timezone.utc)
        await db.commit()
        return {"success": ok}
    except Exception as e:
        conn.status = "error"
        conn.last_tested_at = datetime.now(timezone.utc)
        await db.commit()
        return {"success": False, "error": str(e)}
