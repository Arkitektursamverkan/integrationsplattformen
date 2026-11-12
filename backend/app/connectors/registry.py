"""Connector registry — maps connector_type strings to classes."""
from __future__ import annotations

from app.connectors.base import BaseConnector

_registry: dict[str, type[BaseConnector]] = {}


def register_connector(cls: type[BaseConnector]) -> type[BaseConnector]:
    _registry[cls.connector_type] = cls
    return cls


def get_connector_class(connector_type: str) -> type[BaseConnector]:
    cls = _registry.get(connector_type)
    if cls is None:
        raise ValueError(f"Unknown connector type: {connector_type!r}. Available: {list(_registry.keys())}")
    return cls


def list_connector_types() -> list[str]:
    return list(_registry.keys())


# Import connector modules to trigger registration
def _auto_register() -> None:
    import app.connectors.sharepoint  # noqa: F401
    import app.connectors.two_c8  # noqa: F401
    import app.connectors.generic_rest  # noqa: F401
    import app.connectors.csv_connector  # noqa: F401
    import app.connectors.arkitekten  # noqa: F401
    import app.connectors.excel_sharepoint  # noqa: F401


_auto_register()
