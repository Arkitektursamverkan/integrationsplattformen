"""Webhook endpoints — CRUD management + incoming payload receiver."""
from __future__ import annotations

import hmac
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin_key
from app.models.webhook_endpoint import WebhookEndpointORM
from app.ratelimit import limiter
from app.schemas.webhook import WebhookEndpointCreate, WebhookEndpointRead

router = APIRouter()


# ── CRUD ─────────────────────────────────────────────────────────────────────


# The listing carries each endpoint's path token – admins only.
@router.get("", response_model=list[WebhookEndpointRead], dependencies=[Depends(require_admin_key)])
async def list_webhooks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookEndpointORM).order_by(WebhookEndpointORM.created_at.desc()))
    return result.scalars().all()


@router.get("/{webhook_id}", response_model=WebhookEndpointRead, dependencies=[Depends(require_admin_key)])
async def get_webhook(webhook_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookEndpointORM).where(WebhookEndpointORM.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@router.post("", response_model=WebhookEndpointRead, status_code=201, dependencies=[Depends(require_admin_key)])
async def create_webhook(body: WebhookEndpointCreate, db: AsyncSession = Depends(get_db)):
    webhook = WebhookEndpointORM(
        id=uuid.uuid4(),
        flow_id=body.flow_id,
        path_token=secrets.token_urlsafe(32),
        secret=body.secret,
        enabled=body.enabled,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)
    return webhook


@router.put("/{webhook_id}", response_model=WebhookEndpointRead, dependencies=[Depends(require_admin_key)])
async def update_webhook(
    webhook_id: uuid.UUID,
    body: WebhookEndpointCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WebhookEndpointORM).where(WebhookEndpointORM.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    webhook.flow_id = body.flow_id
    webhook.secret = body.secret
    webhook.enabled = body.enabled

    await db.commit()
    await db.refresh(webhook)
    return webhook


@router.delete("/{webhook_id}", status_code=204, dependencies=[Depends(require_admin_key)])
async def delete_webhook(webhook_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookEndpointORM).where(WebhookEndpointORM.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(webhook)
    await db.commit()


# ── Receiver ─────────────────────────────────────────────────────────────────


@router.post("/receive/{path_token}")
@limiter.limit("60/minute")
async def receive_webhook(
    path_token: str,
    request: Request,
    x_webhook_secret: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    # Look up webhook endpoint
    result = await db.execute(
        select(WebhookEndpointORM).where(
            WebhookEndpointORM.path_token == path_token,
            WebhookEndpointORM.enabled.is_(True),
        )
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    # An endpoint with a secret only answers callers that send it.
    if endpoint.secret and not hmac.compare_digest(
        (x_webhook_secret or "").encode(), endpoint.secret.encode()
    ):
        raise HTTPException(status_code=401, detail="Wrong or missing X-Webhook-Secret")

    # Parse payload
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode(errors="replace")}

    # Execute the associated flow
    from app.services.flow_service import execute_flow
    execution = await execute_flow(db, endpoint.flow_id, trigger_type="webhook")

    return {
        "status": execution.status,
        "execution_id": str(execution.id),
        "records_processed": execution.records_processed,
    }
