"""The post-execution webhook carries the shared secret when one is configured."""
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


async def test_secret_sent_as_header(monkeypatch):
    monkeypatch.setattr(settings, "POST_EXEC_WEBHOOK_SECRET", "delad-hemlighet")
    request = await _send(monkeypatch)
    assert request.headers["X-Webhook-Secret"] == "delad-hemlighet"


async def test_no_header_without_secret(monkeypatch):
    monkeypatch.setattr(settings, "POST_EXEC_WEBHOOK_SECRET", "")
    request = await _send(monkeypatch)
    assert "X-Webhook-Secret" not in request.headers
