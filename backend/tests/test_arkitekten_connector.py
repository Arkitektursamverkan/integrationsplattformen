"""Tests for the Arkitekten connector.

The connector's job is narrow but its failure mode is not: `flow_service`
prunes any record missing from a fetch, so a fetch that quietly returns nothing
would delete the mirror rather than leave it alone. Most of what follows guards
that edge.
"""
import pytest

from app.connectors.base import BaseConnector
from app.connectors.registry import get_connector_class, list_connector_types


def _connector(**config):
    cls = get_connector_class("arkitekten")
    return cls(connection_config=config, credentials={})


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
    """Stands in for httpx.AsyncClient; records what was asked for."""

    def __init__(self, routes, **_kwargs):
        self.routes = routes
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        return self.routes(url)

    async def post(self, url, json=None):
        self.calls.append(("POST", url, json))
        return self.routes(url)


@pytest.fixture
def fake_httpx(monkeypatch):
    """Swap httpx.AsyncClient inside the connector module for a stub."""

    def install(routes):
        from app.connectors import arkitekten

        holder = {}

        def factory(**kwargs):
            holder["client"] = FakeClient(routes, **kwargs)
            return holder["client"]

        monkeypatch.setattr(arkitekten.httpx, "AsyncClient", factory)
        return holder

    return install


class TestRegistration:
    def test_registered(self):
        assert "arkitekten" in list_connector_types()
        assert issubclass(get_connector_class("arkitekten"), BaseConnector)

    def test_schema_requires_base_url(self):
        schema = get_connector_class("arkitekten").config_schema()
        assert "base_url" in schema["required"]
        assert schema["properties"]["mode"]["enum"] == ["tjanst", "2c8"]

    def test_base_url_is_required_at_runtime(self):
        with pytest.raises(ValueError, match="base_url"):
            _connector()._base_url()

    def test_verify_ssl_tolerates_stringified_booleans(self):
        assert _connector(verify_ssl="false")._verify_ssl() is False
        assert _connector(verify_ssl="true")._verify_ssl() is True
        assert _connector()._verify_ssl() is True


class TestRecordShape:
    def test_maps_summary_and_scene(self):
        c = _connector(base_url="http://x")
        rec = c._record(
            {
                "id": "c8-2-2-7-uthyrning",
                "name": "2.2.7 Uthyrning",
                "familj": "2c8",
                "status": "utkast",
                "beteckning": "0.7",
                "fastslagenBeteckning": None,
                "stepCount": 5,
                "versionCount": 7,
                "savedAt": "2026-08-25T00:00:00.000Z",
                "prefix": "2.2.7",
            },
            {"bredd": 7536, "höjd": 1473, "noder": []},
        )
        # external_id is the upsert key in flow_service.
        assert rec["external_id"] == "c8-2-2-7-uthyrning"
        assert rec["beteckning"] == "0.7"
        # The prefix is what joins a scene to an EA Process node.
        assert rec["prefix"] == "2.2.7"
        assert rec["bredd"] == 7536

    def test_omits_prefix_when_absent(self):
        rec = _connector(base_url="http://x")._record({"id": "a"}, None)
        assert "prefix" not in rec
        assert "scen" not in rec


class TestEnvelope:
    def test_raises_on_error_envelope(self):
        with pytest.raises(RuntimeError, match="Flödet finns inte"):
            _connector()._unwrap({"ok": False, "error": "Flödet finns inte."}, "scen")

    def test_raises_on_garbage(self):
        with pytest.raises(RuntimeError):
            _connector()._unwrap("<html>not a service</html>", "flows")


