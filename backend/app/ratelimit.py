"""Rate limiting shared by the whole API (slowapi).

Behind nginx or a platform proxy (Render) every request comes from the proxy's
address, so all clients would share one limit. With TRUST_PROXY_HEADERS the
first X-Forwarded-For entry is the client instead – only turn it on when the
API cannot be reached except through such a proxy, since the header is
otherwise whatever the caller chooses to send.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings


def client_address(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return get_remote_address(request)


# Generous by default (a whole office may share one address); the login
# endpoints and the inbound webhook carry tighter limits of their own.
# Off in tests, which make many requests from the same address.
limiter = Limiter(
    key_func=client_address,
    default_limits=["600/minute"],
    enabled=settings.APP_ENV != "test",
)
