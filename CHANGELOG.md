# Ändringslogg

Ändringarna i Integrationsplattformen, nyast först. Versionerna följer
[semantisk versionering](https://semver.org/lang/sv/): en ny huvudversion
när något tas bort eller byter betydelse, en ny mindre version för nya
funktioner, en ny korrigering för rättelser.

## Ej släppt

- (inget än)

## 0.2.2 – 2026-11-02

- Beroenden uppdaterade: SQLAlchemy 2.1 (med `[asyncio]`), bcrypt 5 (lösenord och API-nycklar längre än 72 byte kapas som förut, så befintliga fungerar), FastAPI 0.162, uvicorn 0.54, httpx 0.28, pydantic-settings 2.16, APScheduler 3.11, tenacity 9.2, react-query 5.105, axios 1.21 och nginx 1.31 i webbens Docker-avbild.
## 0.2.1 – 2026-10-23

- Beroenden uppdaterade: webbgränssnittet går på React 19, MUI 9, React Router 7, Vite 8 (med @vitejs/plugin-react 6), TypeScript 7 och zustand 5 och byggs med Node 24 (LTS) och nginx 1.29; backend på FastAPI 0.150 (Starlette 1.x), pydantic 2.14, asyncpg 0.32, redis 8.1, cryptography 50, alembic 1.20 och python-jose 3.5 (tester med pytest 9); MCP-servern på @modelcontextprotocol/sdk 1.32 och zod 4; GitHub Actions på de senaste huvudversionerna.

## 0.2.0 – 2026-10-23

- Arkitekten-källan: familjen `affarsprocess` (det gamla namnet `2c8` läses som samma familj) och flödestjänstens kontraktsversion läses; en okänd högre version avvisas.
- Borttaget: Arkitekten-källans `mode="2c8"` och `backend/scripts/hamta_2c8_uttag.py` (Arkitekten importerar inte längre 2C8-uttag). Plattformens egen 2C8-källa påverkas inte.
- SharePoint: kolumner som ännu är tomma kommer med i posterna och kan väljas i pipeline-editorn.

## 0.1.2 – 2026-10-19

- Första versionen i Arkitektursamverkan: färdiga avbilder och ren historik.
