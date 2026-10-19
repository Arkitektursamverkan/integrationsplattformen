"""Top-level API router aggregation."""
from fastapi import APIRouter

from app.api.v1 import connections, csv_upload, flows, schedules, executions, data, auth, webhooks, health, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(users.router, prefix="/auth", tags=["auth"])
api_router.include_router(connections.router, prefix="/connections", tags=["connections"])
api_router.include_router(flows.router, prefix="/flows", tags=["flows"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(executions.router, prefix="/executions", tags=["executions"])
api_router.include_router(data.router, prefix="/data", tags=["data"])
api_router.include_router(auth.router, prefix="/api-keys", tags=["api-keys"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(csv_upload.router, prefix="/csv", tags=["csv"])
