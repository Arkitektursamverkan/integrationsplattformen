"""Application configuration loaded from environment variables."""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Values that have shipped as defaults in this repository at some point.
_PLACEHOLDER_SECRETS = {
    "",
    "dev-encryption-key-change-in-production",
    "dev-admin-key",
    "dev-jwt-secret-change-in-production",
    "change-me-in-production",
    "change-me-to-a-32-byte-base64-key",
}


def asyncpg_url(raw: str) -> str:
    """A PostgreSQL URL in the form SQLAlchemy's asyncpg driver needs.

    Managed databases (Render, Heroku and others) hand out ``postgres://`` or
    ``postgresql://``; asyncpg also spells TLS ``ssl=`` where libpq says
    ``sslmode=``. Anything else is left untouched."""
    value = raw.strip()
    for prefix in ("postgres://", "postgresql://"):
        if value.startswith(prefix):
            value = "postgresql+asyncpg://" + value[len(prefix):]
            break
    if value.startswith("postgresql+asyncpg://") and "sslmode=" in value:
        value = value.replace("sslmode=", "ssl=")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://integration_user:integration_pass@localhost:5433/integration_db"

    @field_validator("DATABASE_URL")
    @classmethod
    def normalise_database_url(cls, v: str) -> str:
        # A managed database's own connection string works as it is given.
        return asyncpg_url(v)

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6380/0"

    # ── Security ─────────────────────────────────────────────────────────────
    ENCRYPTION_KEY: str = "dev-encryption-key-change-in-production"
    ADMIN_API_KEY: str = "dev-admin-key"
    JWT_SECRET: str = "dev-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3100,http://localhost:5174"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ── App ──────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "info"
    # Set in the image at release (Dockerfile ARG); "dev" when built locally.
    APP_VERSION: str = "dev"

    def weak_secrets(self) -> list[str]:
        """Secrets that are empty, a known placeholder or too short to guess-proof.

        ADMIN_API_KEY is an admin, JWT_SECRET signs logins and ENCRYPTION_KEY
        protects stored connection credentials. Anything but development/test
        refuses to start with them (see main.lifespan)."""
        weak = []
        for name in ("ENCRYPTION_KEY", "ADMIN_API_KEY", "JWT_SECRET"):
            value = getattr(self, name)
            if value in _PLACEHOLDER_SECRETS or len(value) < 32:
                weak.append(name)
        return weak

    # ── Retention & Alerting ─────────────────────────────────────────────────
    EXECUTION_LOG_RETENTION_DAYS: int = 30
    ALERT_WEBHOOK_URL: str = ""
    # Sent as X-Webhook-Secret on post-execution webhooks, so the receiver
    # (e.g. Arkitekturportalen's SYNC_WEBHOOK_SECRET) can tell them from anyone
    # else's calls. Empty = no header.
    POST_EXEC_WEBHOOK_SECRET: str = ""


settings = Settings()
