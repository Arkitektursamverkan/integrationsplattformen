"""Webhooken efter en körning är signerad – hemligheten själv skickas aldrig."""
import hashlib
import hmac
import json
import time

import httpx

from app.config import settings
from app.services import flow_service


async def _send(monkeypatch) -> httpx.Request:
    sent: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200)), **kwargs)

    monkeypatch.setattr(flow_service.httpx, "AsyncClient", client)
    await flow_service._send_post_exec_webhook("http://ea/api/v1/sync/webhook", flow_service.uuid.uuid4(),
                                               "Flöde", "manual", 1, 1, 0)
    assert len(sent) == 1
    return sent[0]


async def test_signed_not_secret(monkeypatch):
    monkeypatch.setattr(settings, "POST_EXEC_WEBHOOK_SECRET", "delad-hemlighet")
    request = await _send(monkeypatch)
    # Hemligheten finns varken i huvudena eller i kroppen.
    assert "X-Webhook-Secret" not in request.headers
    assert all("delad-hemlighet" not in v for v in request.headers.values())
    assert b"delad-hemlighet" not in request.content

    ts = request.headers["X-Webhook-Timestamp"]
    assert abs(int(ts) - time.time()) < 60
    väntad = hmac.new(b"delad-hemlighet", f"{ts}.".encode() + request.content, hashlib.sha256).hexdigest()
    assert request.headers["X-Webhook-Signature"] == f"sha256={väntad}"
    # Den signerade kroppen är den som skickades, och den är JSON.
    assert request.headers["Content-Type"] == "application/json"
    assert json.loads(request.content)["event"] == "flow.execution.success"


async def test_signature_depends_on_secret_body_and_time(monkeypatch):
    monkeypatch.setattr(settings, "POST_EXEC_WEBHOOK_SECRET", "s")
    a = flow_service.webhook_signatur(b'{"a":1}', 1000)
    assert a["X-Webhook-Timestamp"] == "1000"
    assert a != flow_service.webhook_signatur(b'{"a":2}', 1000)
    assert a != flow_service.webhook_signatur(b'{"a":1}', 1001)
    monkeypatch.setattr(settings, "POST_EXEC_WEBHOOK_SECRET", "t")
    assert a != flow_service.webhook_signatur(b'{"a":1}', 1000)


async def test_unsigned_without_secret(monkeypatch):
    monkeypatch.setattr(settings, "POST_EXEC_WEBHOOK_SECRET", "")
    request = await _send(monkeypatch)
    assert "X-Webhook-Secret" not in request.headers
    assert "X-Webhook-Signature" not in request.headers
    assert "X-Webhook-Timestamp" not in request.headers