class TestFetch:
    @pytest.mark.asyncio
    async def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            await _connector(base_url="http://x", mode="nonsense").fetch()

    @pytest.mark.asyncio
    async def test_fetches_index_and_scene_per_flow(self, fake_httpx):
        def routes(url):
            if url.endswith("/api/flows"):
                return FakeResponse(
                    {
                        "ok": True,
                        "flows": [
                            {"id": "c8-a", "name": "A", "familj": "2c8"},
                            {"id": "portal-b", "name": "B", "familj": "flodesschema"},
                        ],
                    }
                )
            return FakeResponse({"ok": True, "scen": {"bredd": 10, "höjd": 20}})

        holder = fake_httpx(routes)
        recs = await _connector(base_url="http://x").fetch()

        # familj defaults to 2c8 — the portal flows are not processes.
        assert [r["external_id"] for r in recs] == ["c8-a"]
        assert recs[0]["scen"] == {"bredd": 10, "höjd": 20}
        # The approved version is the default, matching what an export would use.
        assert ("GET", "http://x/api/flows/c8-a/scen", {"version": "fastslagen"}) in holder[
            "client"
        ].calls

    @pytest.mark.asyncio
    async def test_include_scene_false_skips_scene_calls(self, fake_httpx):
        holder = fake_httpx(
            lambda url: FakeResponse({"ok": True, "flows": [{"id": "c8-a", "familj": "2c8"}]})
        )
        recs = await _connector(base_url="http://x", include_scene=False).fetch()
        assert "scen" not in recs[0]
        assert len(holder["client"].calls) == 1

    @pytest.mark.asyncio
    async def test_familj_alla_keeps_everything(self, fake_httpx):
        fake_httpx(
            lambda url: FakeResponse(
                {"ok": True, "flows": [{"id": "a", "familj": "2c8"}, {"id": "b", "familj": "flodesschema"}]}
            )
            if url.endswith("/api/flows")
            else FakeResponse({"ok": True, "scen": {}})
        )
        recs = await _connector(base_url="http://x", familj="alla").fetch()
        assert {r["external_id"] for r in recs} == {"a", "b"}

    @pytest.mark.asyncio
    async def test_empty_result_raises_instead_of_pruning_the_mirror(self, fake_httpx):
        """The important one.

        flow_service deletes records that are absent from a fetch. A
        misconfigured familj or an empty FLOWS_DIR must therefore fail loudly
        rather than report success with nothing in it.
        """
        fake_httpx(lambda url: FakeResponse({"ok": True, "flows": []}))
        with pytest.raises(RuntimeError, match="prune"):
            await _connector(base_url="http://x").fetch()

    @pytest.mark.asyncio
    async def test_endast_publicerade_keeps_published_and_carries_the_ea_node(self, fake_httpx):
        """Arkitekten's "Publicera i EA-portalen" puts `publicering` on a flow.

        Only those are mirrored, unpublished ones get no scene fetched, and the
        EA node id, owner and description travel along on the record.
        """
        pub = {"eaNodId": "nod-1", "ägare": "IT-chef", "beskrivning": "Syftet.", "publiceradAt": "2026-10-08T10:00:00Z"}

        def routes(url):
            if url.endswith("/api/flows"):
                return FakeResponse(
                    {
                        "ok": True,
                        "flows": [
                            {"id": "c8-pub", "familj": "2c8", "publicering": pub},
                            {"id": "c8-utkast", "familj": "2c8"},
                        ],
                    }
                )
            return FakeResponse({"ok": True, "scen": {}})

        holder = fake_httpx(routes)
        recs = await _connector(base_url="http://x", endast_publicerade="true").fetch()
        assert [r["external_id"] for r in recs] == ["c8-pub"]
        assert recs[0]["ea_nod_id"] == "nod-1"
        assert recs[0]["ägare"] == "IT-chef"
        assert recs[0]["beskrivning"] == "Syftet."
        assert recs[0]["publicerad_at"] == "2026-10-08T10:00:00Z"
        assert not any("c8-utkast" in c[1] for c in holder["client"].calls)

    @pytest.mark.asyncio
    async def test_nothing_published_is_an_empty_result_not_an_error(self, fake_httpx):
        """Unpublishing the last flow must be able to prune it from the mirror.

        The emptiness guard still protects against a broken service (no flows
        at all); "none published" is a real answer.
        """
        fake_httpx(lambda url: FakeResponse({"ok": True, "flows": [{"id": "c8-a", "familj": "2c8"}]}))
        assert await _connector(base_url="http://x", endast_publicerade=True).fetch() == []

    @pytest.mark.asyncio
    async def test_error_envelope_propagates(self, fake_httpx):
        fake_httpx(lambda url: FakeResponse({"ok": False, "error": "trasig katalog"}))
        with pytest.raises(RuntimeError, match="trasig katalog"):
            await _connector(base_url="http://x").fetch()


class TestTransformMode:
    @pytest.mark.asyncio
    async def test_requires_exports(self):
        with pytest.raises(ValueError, match="exports"):
            await _connector(base_url="http://x", mode="2c8").fetch()

    @pytest.mark.asyncio
    async def test_posts_each_export_and_keeps_the_prefix(self, fake_httpx):
        holder = fake_httpx(
            lambda url: FakeResponse(
                {
                    "ok": True,
                    "scen": {
                        "bredd": 100,
                        "höjd": 50,
                        "flöde": {
                            "id": "c8-2-2-7-uthyrning",
                            "namn": "2.2.7 Uthyrning",
                            "status": "utkast",
                            "beteckning": "0.1",
                            "sparad": "2026-08-28T00:00:00.000Z",
                        },
                    },
                }
            )
        )
        recs = await _connector(
            base_url="http://x",
            mode="2c8",
            exports=[{"model": {"prefix": "2.2.7"}, "nodes": [], "edges": []}],
        ).fetch()

        assert recs[0]["external_id"] == "c8-2-2-7-uthyrning"
        assert recs[0]["prefix"] == "2.2.7"
        assert holder["client"].calls[0][0] == "POST"


class TestConnectivity:
    @pytest.mark.asyncio
    async def test_health_ok(self, fake_httpx):
        fake_httpx(lambda url: FakeResponse({"ok": True, "antal": 71}))
        assert await _connector(base_url="http://x").test_connection() is True

    @pytest.mark.asyncio
    async def test_health_failure_is_false_not_an_exception(self, fake_httpx):
        fake_httpx(lambda url: FakeResponse({"ok": False}, status=500))
        assert await _connector(base_url="http://x").test_connection() is False
