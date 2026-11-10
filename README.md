# Integrationsplattformen

The data-integration half of Arkitekturportalen. It fetches data from other
systems – SharePoint lists, 2C8 process models, REST APIs, CSV files,
Arkitekten flowcharts – transforms it in pipelines and serves it to the
architecture portal, on a schedule or on demand.

| Part | What |
|---|---|
| `backend/` | FastAPI + SQLAlchemy (PostgreSQL), APScheduler with Redis |
| `frontend/` | React + MUI: connections, flows, schedules, executions |
| `mcp-server/` | MCP server exposing the API as tools for AI agents |

Connectors live in `backend/app/connectors/` (one class per source system,
registered in `registry.py`). Stored credentials are encrypted with
`ENCRYPTION_KEY`.

## Installing for an organisation

Install the platform together with the portal from the ready-made images with
the [arkitekturportalen-drift](https://github.com/Arkitektursamverkan/arkitekturportalen-drift)
repository: its `./installera.sh` asks whether to include the platform and
connects the two.

Settings that matter for security – connections to internal addresses
(`CONNECTOR_ALLOWED_HOSTS`), consumer-key scopes, the signed webhook and rate
limits behind a proxy – are described in [docs/sakerhet.md](docs/sakerhet.md).

## Development

```bash
cp .env.example .env    # APP_ENV=development for placeholder secrets
docker compose up -d --build
```

The web UI is on http://localhost:3100 and the API on
http://localhost:8100/api/docs. On first visit the UI asks for the first
administrator.

Tests run on SQLite (see `backend/requirements-dev.txt`):

```bash
cd backend
DATABASE_URL=sqlite+aiosqlite:///test.db ENCRYPTION_KEY=k ADMIN_API_KEY=k JWT_SECRET=k \
  python -m pytest -q
```

A release is a version tag: `git tag v0.1.2 && git push origin v0.1.2` runs CI
and publishes the `api` and `web` images to GitHub Container Registry.

## Licence

Free software under the [EUPL-1.2](LICENSE) (European Union Public Licence),
which is available in all official EU languages, including Swedish.
