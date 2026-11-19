"""Tests for the 2C8 connector's `diagrams` resource type.

What matters most here is WHICH VERSION a drawing belongs to. 2C8 returns the
rows of every version in one list with nothing to tell them apart, and says
"approved" only about the current version. A consumer that shows approved
processes to a whole organisation must never be handed the draft by mistake.
"""
import pytest

from app.connectors import two_c8_diagram as diagram
from app.connectors.registry import get_connector_class

REPO = "repo-1"
BASE = f"https://c8.example.org/mt-backend/api/v1/repositories/{REPO}"
SV = "lang-sv"


# ── pure functions ────────────────────────────────────────────────────────────

class TestSplitVersions:
    def test_a_block_ends_where_a_key_comes_back(self):
        rows = [{"uuid": "a"}, {"uuid": "b"}, {"uuid": "a"}, {"uuid": "b"}, {"uuid": "c"}, {"uuid": "a"}]
        blocks = diagram.split_versions(rows, "uuid")
        assert [[r["uuid"] for r in b] for b in blocks] == [["a", "b"], ["a", "b", "c"], ["a"]]

    def test_no_rows_no_blocks(self):
        assert diagram.split_versions([], "uuid") == []

    def test_rows_without_the_key_stay_in_their_block(self):
        blocks = diagram.split_versions([{"uuid": "a"}, {}, {}, {"uuid": "a"}], "uuid")
        assert [len(b) for b in blocks] == [3, 1]


class TestBlockFor:
    def test_counts_from_the_end(self):
        blocks = [["v0"], ["v1"], ["v2"]]
        assert diagram.block_for(blocks, 2, 2) == ["v2"]
        assert diagram.block_for(blocks, 0, 2) == ["v0"]

    def test_current_version_is_the_last_block_even_when_early_ones_are_gone(self):
        # Model version 5, but only three blocks came back.
        blocks = [["v3"], ["v4"], ["v5"]]
        assert diagram.block_for(blocks, 5, 5) == ["v5"]
        assert diagram.block_for(blocks, 3, 5) == ["v3"]
        assert diagram.block_for(blocks, 2, 5) is None

    def test_an_empty_model_is_an_empty_drawing_not_a_missing_one(self):
        assert diagram.block_for([], 0, 0) == []
        assert diagram.block_for([], 0, 1) is None


class TestApprovedVersion:
    def test_current_version_approved(self):
        assert diagram.approved_version({"version": 3, "workflowState": "APPROVED"}, []) == 3

    def test_older_version_approved(self):
        versions = [
            {"version": 0, "logItems": [{"workflowState": "UNDER_APPROVAL"}, {"workflowState": "APPROVED"}]},
            {"version": 1, "logItems": [{"workflowState": "EDITABLE"}]},
        ]
        assert diagram.approved_version({"version": 1, "workflowState": "EDITABLE"}, versions) == 0

    def test_the_latest_approved_one_wins(self):
        versions = [
            {"version": 0, "logItems": [{"workflowState": "APPROVED"}]},
            {"version": 1, "logItems": [{"workflowState": "EDITABLE"}]},
            {"version": 2, "logItems": [{"workflowState": "APPROVED"}]},
            {"version": 3, "logItems": [{"workflowState": "UNDER_REVISION"}]},
        ]
        assert diagram.approved_version({"version": 3, "workflowState": "UNDER_REVISION"}, versions) == 2

    def test_never_approved(self):
        versions = [{"version": 0, "logItems": [{"workflowState": "UNDER_APPROVAL"}]}]
        assert diagram.approved_version({"version": 0, "workflowState": "UNDER_REVISION"}, versions) is None

    def test_an_approval_in_the_current_versions_log_does_not_count(self):
        # Approved, then reopened in the same version: the model's own state
        # is what applies to the current version.
        versions = [{"version": 0, "logItems": [{"workflowState": "APPROVED"}, {"workflowState": "EDITABLE"}]}]
        assert diagram.approved_version({"version": 0, "workflowState": "EDITABLE"}, versions) is None


