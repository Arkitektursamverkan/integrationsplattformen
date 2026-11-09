# Ändringslogg

Ändringarna i Integrationsplattformen, nyast först. Versionerna följer
[semantisk versionering](https://semver.org/lang/sv/): en ny huvudversion
när något tas bort eller byter betydelse, en ny mindre version för nya
funktioner, en ny korrigering för rättelser.

## Ej släppt

- **Säkerhet: förvaltningens läsningar kräver inloggning.** Listorna och detaljerna för källor, flöden, scheman och körningar svarade utan inloggning; nu krävs inloggning eller admin-nyckeln. Webhooks (med sina hemliga sökvägar) visas bara för administratörer. Portalens anrop (`/data` och "Hämta nu") påverkas inte.
- **Säkerhet: första administratören kräver engångskoden `SETUP_CODE`** i produktion. Utan den går inget första konto att skapa. Med Entra och `BOOTSTRAP_ADMIN_EMAILS` är sidan stängd helt.
- **Säkerhet: `APP_ENV` är `production` som standard**, så svaga eller exempelhemligheter stoppar starten även när `APP_ENV` inte är satt. Utveckling sätter `APP_ENV=development` själv.

## 0.4.0 – 2026-11-09

- **Logga in med Microsoft (Entra)** – med samma app-registrering som Arkitekturportalen och Arkitekten, så att ett och samma konto gäller överallt. Sätt `ENTRA_TENANT_ID` och `ENTRA_CLIENT_ID` på api:t och lägg till `https://<plattformens adress>/login` som SPA-omdirigering. Adresserna i `BOOTSTRAP_ADMIN_EMAILS` blir administratörer vid första inloggningen; andra släpps in om en administratör lagt till dem med samma e-post. Egna konton fungerar som förut.

- **Arkitektens källa skapas av sig själv**: med `ARKITEKTEN_URL` satt (full adress, eller bara värd – då port 8200) skapar plattformen vid starten källan, flödet och schemat (varannan timme) som hämtar Arkitektens publicerade processbilder. Bara om ingen källa av typen arkitekten finns – en befintlig rörs inte.
- **Inloggningen på svenska**, och en ny installation utan konton går direkt till sidan där det första administratörskontot skapas (ny publik `GET /api/v1/auth/setup` svarar `{"needed": true|false}`).

## 0.3.1 – 2026-11-09

- **Render**: webben når api:t. Render ger api:t ett kort internt namn som bara går att slå upp med en sökdomän, och nginx egen uppslagning använder inte sökdomäner – webben svarade 502 på allt under `/api`. Namnet byggs nu ut med sökdomänen när containern startar (`18-api-upstream.envsh`). Med docker compose är allt som förut.

## 0.3.0 – 2026-11-09

- **Går att köra på Render och liknande plattformar.** Webben lyssnar på `PORT` (förval 80) och slår upp api-adressen (`API_UPSTREAM`) på nytt var tionde sekund i stället för en gång vid start.
- `DATABASE_URL` tas emot i den form en hanterad databas ger den (`postgres://…`, `postgresql://…`, `sslmode=`).


## 0.2.3 – 2026-11-02

- Backend på Python 3.14 och webbens bygge på Node 26 (LTS).

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
