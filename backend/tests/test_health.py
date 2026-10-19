"""The health endpoint reports the running version."""
from app.api.v1.health import health_check
from app.config import settings


async def test_health_reports_version(monkeypatch):
    monkeypatch.setattr(settings, "APP_VERSION", "1.2.3")
    assert await health_check() == {"status": "ok", "service": "integration-platform", "version": "1.2.3"}
