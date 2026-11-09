"""Top-level API router aggregation."""
from fastapi import APIRouter, Depends

from app.dependencies import require_auth
from app.api.v1 import connections, csv_upload, flows, schedules, executions, data, auth, webhooks, health, users

api_router = APIRouter(prefix="/api/v1")

# Management reads need a login (or the admin key); writes need an admin on top,
# per endpoint. Open on purpose: health, auth, data (its own consumer-key
# check) and the inbound webhook (its path token is the credential).
_inloggad = [Depends(require_auth)]

api_router.include_router(health.router, tags=["health"])
api_router.include_router(users.router, prefix="/auth", tags=["auth"])
api_router.include_router(connections.router, prefix="/connections", tags=["connections"], dependencies=_inloggad)
api_router.include_router(flows.router, prefix="/flows", tags=["flows"], dependencies=_inloggad)
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"], dependencies=_inloggad)
api_router.include_router(executions.router, prefix="/executions", tags=["executions"], dependencies=_inloggad)
api_router.include_router(data.router, prefix="/data", tags=["data"])
api_router.include_router(auth.router, prefix="/api-keys", tags=["api-keys"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(csv_upload.router, prefix="/csv", tags=["csv"])
