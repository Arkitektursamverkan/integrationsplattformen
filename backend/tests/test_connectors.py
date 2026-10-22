"""Tests for connector registry and mock connectors."""
import pytest
from app.connectors.registry import get_connector_class, list_connector_types
from app.connectors.base import BaseConnector


class TestConnectorRegistry:
    def test_registered_types(self):
        types = list_connector_types()
        assert "generic_rest" in types
        assert "sharepoint" in types
        assert "2c8" in types
        assert "csv" in types

    def test_get_connector_class(self):
        cls = get_connector_class("generic_rest")
        assert issubclass(cls, BaseConnector)

    def test_unknown_connector_raises(self):
        with pytest.raises((KeyError, ValueError)):
            get_connector_class("nonexistent_connector")


class TestGenericRestConnector:
    def test_instantiation(self):
        cls = get_connector_class("generic_rest")
        connector = cls(
            connection_config={"url": "https://example.com/api", "method": "GET"},
            credentials={},
        )
        assert connector is not None

    @pytest.mark.asyncio
    async def test_test_connection_no_url(self):
        cls = get_connector_class("generic_rest")
        connector = cls(connection_config={}, credentials={})
        result = await connector.test_connection()
        assert result is False or (isinstance(result, dict) and result.get("success") is False)


class TestSharePointConnector:
    @pytest.mark.asyncio
    async def test_mock_mode_fetch(self):
        cls = get_connector_class("sharepoint")
        connector = cls(
            connection_config={"mode": "mock"},
            credentials={},
        )
        records = await connector.fetch()
        assert isinstance(records, list)
        assert len(records) > 0
        # Mock records should have name fields
        assert any("name" in r or "Name" in r for r in records)

    def test_column_record_keys_match_cleaned_field_names(self):
        connector = get_connector_class("sharepoint")(connection_config={}, credentials={})
        keys = connector._column_record_keys([
            {"name": "Title", "displayName": "Rubrik"},
            {"name": "Komponentversion", "displayName": "Komponentversion"},
            {"name": "Milj_x00f6_", "displayName": "Miljö"},
            {"name": "Systemagare", "displayName": "Systemägare", "personOrGroup": {}},
            {"name": "Leverantor", "displayName": "Leverantör", "lookup": {"listId": "x"}},
            {"name": "ContentType", "displayName": "Content Type"},
            {"name": "Attachments", "displayName": "Attachments"},
            {"name": "Applikation", "displayName": "Applikation"},
        ])
        assert keys == ["Title", "Komponentversion", "Miljö", "Systemägare", "Leverantör"]


class TestTwoCEightConnector:
    @pytest.mark.asyncio
    async def test_mock_mode_fetch(self):
        cls = get_connector_class("2c8")
        connector = cls(
            connection_config={"mode": "mock"},
            credentials={},
        )
        records = await connector.fetch()
        assert isinstance(records, list)
        assert len(records) > 0

    async def test_current_workflow_state_is_never_promoted(self):
        # A model mid-revision keeps workflow_state APPROVED (an earlier version
        # is still the published one) but reports its real state alongside.
        cls = get_connector_class("2c8")
        connector = cls(connection_config={"mode": "mock"}, credentials={})
        models = [
            {"uuid": "a", "prefix": "1", "titles": {"sv": {"title": "Godkänd"}},
             "modelType": "PROCESS_MODEL", "workflowState": "APPROVED"},
            {"uuid": "b", "prefix": "2", "titles": {"sv": {"title": "Revideras"}},
             "modelType": "PROCESS_MODEL", "workflowState": "UNDER_REVISION"},
        ]

        async def fake_paginated(client, path, **kwargs):
            return models

        async def fake_has_approved(client, repo_id, uuid):
            return True

        connector._get_paginated = fake_paginated
        connector._has_approved_version = fake_has_approved
        records = {r["external_id"]: r for r in await connector._fetch_models(None, "repo")}

        assert records["a"]["current_workflow_state"] == "APPROVED"
        assert records["b"]["workflow_state"] == "APPROVED"
        assert records["b"]["current_workflow_state"] == "UNDER_REVISION"
