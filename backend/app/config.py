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


# Databaslösenord som har stått som standard i compose-filer och exempel.
_STANDARD_DB_LÖSENORD = {"integration_pass", "postgres", "password", "changeme", "change-me"}


def _db_lösenord(url: str) -> str | None:
    """Lösenordet i en databasadress, None om den inte har något."""
    from urllib.parse import unquote, urlsplit
    try:
        lösen = urlsplit(url).password
    except ValueError:
        return None
    return unquote(lösen) if lösen is not None else None


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

    # Rate limits count per client address. Behind nginx or a platform proxy
    # that is the proxy's; true = take the client from X-Forwarded-For instead.
    # Only when the API is reachable through that proxy alone (see ratelimit.py).
    TRUST_PROXY_HEADERS: bool = False
    # Hur många proxyer framför API:t som lägger till ett led i X-Forwarded-For.
    # Klienten är ledet så många steg från HÖGER – led längre till vänster kan
    # anroparen själv ha skrivit. Webbens nginx ensam = 1.
    TRUSTED_PROXY_COUNT: int = 1

    @field_validator("TRUSTED_PROXY_COUNT")
    @classmethod
    def minst_en_proxy(cls, v: int) -> int:
        return max(1, v)

    # Spärr per användarnamn vid inloggning, utöver gränsen per adress:
    # så många misslyckade försök inom fönstret låser kontot tillfälligt.
    LOGIN_MAX_FAILURES: int = 10
    LOGIN_FAILURE_WINDOW_SECONDS: int = 15 * 60

    # ── App ──────────────────────────────────────────────────────────────────
    # Production unless said otherwise: then weak or placeholder secrets stop
    # the start. Development and tests set APP_ENV themselves.
    APP_ENV: str = "production"
    LOG_LEVEL: str = "info"
    # Set in the image at release (Dockerfile ARG); "dev" when built locally.
    APP_VERSION: str = "dev"

    def weak_secrets(self) -> list[str]:
        """Secrets that are empty, a known placeholder or too short to guess-proof.

        ADMIN_API_KEY is an admin, JWT_SECRET signs logins and ENCRYPTION_KEY
        protects stored connection credentials. DATABASE_URL counts when its
        password is a known default such as integration_pass. Anything but development/test
        refuses to start with them (see main.lifespan)."""
        weak = []
        for name in ("ENCRYPTION_KEY", "ADMIN_API_KEY", "JWT_SECRET"):
            value = getattr(self, name)
            if value in _PLACEHOLDER_SECRETS or len(value) < 32:
                weak.append(name)
        # Ett känt standardlösenord för databasen (docker-compose.yml hade
        # integration_pass som förval).
        if _db_lösenord(self.DATABASE_URL) in _STANDARD_DB_LÖSENORD:
            weak.append("DATABASE_URL")
        return weak

    # ── Retention & Alerting ─────────────────────────────────────────────────
    EXECUTION_LOG_RETENTION_DAYS: int = 30
    ALERT_WEBHOOK_URL: str = ""
    # Signerar webhooken efter en körning (X-Webhook-Timestamp och
    # X-Webhook-Signature = HMAC-SHA256), så att mottagaren (t.ex.
    # Arkitekturportalens SYNC_WEBHOOK_SECRET) kan skilja den från andras
    # anrop. Själva hemligheten skickas aldrig. Tomt = osignerad.
    POST_EXEC_WEBHOOK_SECRET: str = ""

    # ── Entra (samma app-registrering som portalen och Arkitekten) ───────────
    # Tenant och client satta = webben visar "Logga in med Microsoft". Tomt =
    # bara egna konton. Scope tomt = api://<client>/access_as_user.
    ENTRA_TENANT_ID: str = ""
    ENTRA_CLIENT_ID: str = ""
    ENTRA_API_SCOPE: str = ""
    # Scopet (scp) en token måste ha för att godtas här, t.ex. Plattform.Access.
    # Tomt = sista delen av ENTRA_API_SCOPE (access_as_user) – samma som
    # portalen och Arkitekten, så att deras token godtas här också. Se
    # docs/sakerhet.md om ett eget scope eller en egen app-registrering.
    ENTRA_REQUIRED_SCOPE: str = ""
    # De här adresserna blir administratörer vid sin första Entra-inloggning –
    # bara så länge installationen saknar administratör. Andra måste först
    # läggas till av en administratör (med samma e-post, utan lösenord).
    BOOTSTRAP_ADMIN_EMAILS: str = ""

    # ── Portalen (Render-automatik) ──────────────────────────────────────────
    # Arkitekturportalens API: full adress (http://host:port/api/v1) eller bara
    # värd:port (Render fromService … hostport) = http://värd:port/api/v1.
    # Satt = plattformen hämtar Entra-uppgifterna ur portalens
    # GET /installation vid starten och fyller ENTRA_TENANT_ID, ENTRA_CLIENT_ID,
    # ENTRA_API_SCOPE och BOOTSTRAP_ADMIN_EMAILS – bara de som är tomma här.
    # Tomt = inget hämtas (som förut).
    PORTAL_URL: str = ""
    # Skickas som X-Installation-Secret – portalens SYNC_WEBHOOK_SECRET. Tomt =
    # POST_EXEC_WEBHOOK_SECRET (som redan är samma värde).
    PORTAL_INSTALLATION_SECRET: str = ""

    # One-time code for creating the first admin at /setup. In production the
    # first account cannot be created without it – otherwise whoever reached a
    # new installation first would become its admin.
    SETUP_CODE: str = ""

    def setup_code_required(self) -> bool:
        return self.APP_ENV not in ("development", "test") or bool(self.SETUP_CODE)

    @property
    def bootstrap_admin_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.BOOTSTRAP_ADMIN_EMAILS.split(",") if e.strip()]

    # ── Arkitekten ───────────────────────────────────────────────────────────
    # Arkitektens flödestjänst (full adress, eller värd[:port] – utan port
    # 8200). Satt = plattformen skapar vid starten källan som hämtar de
    # publicerade processbilderna, om ingen sådan källa finns. Tomt = inget.
    ARKITEKTEN_URL: str = ""
    # Arkitektens flödestjänst kräver den här nyckeln (huvudet
    # X-Arkitekten-Nyckel) när den har en – samma värde som där. Tomt = ingen.
    # Skickas bara till samma schema, värd och port som ARKITEKTEN_URL.
    ARK_FLODESTJANST_NYCKEL: str = ""

    # ── Kopplingarnas nätverk (SSRF-spärr) ───────────────────────────────────
    # Kopplingar (REST, 2C8, Arkitekten) får inte anropa interna adresser –
    # loopback, länklokala (t.ex. 169.254.169.254), privata och reserverade –
    # så att den som kan skapa en koppling inte kan nå tjänster bakom
    # brandväggen. auto = på utom i development/test; true/false = alltid.
    CONNECTOR_BLOCK_INTERNAL: str = "auto"
    # Interna mål som ändå är tillåtna, kommaseparerade: värdnamn (arkitekten),
    # domäner (*.intern.example), adresser (10.1.2.3) eller nät (10.0.0.0/8).
    # Värden i ARKITEKTEN_URL är alltid tillåten.
    CONNECTOR_ALLOWED_HOSTS: str = ""


settings = Settings()
