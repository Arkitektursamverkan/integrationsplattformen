# Ändringslogg

Ändringarna i Integrationsplattformen, nyast först. Versionerna följer
[semantisk versionering](https://semver.org/lang/sv/): en ny huvudversion
när något tas bort eller byter betydelse, en ny mindre version för nya
funktioner, en ny korrigering för rättelser.

## Ej släppt

- **Render-automatik: Entra ur portalen.** Med nya `PORTAL_URL` (full adress `http://värd:port/api/v1` eller bara `värd:port`, som Renders `hostport`) hämtar plattformen portalens `GET /installation` i bakgrunden vid starten – var 10:e sekund tills det lyckas, sedan var 5:e minut – och fyller `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_API_SCOPE` och `BOOTSTRAP_ADMIN_EMAILS` när de är tomma i plattformens egen miljö. Egna värden vinner alltid. Hemligheten (`X-Installation-Secret`) är nya `PORTAL_INSTALLATION_SECRET`, tomt = `POST_EXEC_WEBHOOK_SECRET`. Omdirigeringar följs inte. Kräver en portal med `/installation`. Utan `PORTAL_URL` är allt som förut. Microsofts nycklar cachas nu per tenant.

## 0.8.0 – 2026-11-10

- **Säkerhet: inloggningar kan återkallas.** Varje användare har en tokenversion (migrering 0006); lösenordsbyte och "logga ut överallt" gör tidigare åtkomst- och uppdateringstoken ogiltiga. Token från äldre versioner gäller tills de går ut. Uppdateringstoken ligger i `sessionStorage`.
- **Säkerhet: Entra** – lokala konton med lösenord kopplas inte via e-posten, gästkonton (B2B) nekas och `BOOTSTRAP_ADMIN_EMAILS` ger administratörsroll bara så länge ingen administratör finns. Koppling och befordran loggas. Nya `ENTRA_REQUIRED_SCOPE` för ett eget scope.
- **Säkerhet: läsare ser inte hemligheter** – huvuden och nycklar i kopplingar, webhookadresser och fullständiga felmeddelanden visas bara för administratörer; den maskerade visningen skriver aldrig över ett sparat värde.
- **Säkerhet: inga standardlösenord.** docker compose kräver `POSTGRES_PASSWORD`, och API:t vägrar starta i produktion med kända förval (`integration_pass` m.fl.). **Uppgradering: en installation som kör med `integration_pass` byter först lösenordet** – `ALTER USER integration_user WITH PASSWORD '…'` och samma värde i `.env`.
- **API-porten publiceras inte längre** i repots docker-compose.yml; webben och portalen når API:t över Docker-nätet. Behövs porten på värden: lägg till `deploy/api-port.yml`.
- Gränser: kroppar högst 21 MB i API:t och nginx; transformstegen körs i en tråd med gränser för reguljära uttryck och mallar. Inaktiverade flöden körs inte av webhook eller schema.
- MCP-servern har `MCP_READ_ONLY=1`. Engångskoden med å/ä/ö ger inte längre fel 500.
- Webben kör nginx som vanlig användare (nginx-unprivileged), fortfarande på port 80, och skickar HSTS bara över https.

## 0.7.0 – 2026-11-10

- **Säkerhet: kopplingar når inte interna adresser i produktion** (loopback, länklokala inkl. 169.254.169.254, privata, 100.64/10, reserverade; omdirigeringar följs inte). Interna mål tillåts med nya `CONNECTOR_ALLOWED_HOSTS` (värdnamn, `*.domän`, IP eller CIDR); värden i `ARKITEKTEN_URL` är alltid tillåten. `CONNECTOR_BLOCK_INTERNAL=false` stänger av spärren. **En installation som hämtar från interna system måste sätta `CONNECTOR_ALLOWED_HOSTS` vid uppgraderingen.**
- **Säkerhet: webhooken efter en körning signeras** (`X-Webhook-Timestamp` + `X-Webhook-Signature`, HMAC-SHA256) och hemligheten skickas aldrig. Kräver Arkitekturportalen 0.13.0 eller senare – uppgradera portalen först.
- **Säkerhet: Arkitektens nyckel skickas bara till värden i `ARKITEKTEN_URL`.** Sparade inloggningsuppgifter i en koppling töms när värden eller `verify_ssl` ändras.
- **Säkerhet: konsumentnycklarnas scopes verkställs** – `data:read` krävs, och nya `flow:<uuid>` begränsar en nyckel till vissa flöden. Befintliga nycklar utan scopes får `data:read` (migrering 0005).
- **Säkerhet: anropsgränser bakom proxy** – nginx skickar klientens adress i stället för att lägga till den, nya `TRUSTED_PROXY` (webben) och `TRUSTED_PROXY_COUNT` (API:t, led räknat från höger). Inloggningen spärras efter 10 misslyckade försök per användarnamn på 15 minuter, och bcrypt körs utanför event-loopen.
- Webbens beroenden installeras med `npm ci`. CI har bara läsbehörighet och actions är låsta till commit-SHA.

## 0.6.0 – 2026-11-09

- Arkitekten-källan skickar `ARK_FLODESTJANST_NYCKEL` som `X-Arkitekten-Nyckel` till Arkitektens flödestjänst (Arkitekten 0.7.0 kräver den när den är satt där), och "Testa anslutning" prövar nu en väg som kräver nyckeln.
- **Säkerhet: CSV-uppladdning kräver administratör.** `POST /csv/upload` och `/csv/replace/{flöde}` krävde bara inloggning, så en läsare kunde skapa källor och tömma vilket flödes poster som helst. Nu krävs administratör, ersättningen godtar bara flöden vars källa är CSV, och filer över 20 MB avvisas (413).
- **Säkerhet: gränser för antal anrop gäller nu.** De var inställda men aldrig inkopplade. Inloggning (`/auth/login`, `/auth/entra`, `/auth/setup`) tål 10 anrop i minuten, inkommande webhooks 60 och övrigt 600, per klientadress. Bakom en proxy (webbens nginx, Render) är adressen proxyns; med nya `TRUST_PROXY_HEADERS=true` räknas i stället första adressen i `X-Forwarded-For` – bara när api:t inte går att nå förbi proxyn.
- **Säkerhet: webhookens hemlighet kontrolleras.** En webhook med hemlighet tar bara emot anrop med samma värde i `X-Webhook-Secret` (annars 401). Webhooks utan hemlighet fungerar som förut.
- **Säkerhet: Entra-inloggningen är stramare.** Bara åtkomsttoken med plattformens scope (`access_as_user`) godtas, inte id-token. Konton kopplas till Entra-kontots `oid` vid första inloggningen och hittas sedan på den; e-postmatchning gäller bara konton som ännu inte är kopplade, och det overifierade claimet `email` används inte. Ny kolumn `users.entra_oid` (migrering 0004). En token med okänd nyckel hämtar Microsofts nycklar på nytt högst en gång i minuten.
- **Säkerhet:** admin-nyckeln jämförs i konstant tid; konsumentnycklar med samma prefix ger inte längre fel 500; utgångstider utan tidszon jämförs som UTC.
- Data-API:t: `by-external` och `changes` visar inte längre CSV-filernas interna originalposter (som övriga anrop redan inte gjorde).
- **Säkerhet: webben skickar säkerhetshuvuden** – Content-Security-Policy, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` och `Referrer-Policy`.
- Avbilderna: api:ts avbild innehåller inte längre testerna, `.env`-filer hålls utanför båda avbilderna och webben byggs utan källkartor. MCP-servern startar inte utan `INTEGRATION_PLATFORM_ADMIN_KEY` (förvalet `dev-admin-key` är borttaget).

## 0.5.0 – 2026-11-09

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
