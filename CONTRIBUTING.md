# Bidra till Integrationsplattformen

Integrationsplattformen är en del av Arkitekturportalen och delas av organisationerna i
Arkitektursamverkan under EUPL-1.2. Bidrag är välkomna – buggrättningar,
förbättringar och nya funktioner som fler än en organisation har nytta av.

## Så går det till

1. **Börja med ett ärende** (Issues) för allt som är större än en rättelse:
   vad problemet är och vad du tänker göra. Då hinner vi säga om det passar
   innan du lagt tid på det.
2. **En gren och en pull request per steg** mot `main`. En PR gör en sak och
   går att granska på en gång.
3. **CI ska vara grön.** Kör testerna själv först (nedan).
4. **Huvudägaren granskar och mergar** (`.github/CODEOWNERS`). Inriktningen
   och vad som tas in beslutas där; en PR kan behöva justeras innan den tas in.

## Regler för koden

- **Ny kod är generell.** Inget som bara gäller en organisation – namn,
  adresser, personer, egna system – i koden, testerna eller dokumentationen.
  Sådant hör hemma i inställningar, innehållspaket eller organisationens eget
  driftrepo.
- **Inga hemligheter** i repot: inga nycklar, lösenord eller riktiga
  tenant- och klient-id:n, inte heller i exempel och tester.
- **Inget innehåll med riktiga data** – inga processer, objekt eller
  dokument ur en organisations verksamhet, inte ens som testdata.
- **Svenska** i gränssnittet, dokumentationen och commit-meddelandena.
  Identifierare följer stilen i filen du ändrar.
- **Bakåtkompatibelt.** En installation som uppgraderar ska fungera som förut;
  ändrade lagringsformat eller gränssnitt kräver en migrering eller en ny
  version av gränssnittet, och en rad i `CHANGELOG.md`.

## Testa

```sh
# Backend (SQLite räcker för testerna)
cd backend
pip install -r requirements.txt -r requirements-dev.txt
DATABASE_URL=sqlite+aiosqlite:///test.db ENCRYPTION_KEY=test-key ADMIN_API_KEY=test-key \
  JWT_SECRET=test-key APP_ENV=test python -m pytest -q

# Frontend
cd frontend
npm ci && npm run build
```

## Licens

Genom att bidra godkänner du att bidraget licensieras under EUPL-1.2, samma
licens som resten av koden (`LICENSE`).

## Säkerhet

Rapportera aldrig en sårbarhet i ett öppet ärende – se `SECURITY.md`.
