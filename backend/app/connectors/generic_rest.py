"""Generic REST connector — configurable for any REST API."""
from __future__ import annotations

import httpx

from app.connectors.base import BaseConnector
from app.connectors.registry import register_connector


@register_connector
class GenericRestConnector(BaseConnector):
    connector_type = "generic_rest"

    async def fetch(self, params: dict | None = None) -> list[dict]:
        url = self.config.get("url", "")
        method = self.config.get("method", "GET").upper()
        headers = {**self.config.get("headers", {})}
        query_params = {**self.config.get("params", {}), **(params or {})}

        # Apply auth
        auth_type = self.config.get("auth_type", "none")
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {self.credentials.get('token', '')}"
        elif auth_type == "api_key":
            header_name = self.config.get("api_key_header", "X-Api-Key")
            headers[header_name] = self.credentials.get("api_key", "")

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers, params=query_params)
            else:
                body = self.config.get("body", {})
                resp = await client.request(method, url, headers=headers, params=query_params, json=body)

            resp.raise_for_status()
            data = resp.json()

        # Extract records from response using a configurable path
        data_path = self.config.get("data_path", "")
        if data_path:
            for key in data_path.split("."):
                if isinstance(data, dict):
                    data = data.get(key, [])
                else:
                    break

        if isinstance(data, list):
            return data
        return [data]

    async def test_connection(self) -> bool:
        try:
            records = await self.fetch()
            return True
        except Exception:
            return False

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string", "description": "The API endpoint URL"},
                "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
                "headers": {"type": "object", "default": {}},
                "params": {"type": "object", "default": {}},
                "body": {"type": "object", "default": {}},
                "auth_type": {"type": "string", "enum": ["none", "bearer", "api_key"], "default": "none"},
                "api_key_header": {"type": "string", "default": "X-Api-Key"},
                "data_path": {"type": "string", "description": "Dot-separated path to records array in response"},
            },
        }
