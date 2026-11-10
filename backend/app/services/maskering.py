"""Hemligheter som bara administratörer ska se.

Alla inloggade får läsa kopplingar, flöden och körningar; en läsare (viewer)
ska ändå inte se det som ger åtkomst till andra system: huvuden och nycklar i
en kopplings config, webhookadressen efter en körning (den kan bära en nyckel
i sökvägen eller frågesträngen) och felmeddelanden som kan citera adresser
med nycklar i.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from app.models.user import UserORM

# Ersätter ett dolt värde. En administratör som skickar tillbaka det oförändrat
# (gränssnittet sparar hela config) behåller det sparade värdet.
MASK = "••••••"

_KÄNSLIGA_ORD = ("token", "key", "secret", "password", "authorization")
# Felmeddelanden till läsare kortas till så här många tecken.
FEL_MAX = 300


def är_admin(principal: Any) -> bool:
    """Administratörsnyckeln (None) eller en inloggad administratör."""
    return principal is None or (isinstance(principal, UserORM) and principal.role == "admin")


def känslig_nyckel(namn: str) -> bool:
    n = str(namn).lower()
    return n == "headers" or any(ord_ in n for ord_ in _KÄNSLIGA_ORD)


def _maskera_värde(värde: Any) -> Any:
    if isinstance(värde, dict):
        return {k: MASK for k in värde}
    if värde in (None, ""):
        return värde
    return MASK


def maskera_config(config: dict | None) -> dict:
    """En kopia av config där känsliga nycklar och alla huvuden är dolda."""
    ut: dict = {}
    for k, v in (config or {}).items():
        if känslig_nyckel(k):
            ut[k] = _maskera_värde(v)
        elif isinstance(v, dict):
            ut[k] = maskera_config(v)
        else:
            ut[k] = v
    return ut


def återställ_maskerat(ny: Any, gammal: Any) -> Any:
    """Ny config där varje värde som är exakt MASK ersätts med det sparade –
    så skrivs en hemlighet aldrig över med masken."""
    if isinstance(ny, dict):
        g = gammal if isinstance(gammal, dict) else {}
        ut = {}
        for k, v in ny.items():
            if v == MASK:
                if k in g:
                    ut[k] = g[k]
                # Inget sparat värde att återställa: masken sparas inte.
                continue
            ut[k] = återställ_maskerat(v, g.get(k))
        return ut
    return ny


def maskera_url(url: str | None) -> str | None:
    """Bara schema och värd, t.ex. https://mottagare.example/… ."""
    if not url:
        return url
    try:
        delar = urlsplit(url)
        värd = delar.hostname or ""
        if delar.port:
            värd = f"{värd}:{delar.port}"
    except ValueError:
        return MASK
    if not delar.scheme or not värd:
        return MASK
    return f"{delar.scheme}://{värd}/…"


_URL = re.compile(r"""(?i)\b[a-z][a-z0-9+.-]*://[^\s'"<>]+""")


def _rensa_url(m: re.Match) -> str:
    url = m.group(0)
    # Användare och lösenord i adressen, frågesträng och fragment bort.
    url = re.sub(r"(?i)^([a-z][a-z0-9+.-]*://)[^/@\s]*@", r"\1", url)
    return re.split(r"[?#]", url, maxsplit=1)[0] + ("?…" if "?" in url else "")


def rensa_felmeddelande(fel: str | None) -> str | None:
    """Felmeddelandet för en läsare: adresser utan frågesträng och inloggning,
    och högst FEL_MAX tecken."""
    if not fel:
        return fel
    rensat = _URL.sub(_rensa_url, fel)
    if len(rensat) > FEL_MAX:
        rensat = rensat[:FEL_MAX] + "…"
    return rensat