class TestBuildExport:
    def _export(self, **kwargs):
        defaults = dict(
            model={"uuid": "m1", "prefix": "1.2", "modelType": "PROCESS_MODEL"},
            name="Process",
            version=0,
            workflow_state="APPROVED",
            vertices=[],
            edges=[],
            descriptions=[],
            model_layers=[],
            symbols={},
            layer_types={},
            drilldowns={},
            language=SV,
        )
        return diagram.build_export(**{**defaults, **kwargs})

    def test_node_takes_name_and_type_from_its_symbol(self):
        out = self._export(
            vertices=[{"uuid": "v1", "symbol": {"uuid": "s1"}, "x": 1, "y": 2, "width": 3, "height": 4, "zOrder": 5}],
            symbols={"s1": {"objectType": "ACTIVITY", "titles": {SV: {"title": "Godkänner"}}}},
        )
        assert out["nodes"] == [{
            "id": "v1", "symbol_id": "s1", "label": "Godkänner", "object_type": "ACTIVITY",
            "geometry": {"x": 1, "y": 2, "width": 3, "height": 4, "z": 5},
            "layer_id": None, "drilldown": None,
        }]

    def test_the_vertex_own_title_wins(self):
        out = self._export(
            vertices=[{"uuid": "v1", "symbol": {"uuid": "s1"}, "titles": {SV: {"title": "Eget namn"}}}],
            symbols={"s1": {"objectType": "ROLE", "titles": {SV: {"title": "Symbolens"}}}},
        )
        assert out["nodes"][0]["label"] == "Eget namn"

    def test_edges_point_at_vertices_and_mark_the_sequence(self):
        out = self._export(edges=[
            {"uuid": "e1", "fromVertex": "v1", "toVertex": "v2", "edgeType": "FLOW",
             "labels": {SV: {"title": "Ja"}}, "points": ["1,2,3,4"]},
            {"uuid": "e2", "fromVertex": "v3", "toVertex": "v1", "edgeType": "RACI_RESPONSIBLE"},
        ])
        assert out["edges"][0] == {
            "id": "e1", "from": "v1", "to": "v2", "edge_type": "FLOW", "label": "Ja",
            "is_sequence": True, "waypoints": ["1,2,3,4"],
        }
        assert out["edges"][1]["is_sequence"] is False

    def test_description_html_is_flattened(self):
        out = self._export(descriptions=[
            {"descriptionType": "t1", "content": {SV: {"text": "<p>M&aring;let</p><p>Rad tv&aring;</p>"}}},
        ])
        assert out["descriptions"][0]["text"] == "Målet\n\nRad två"

    def test_only_layers_in_use_are_listed(self):
        out = self._export(
            vertices=[{"uuid": "v1", "symbol": {"uuid": "s1"}, "layer": "l1"}],
            model_layers=[{"uuid": "l1", "layerType": "lt1"}, {"uuid": "l2", "layerType": "lt1"}],
            layer_types={"lt1": {"titles": {SV: {"title": "Ansvar"}}, "objectTypes": "ROLE;POSITION;"}},
        )
        assert out["layers"] == [{"id": "l1", "name": "Ansvar", "applies_to_object_types": ["ROLE", "POSITION"]}]


# ── the connector ─────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get(self, url, headers=None, params=None):
        self.calls.append((url, params))
        if url not in self.routes:
            return FakeResponse({"data": []})
        payload = self.routes[url]
        return payload if isinstance(payload, FakeResponse) else FakeResponse({"data": payload, "total": len(payload)})


def _vertex(uuid, symbol):
    return {"uuid": uuid, "symbol": {"uuid": symbol}, "x": 0, "y": 0, "width": 10, "height": 10}


