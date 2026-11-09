"""Arkitektens källa, skapad av plattformen själv vid starten.

En installation där Arkitekten körs bredvid plattformen (Render, compose) ska
inte behöva ett efterstartsskript för att koppla ihop dem. Med ARKITEKTEN_URL
satt skapar plattformen vid starten källan, flödet och schemat som hämtar
Arkitektens publicerade processbilder – en gång. Finns redan en källa av typen
arkitekten (skapad här, i gränssnittet eller av ett skript) görs ingenting, så
den som ändrat eller tagit bort schemat får behålla sin ändring.
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import ConnectionORM
from app.models.flow import FlowORM
from app.models.schedule import ScheduleORM

log = structlog.get_logger(__name__)

# Flödestjänstens port i Arkitekten (ARK_FLODESTJANST_PORT).
STANDARDPORT = 8200
CRON = "0 */2 * * *"


def bas_url(värde: str) -> str:
    """En full adress, eller bara värd / värd:port som Render ger internt.

    Utan port används flödestjänstens 8200 – inte webbens port, som Render
    anger för en webbtjänst."""
    v = värde.strip().rstrip("/")
    if not v:
        return ""
    if "://" not in v:
        v = "http://" + v
    värddel = v.split("://", 1)[1].split("/", 1)[0]
    if ":" not in värddel:
        schema, rest = v.split("://", 1)
        värd, _, väg = rest.partition("/")
        v = f"{schema}://{värd}:{STANDARDPORT}" + (f"/{väg}" if väg else "")
    return v


async def se_till_att_källan_finns(db: AsyncSession, värde: str) -> bool:
    """Skapar källa, flöde och schema om ingen arkitekten-källa finns. Sant om
    något skapades."""
    url = bas_url(värde)
    if not url:
        return False
    finns = await db.execute(
        select(ConnectionORM.id).where(ConnectionORM.connector_type == "arkitekten").limit(1)
    )
    if finns.scalar_one_or_none() is not None:
        return False

    källa = ConnectionORM(
        id=uuid.uuid4(),
        name="Arkitekten",
        connector_type="arkitekten",
        description="Publicerade processbilder från Arkitekten",
        config={"base_url": url, "familj": "alla", "endast_publicerade": True, "version": "fastslagen"},
        auth_type="none",
    )
    flöde = FlowORM(
        id=uuid.uuid4(),
        name="Arkitekten – processbilder till portalen",
        connection_id=källa.id,
        enabled=True,
    )
    schema = ScheduleORM(id=uuid.uuid4(), flow_id=flöde.id, cron_expression=CRON, enabled=True)
    db.add(källa)
    await db.flush()
    db.add(flöde)
    await db.flush()
    db.add(schema)
    await db.commit()
    log.info("arkitekten.kalla_skapad", base_url=url, cron=CRON)
    return True
