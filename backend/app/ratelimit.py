"""Rate limiting shared by the whole API (slowapi).

Behind nginx or a platform proxy (Render) every request comes from the proxy's
address, so all clients would share one limit. With TRUST_PROXY_HEADERS the
client is read from X-Forwarded-For instead – only turn it on when the API
cannot be reached except through such a proxy, since the header is otherwise
whatever the caller chooses to send.

Varje proxy lägger till den adress den såg sist i huvudet, så bara de
TRUSTED_PROXY_COUNT sista leden (räknat från höger) är skrivna av proxyer vi
litar på. Klienten är ledet nummer TRUSTED_PROXY_COUNT från höger – det första
ledet kan anroparen ha skrivit själv och får aldrig avgöra gränsen.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings


def client_address(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        # Flera X-Forwarded-For-huvuden räknas som ett, i ordning.
        led = [
            del_.strip()
            for värde in request.headers.getlist("x-forwarded-for")
            for del_ in värde.split(",")
            if del_.strip()
        ]
        if led:
            antal = max(1, settings.TRUSTED_PROXY_COUNT)
            # Färre led än proxyer: alla är proxyernas, ta det yttersta.
            return led[-antal] if len(led) >= antal else led[0]
    return get_remote_address(request)


# Generous by default (a whole office may share one address); the login
# endpoints and the inbound webhook carry tighter limits of their own.
# Off in tests, which make many requests from the same address.
limiter = Limiter(
    key_func=client_address,
    default_limits=["600/minute"],
    enabled=settings.APP_ENV != "test",
)
