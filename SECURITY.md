# Säkerhet

## Rapportera en sårbarhet

Skriv **inte** om en sårbarhet i ett ärende eller en pull request. Kontakta
i stället Arkitektursamverkans kontaktperson direkt – uppgifterna står i
installationsmanualen i
[arkitekturportalen-drift](https://github.com/Arkitektursamverkan/arkitekturportalen-drift)
(`docs/installationsmanual.html`). Beskriv vad som är sårbart, i vilken
version och hur det kan återskapas.

Vi bekräftar att rapporten kommit fram, bedömer den och berättar när en
rättelse finns. Rättelsen släpps som en ny version; installationerna
uppgraderar med `./uppgradera.sh` i driftrepot.

## Versioner som får rättelser

Den senaste släppta versionen. Äldre versioner rättas inte – uppgradera.

## För den som installerar

- Hemligheterna står i `.env` i driftrepot och skapas av installationsguiden.
  Spara en kopia säkert; lägg aldrig `.env` i git.
- Håll avbilderna uppdaterade och ta backup före varje uppgradering
  (`./uppgradera.sh` gör det).
