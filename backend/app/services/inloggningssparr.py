"""Spärr per användarnamn mot lösenordsgissning.

Gränsen per adress (ratelimit.py) stoppar inte den som gissar från många
adresser mot ett och samma konto. Här räknas misslyckade inloggningar per
användarnamn: LOGIN_MAX_FAILURES inom LOGIN_FAILURE_WINDOW_SECONDS spärrar
namnet tills det äldsta försöket fallit ur fönstret.

Räknaren finns i processens minne (plattformens API kör en process). Den
glöms vid omstart, vilket är godtagbart för en tillfällig spärr.
"""
from __future__ import annotations

import math
import time
from collections import deque

from app.config import settings

# Tak för hur många namn som hålls i minnet: den som skickar påhittade namn
# ska inte kunna fylla det.
_MAX_NAMN = 10_000

_misslyckade: dict[str, deque[float]] = {}


def _nyckel(användarnamn: str) -> str:
    return användarnamn.strip().casefold()


def _rensa(försök: deque[float], nu: float) -> None:
    gräns = nu - settings.LOGIN_FAILURE_WINDOW_SECONDS
    while försök and försök[0] <= gräns:
        försök.popleft()


def spärrad_i(användarnamn: str) -> int:
    """Sekunder kvar av spärren för namnet, 0 = inte spärrat."""
    försök = _misslyckade.get(_nyckel(användarnamn))
    if not försök:
        return 0
    nu = time.monotonic()
    _rensa(försök, nu)
    if len(försök) < settings.LOGIN_MAX_FAILURES:
        return 0
    return max(1, math.ceil(försök[0] + settings.LOGIN_FAILURE_WINDOW_SECONDS - nu))


def misslyckades(användarnamn: str) -> None:
    nu = time.monotonic()
    if len(_misslyckade) >= _MAX_NAMN:
        for namn in list(_misslyckade):
            _rensa(_misslyckade[namn], nu)
            if not _misslyckade[namn]:
                del _misslyckade[namn]
        if len(_misslyckade) >= _MAX_NAMN:
            # Fortfarande fullt: släpp det äldst tillagda namnet.
            del _misslyckade[next(iter(_misslyckade))]
    försök = _misslyckade.setdefault(_nyckel(användarnamn), deque())
    _rensa(försök, nu)
    försök.append(nu)


def lyckades(användarnamn: str) -> None:
    _misslyckade.pop(_nyckel(användarnamn), None)


def nollställ() -> None:
    _misslyckade.clear()
