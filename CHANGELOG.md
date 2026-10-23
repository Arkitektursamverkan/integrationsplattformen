# Ändringslogg

Ändringarna i Integrationsplattformen, nyast först. Versionerna följer
[semantisk versionering](https://semver.org/lang/sv/): en ny huvudversion
när något tas bort eller byter betydelse, en ny mindre version för nya
funktioner, en ny korrigering för rättelser.

## Ej släppt

- (inget än)

## 0.2.0 – 2026-10-23

- Arkitekten-källan: familjen `affarsprocess` (det gamla namnet `2c8` läses som samma familj) och flödestjänstens kontraktsversion läses; en okänd högre version avvisas.
- Borttaget: Arkitekten-källans `mode="2c8"` och `backend/scripts/hamta_2c8_uttag.py` (Arkitekten importerar inte längre 2C8-uttag). Plattformens egen 2C8-källa påverkas inte.
- SharePoint: kolumner som ännu är tomma kommer med i posterna och kan väljas i pipeline-editorn.

## 0.1.2 – 2026-10-19

- Första versionen i Arkitektursamverkan: färdiga avbilder och ren historik.
