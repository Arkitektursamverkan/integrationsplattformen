"""Abstract base connector — all connectors implement this interface."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseConnector(ABC):
    connector_type: str = ""

    def __init__(self, connection_config: dict, credentials: dict | None = None):
        self.config = connection_config
        self.credentials = credentials or {}

    @abstractmethod
    async def fetch(self, params: dict | None = None) -> list[dict]:
        """Fetch raw records from the external system."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Verify connectivity and credentials."""

    @classmethod
    def config_schema(cls) -> dict:
        """Return JSON Schema describing required config fields."""
        return {}
