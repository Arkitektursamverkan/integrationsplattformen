"""Kopplingarnas nätverk: spärr mot anrop till interna adresser (SSRF).

En koppling anropar den adress som administratören skrivit in. Utan spärr
kan den som får skapa en koppling låta plattformen anropa sådant som bara
syns inifrån: molnets metadatatjänst (169.254.169.254), databaser och andra
tjänster på det interna nätet, eller plattformen själv.

Med spärren på (CONNECTOR_BLOCK_INTERNAL, på i produktion) slås värdnamnet
upp före varje anrop, och anropet stoppas om NÅGON av adresserna är
loopback, länklokal, privat, delad (100.64/10), multicast eller reserverad.
Omdirigeringar följs inte (httpx standard), och varje anrop som ändå görs
kontrolleras för sig av samma krok.

Interna mål som ska nås – Arkitekten i samma compose-projekt, 2C8 på
10.x-nätet – anges i CONNECTOR_ALLOWED_HOSTS. Värden i ARKITEKTEN_URL är
alltid tillåten.

Kvarvarande risk: namnet slås upp igen när httpx ansluter. En angripare som
styr en DNS-zon kan i princip byta svar mellan kontrollen och anslutningen
(DNS-rebinding). Kontrollen stänger de vanliga vägarna, inte den.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from app.config import settings

_STANDARDPORT = {"http": 80, "https": 443}

Adress = ipaddress.IPv4Address | ipaddress.IPv6Address
Nät = ipaddress.IPv4Network | ipaddress.IPv6Network


class SpärradAdress(ValueError):
    """Anropet stoppades: målet är internt och inte tillåtet."""


def spärr_på() -> bool:
    värde = settings.CONNECTOR_BLOCK_INTERNAL.strip().lower()
    if värde in ("", "auto"):
        return settings.APP_ENV not in ("development", "test")
    return värde in ("true", "1", "yes", "on")


def ursprung(url: str) -> tuple[str, str, int] | None:
    """(schema, värd, port) för en adress, med standardport utskriven."""
    try:
        delar = urlsplit(url.strip())
        schema = delar.scheme.lower()
        värd = (delar.hostname or "").lower().rstrip(".")
        port = delar.port or _STANDARDPORT.get(schema)
    except ValueError:
        return None
    if not schema or not värd or port is None:
        return None
    return schema, värd, port


def arkitekten_ursprung() -> tuple[str, str, int] | None:
    """Ursprunget för den konfigurerade ARKITEKTEN_URL (värd utan port = 8200)."""
    from app.services.arkitekten_kalla import bas_url

    url = bas_url(settings.ARKITEKTEN_URL)
    return ursprung(url) if url else None


def _tillåtna() -> tuple[set[str], list[Nät]]:
    namn: set[str] = set()
    nät: list[Nät] = []
    for post in settings.CONNECTOR_ALLOWED_HOSTS.split(","):
        post = post.strip().lower().rstrip(".")
        if not post:
            continue
        try:
            nät.append(ipaddress.ip_network(post, strict=False))
            continue
        except ValueError:
            pass
        namn.add(post)
    ark = arkitekten_ursprung()
    if ark:
        namn.add(ark[1])
    return namn, nät


def _namn_tillåtet(värd: str, namn: set[str]) -> bool:
    if värd in namn:
        return True
    # *.intern.example (eller .intern.example) = alla namn under domänen.
    for post in namn:
        suffix = post[1:] if post.startswith("*.") else post if post.startswith(".") else None
        if suffix and värd.endswith(suffix):
            return True
    return False


def _intern(ip: Adress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _slå_upp(värd: str, port: int) -> set[Adress]:
    try:
        return {ipaddress.ip_address(värd)}
    except ValueError:
        pass
    try:
        svar = await asyncio.get_running_loop().getaddrinfo(värd, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SpärradAdress(f"{värd} kan inte slås upp ({e})") from e
    # Ett IPv6-svar kan bära zon ("fe80::1%eth0").
    return {ipaddress.ip_address(str(s[4][0]).split("%")[0]) for s in svar}


async def kontrollera_url(url: str) -> None:
    """Stoppar (SpärradAdress) ett anrop till en intern, otillåten adress."""
    if not spärr_på():
        return
    delar = ursprung(url)
    if delar is None or delar[0] not in _STANDARDPORT:
        raise SpärradAdress(f"Ogiltig adress för en koppling: {url!r} (http eller https krävs)")
    _, värd, port = delar
    namn, nät = _tillåtna()
    if _namn_tillåtet(värd, namn):
        return
    for ip in await _slå_upp(värd, port):
        if any(ip in n for n in nät):
            continue
        if _intern(ip):
            raise SpärradAdress(
                f"{värd} pekar på den interna adressen {ip}. Kopplingar får inte anropa "
                "interna adresser – lägg till värden i CONNECTOR_ALLOWED_HOSTS om det är meningen."
            )


async def _kontrollera_anrop(request: httpx.Request) -> None:
    await kontrollera_url(str(request.url))


def klient(**kwargs) -> httpx.AsyncClient:
    """httpx.AsyncClient för kopplingar: varje anrop kontrolleras först, och
    omdirigeringar följs inte."""
    kwargs["follow_redirects"] = False
    hooks = dict(kwargs.pop("event_hooks", None) or {})
    hooks["request"] = [_kontrollera_anrop, *hooks.get("request", [])]
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)