def _model(uuid, prefix, title, state, version=0, model_type="PROCESS_MODEL"):
    return {"uuid": uuid, "prefix": prefix, "titles": {SV: {"title": title}}, "modelType": model_type,
            "workflowState": state, "version": version, "lastModified": "2026-01-01T00:00:00Z"}


def _connector(**config):
    cls = get_connector_class("2c8")
    return cls(
        connection_config={"mode": "api", "base_url": "https://c8.example.org", "repository_id": REPO,
                           "resource_type": "diagrams", **config},
        credentials={"api_key": "hemlig"},
    )


def _routes(models, per_model):
    routes = {
        f"{BASE}/languages": [{"uuid": SV, "defaultLanguage": True}],
        f"{BASE}/models": models,
        f"{BASE}/symbols": [
            {"uuid": "s-akt", "objectType": "ACTIVITY", "titles": {SV: {"title": "Aktivitet"}}},
            {"uuid": "s-ny", "objectType": "ACTIVITY", "titles": {SV: {"title": "Ny aktivitet"}}},
        ],
        f"{BASE}/layer-types": [],
    }
    for uuid, delar in per_model.items():
        for del_, rader in delar.items():
            routes[f"{BASE}/models/{uuid}/{del_}"] = rader
    return routes


class TestFetchDiagrams:
    @pytest.mark.asyncio
    async def test_approved_model_reports_its_current_version_as_the_approved_one(self):
        client = FakeClient(_routes(
            [_model("m1", "1", "Godkänd", "APPROVED")],
            {"m1": {"vertices": [_vertex("v1", "s-akt")]}},
        ))
        [post] = await _connector()._fetch_diagrams(client, REPO)
        assert post["external_id"] == "m1"
        assert post["approved_version"] == 0 and post["approved_is_current"] is True
        assert post["approved"] is None and post["approved_missing"] is False
        assert [n["label"] for n in post["current"]["nodes"]] == ["Aktivitet"]
        # The version log is not needed for an approved model.
        assert not any(url.endswith("/versions") for url, _ in client.calls)

    @pytest.mark.asyncio
    async def test_model_under_revision_keeps_its_approved_drawing_apart_from_the_draft(self):
        client = FakeClient(_routes(
            [_model("m1", "1", "Revideras", "EDITABLE", version=1)],
            {"m1": {
                # Two versions in one list: the block ends where v1 comes back.
                "vertices": [_vertex("v1", "s-akt"), _vertex("v1", "s-akt"), _vertex("v2", "s-ny")],
                "versions": [
                    {"version": 0, "logItems": [{"workflowState": "APPROVED"}]},
                    {"version": 1, "logItems": [{"workflowState": "EDITABLE"}]},
                ],
            }},
        ))
        [post] = await _connector()._fetch_diagrams(client, REPO)
        assert post["workflow_state"] == "EDITABLE" and post["version"] == 1
        assert post["approved_version"] == 0 and post["approved_is_current"] is False
        assert [n["id"] for n in post["approved"]["nodes"]] == ["v1"]
        assert [n["id"] for n in post["current"]["nodes"]] == ["v1", "v2"]
        assert post["approved"]["model"]["workflow_state"] == "APPROVED"
        assert post["current"]["model"]["workflow_state"] == "EDITABLE"

    @pytest.mark.asyncio
    async def test_never_approved_model_has_no_approved_drawing(self):
        client = FakeClient(_routes(
            [_model("m1", "1", "Utkast", "EDITABLE")],
            {"m1": {"vertices": [_vertex("v1", "s-akt")]}},
        ))
        [post] = await _connector()._fetch_diagrams(client, REPO)
        assert post["approved_version"] is None
        assert post["approved"] is None and post["approved_is_current"] is False

    @pytest.mark.asyncio
    async def test_says_so_when_the_approved_versions_rows_are_gone(self):
        client = FakeClient(_routes(
            [_model("m1", "1", "Revideras", "EDITABLE", version=1)],
            {"m1": {
                "vertices": [_vertex("v2", "s-ny")],  # only the current version came back
                "versions": [{"version": 0, "logItems": [{"workflowState": "APPROVED"}]}],
            }},
        ))
        [post] = await _connector()._fetch_diagrams(client, REPO)
        assert post["approved_version"] == 0
        assert post["approved"] is None and post["approved_missing"] is True

    @pytest.mark.asyncio
    async def test_only_process_models_unless_configured(self):
        models = [_model("m1", "1", "Process", "APPROVED"),
                  _model("m2", "", "Organisation", "EDITABLE", model_type="ORGANISATION_MODEL")]
        poster = await _connector()._fetch_diagrams(FakeClient(_routes(models, {})), REPO)
        assert [p["external_id"] for p in poster] == ["m1"]
        poster = await _connector(model_types=["ORGANISATION_MODEL"])._fetch_diagrams(
            FakeClient(_routes(models, {})), REPO)
        assert [p["external_id"] for p in poster] == ["m2"]

    @pytest.mark.asyncio
    async def test_prefix_root_limits_to_a_subtree(self):
        models = [_model("m1", "4.4", "IT", "APPROVED"), _model("m2", "4.4.1", "Under", "APPROVED"),
                  _model("m3", "4.41", "Granne", "APPROVED")]
        poster = await _connector(prefix_root="4.4")._fetch_diagrams(FakeClient(_routes(models, {})), REPO)
        assert sorted(p["prefix"] for p in poster) == ["4.4", "4.4.1"]

    @pytest.mark.asyncio
    async def test_drilldown_is_read_backwards_and_the_owning_model_comes_first(self):
        models = [_model("m1", "1", "Karta", "APPROVED"), _model("m2", "1.1", "Äger", "APPROVED"),
                  _model("m3", "1.2", "Återanvänder", "APPROVED")]
        client = FakeClient(_routes(models, {
            "m1": {"vertices": [_vertex("v1", "s-akt")]},
            "m3": {"broken-down-from": [{"symbol": {"uuid": "s-akt"}, "owning": False}]},
            "m2": {"broken-down-from": [{"symbol": {"uuid": "s-akt"}, "owning": True}]},
        }))
        poster = await _connector()._fetch_diagrams(client, REPO)
        karta = next(p for p in poster if p["external_id"] == "m1")
        assert karta["current"]["nodes"][0]["drilldown"] == {
            "model_id": "m2", "name": "Äger", "prefix": "1.1", "is_primary": True,
        }

    @pytest.mark.asyncio
    async def test_no_models_is_an_error_not_an_empty_result(self):
        # flow_service prunes every record missing from a fetch.
        with pytest.raises(RuntimeError, match="no models"):
            await _connector()._fetch_diagrams(FakeClient(_routes([], {})), REPO)

    @pytest.mark.asyncio
    async def test_a_truncated_drawing_is_an_error(self):
        routes = _routes([_model("m1", "1", "Process", "APPROVED")], {})
        routes[f"{BASE}/models/m1/vertices"] = FakeResponse({"data": [_vertex("v1", "s-akt")], "total": 40})
        with pytest.raises(RuntimeError, match="reports 40 rows"):
            await _connector()._fetch_diagrams(FakeClient(routes), REPO)

    @pytest.mark.asyncio
    async def test_asks_for_every_field_and_every_row(self):
        client = FakeClient(_routes([_model("m1", "1", "Process", "APPROVED")], {}))
        await _connector()._fetch_diagrams(client, REPO)
        assert all(params == {"projection": "ALL", "startAt": 0, "maxResults": 20000} for _, params in client.calls)

    def test_schema_lists_the_resource_type(self):
        schema = get_connector_class("2c8").config_schema()
        assert "diagrams" in schema["properties"]["resource_type"]["enum"]
