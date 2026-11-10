"""Största tillåtna kropp i en begäran, innan något läses in.

CSV-filerna får vara 20 MB (api/v1/csv_upload.py), men formuläret tolkas –
och sparas i temporära filer – innan den gränsen prövas. Den här
ASGI-middlewaren avvisar redan vid Content-Length, och räknar byten när
huvudet saknas (chunked), så att ingen kan skicka obegränsat mycket.
Webbens nginx har samma gräns (client_max_body_size 20m) för /api.
"""
from __future__ import annotations

import json

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 20 MB fil plus formulärets övriga delar.
MAX_BODY_BYTES = 21 * 1024 * 1024


class KroppenFörStor(HTTPException):
    """Ett HTTPException, så att FastAPI släpper igenom det när kroppen
    läses (andra fel blir 400) och svarar 413."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=_DETALJ)


_DETALJ = f"Request body too large (max {MAX_BODY_BYTES // (1024 * 1024)} MB)"


class Kroppsgräns:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _svara_413(self, send: Send) -> None:
        body = json.dumps({"detail": _DETALJ}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for namn, värde in scope.get("headers", []):
            if namn == b"content-length":
                try:
                    längd = int(värde)
                except ValueError:
                    längd = 0
                if längd > self.max_bytes:
                    await self._svara_413(send)
                    return

        mottaget = 0
        för_stor = False
        påbörjat = False

        async def räknande_receive() -> Message:
            nonlocal mottaget, för_stor
            meddelande = await receive()
            if meddelande["type"] == "http.request":
                mottaget += len(meddelande.get("body", b""))
                if mottaget > self.max_bytes:
                    för_stor = True
                    raise KroppenFörStor()
            return meddelande

        async def spårande_send(meddelande: Message) -> None:
            nonlocal påbörjat
            if för_stor:
                # Det som läste kroppen kan ha gjort om felet till något annat
                # (FastAPI svarar 400 på fel i en tolkning, middleware i
                # mellan slår in det): svaret blir ändå 413.
                if meddelande["type"] == "http.response.start" and not påbörjat:
                    påbörjat = True
                    await self._svara_413(send)
                return
            if meddelande["type"] == "http.response.start":
                påbörjat = True
            await send(meddelande)

        try:
            await self.app(scope, räknande_receive, spårande_send)
        except Exception:
            if not för_stor:
                raise
            if not påbörjat:
                await self._svara_413(send)
