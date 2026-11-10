# Säkerhet: inställningar en installation behöver känna till

Allt nedan ställs in i `.env` (se `.env.example`). Standardvärdena är säkra;
det som en befintlig installation kan behöva ändra vid uppgradering står under
varje rubrik.

## Kopplingar till interna adresser (SSRF-spärr)

En koppling anropar den adress som administratören skriver in. För att den som
får skapa kopplingar inte ska kunna låta plattformen anropa sådant som bara syns
inifrån – molnets metadatatjänst (`169.254.169.254`), databaser, andra tjänster
på det interna nätet eller plattformen själv – stoppar plattformen anrop till

- loopback (`127.0.0.0/8`, `::1`),
- länklokala adresser (`169.254.0.0/16`, `fe80::/10`),
- privata nät (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`),
- delade (`100.64.0.0/10`), multicast och reserverade adresser.

Värdnamnet slås upp före varje anrop och stoppas om **någon** av adresserna är
intern. Omdirigeringar följs inte. Spärren gäller REST-, 2C8- och
Arkitekten-kopplingarna och knappen "Testa" (som då visar varför).
SharePoint-kopplingen anropar bara Microsofts fasta adresser.

| Inställning | Betydelse |
|---|---|
| `CONNECTOR_BLOCK_INTERNAL` | `auto` (standard) = på utom när `APP_ENV` är `development`/`test`. `true`/`false` = alltid på/av. |
| `CONNECTOR_ALLOWED_HOSTS` | Interna mål som ändå får anropas, kommaseparerade: värdnamn (`arkitekten`), domäner (`*.intern.example`), adresser (`10.1.2.3`) eller nät (`10.0.0.0/8`). |

Värden i `ARKITEKTEN_URL` är alltid tillåten.

**Viktigt för en befintlig installation:** når plattformen 2C8, ett REST-API
eller något annat på det interna nätet eller i samma docker-nät (t.ex. ett
docker-namn som `arkitekten` utan att `ARKITEKTEN_URL` är satt), måste värden
stå i `CONNECTOR_ALLOWED_HOSTS` – annars misslyckas hämtningarna med ett fel
som säger just det. Exempel:

```sh
CONNECTOR_ALLOWED_HOSTS=arkitekten,2c8.intern.example,10.0.0.0/8
```

Kvarvarande risk: namnet slås upp en gång till när anslutningen görs. Den som
styr en DNS-zon kan i princip byta svar däremellan (DNS-rebinding). Tillåt
därför hellre enskilda värdar än hela nät.

## Arkitektens nyckel

`ARK_FLODESTJANST_NYCKEL` skickas som `X-Arkitekten-Nyckel` **bara** till samma
schema, värd och port som `ARKITEKTEN_URL` (värd utan port betyder `:8200`).
En Arkitekten-koppling med en annan adress får ingen nyckel, och en varning
(`arkitekten.nyckel_ej_skickad`) skrivs i loggen. Har installationen nyckeln
satt men inte `ARKITEKTEN_URL`, sätt den till kopplingens adress.

## Webhooken efter en körning

Flödets "after execution"-webhook är signerad i stället för att bära
hemligheten:

```
X-Webhook-Timestamp: <unix-sekunder>
X-Webhook-Signature: sha256=<hex HMAC-SHA256(POST_EXEC_WEBHOOK_SECRET, "<timestamp>." + kroppen)>
```

Mottagaren räknar om signaturen över den råa kroppen och godtar bara en
tidsstämpel inom ±300 sekunder. `X-Webhook-Secret` skickas inte längre.
Arkitekturportalen måste därför ha en version som verifierar signaturen;
äldre portaler tar emot webhooken som obehörig (synken sker då bara på
portalens eget schema).

## Konsumentnycklar och scopes

Data-API:t (`/api/v1/data/...`) kräver att nyckeln har scopet `data:read`.
Med ett eller flera `flow:<flödets uuid>` får nyckeln bara läsa de flödena:
`/data/sources` visar bara dem, och andra flöden ger 403. En nyckel utan
`flow:`-scope läser alla flöden, som förut. I gränssnittet väljs flödena under
Settings → New API Key.

Nycklar som skapats med en tom scope-lista får `data:read` av migreringen
`0005`. En nyckel med andra scopes men utan `data:read` slutar fungera mot
data-API:t.

## Sparade inloggningsuppgifter när adressen ändras

Ändras värden (eller schema/port) i en kopplings `url`/`base_url`, eller
`verify_ssl`, töms de sparade inloggningsuppgifterna om inga nya anges i samma
ändring. Svaret har `credentials_cleared: true`, och gränssnittet ber om
uppgifterna igen.

## Anropsgränser bakom en proxy

Anropsgränserna (t.ex. 10 inloggningar i minuten) räknas per klientadress.

- Webbens nginx skickar alltid exakt ett led i `X-Forwarded-For` till API:t:
  klienten som nginx ser den.
- `TRUSTED_PROXY` (webben): proxyn framför nginx, som adress eller intervall
  (flera med mellanslag eller komma). Då tar nginx klientens adress ur
  proxyns `X-Forwarded-For` – bara från de adresserna.
- `TRUST_PROXY_HEADERS=true` (API:t): klienten tas ur `X-Forwarded-For`, ledet
  nummer `TRUSTED_PROXY_COUNT` (standard 1) räknat från höger. Bara när API:t
  inte kan nås utom genom proxyn.

Utöver gränsen per adress spärras ett användarnamn efter `LOGIN_MAX_FAILURES`
(10) misslyckade inloggningar inom `LOGIN_FAILURE_WINDOW_SECONDS` (900 s).
Spärren finns i API-processens minne och glöms vid omstart.
