"""CRUD endpoints for external system connections."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import natverk
from app.connectors.registry import get_connector_class, list_connector_types
from app.database import get_db
from app.dependencies import require_admin_key, require_auth
from app.models.connection import ConnectionORM
from app.schemas.connection import ConnectionCreate, ConnectionRead, ConnectionUpdate
from app.services.crypto_service import decrypt_credentials, encrypt_credentials
from app.services.maskering import maskera_config, återställ_maskerat, är_admin

router = APIRouter()


def _för(principal, conn: ConnectionORM) -> ConnectionRead:
    """Kopplingen som anroparen får se: huvuden och nycklar i config är dolda
    för alla utom administratörer."""
    läst = ConnectionRead.model_validate(conn)
    if är_admin(principal):
        return läst
    return läst.model_copy(update={"config": maskera_config(conn.config)})


@router.get("", response_model=list[ConnectionRead])
async def list_connections(db: AsyncSession = Depends(get_db), principal=Depends(require_auth)):
    result = await db.execute(select(ConnectionORM).order_by(ConnectionORM.created_at.desc()))
    return [_för(principal, c) for c in result.scalars().all()]


@router.get("/types")
async def list_types():
    """List available connector types."""
    return {"connector_types": list_connector_types()}


@router.get("/{connection_id}", response_model=ConnectionRead)
async def get_connection(
    connection_id: uuid.UUID, db: AsyncSession = Depends(get_db), principal=Depends(require_auth),
):
    result = await db.execute(select(ConnectionORM).where(ConnectionORM.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return _för(principal, conn)


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


# Där kopplingarna har sin adress (generic_rest: url, 2C8 och Arkitekten: base_url).
_ADRESSFÄLT = ("url", "base_url")


def _som_bool(värde: object, standard: bool = True) -> bool:
    if värde is None:
        return standard
    if isinstance(värde, str):
        return värde.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(värde)


def _mål(config: dict | None) -> tuple:
    """Vart uppgifterna skickas: adressernas ursprung och om certifikatet prövas."""
    config = config or {}
    return (
        tuple(natverk.ursprung(str(config.get(f) or "")) for f in _ADRESSFÄLT),
        _som_bool(config.get("verify_ssl")),
    )


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
    nya_uppgifter = bool(body.credentials) and any(v for v in body.credentials.values() if v)
    cleared = False
    if body.config is not None:
        # Ett dolt värde som skickas tillbaka oförändrat behåller det sparade.
        body.config = återställ_maskerat(body.config, conn.config or {})
        # Ny värd (eller schema/port) eller ändrad certifikatprövning: sparade
        # uppgifter skulle annars skickas till ett mål som inte är det de
        # angavs för. De töms och måste anges igen, om inte nya kommer nu.
        if conn.credentials_encrypted and not nya_uppgifter and _mål(body.config) != _mål(conn.config):
            conn.credentials_encrypted = None
            cleared = True
        conn.config = body.config
    if nya_uppgifter:
        # Only update credentials if non-empty values were actually provided
        conn.credentials_encrypted = encrypt_credentials(body.credentials)
    if body.auth_type is not None:
        conn.auth_type = body.auth_type
    if body.status is not None:
        conn.status = body.status

    await db.commit()
    await db.refresh(conn)
    return ConnectionRead.model_validate(conn).model_copy(update={"credentials_cleared": cleared})


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
        # Spärren mot interna adresser, med ett begripligt fel i stället för
        # bara "misslyckades" (kopplingarna kontrollerar själva också).
        mock = conn.connector_type == "2c8" and conn.config.get("mode", "mock") == "mock"
        for fält in _ADRESSFÄLT:
            if conn.config.get(fält) and not mock:
                await natverk.kontrollera_url(str(conn.config[fält]))
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
