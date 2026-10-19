"""Arkitekten connector — fetches flowcharts as ready-to-draw *scenes*.

Arkitekten owns the flowcharts; the EA Application needs to display them.
Rather than shipping the raw model and letting the consumer lay it out, this
connector fetches a **scene**: a fully routed layout with coordinates, finished
SVG paths and finished node shapes. Arkitekten computes, the consumer draws.

That split is deliberate. Arkitekten keeps each layout rule in one place
because duplicated rules once made its screen and its exported files
disagree. A consumer that re-derives the layout would recreate exactly that
failure across two systems instead of two files. Arkitekten's flow service
documents the contract.

Two sources, one record shape:

  * ``mode="tjanst"``  — pull from Arkitekten's read-only flow service
    (``GET /api/flows`` + ``/api/flows/{id}/scen``). This covers whatever is
    stored in Arkitekten's ``flows/`` directory.
  * ``mode="2c8"``     — send a 2C8 export through the service's pure
    transform endpoint (``POST /api/scen/2c8``) and get a scene back. The real
    processes live in 2C8, not in Arkitekten, so this is the path that reaches
    all of them. Combine with the ``2c8`` connector, which knows how to pull
    vertices/edges out of the MT Backend.
"""
from __future__ import annotations

import asyncio

import httpx

from app.connectors.base import BaseConnector
from app.connectors.registry import register_connector

# The scene for a large process (104 objects) is ~112 kB and takes ~2 s to
# route, so a whole repository is minutes of work. Keep the per-request timeout
# generous but bounded, and fetch scenes with limited concurrency so we don't
# stampede a single-process Node service.
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_CONCURRENCY = 4


@register_connector
class ArkitektenConnector(BaseConnector):
    connector_type = "arkitekten"

    # ── helpers ───────────────────────────────────────────────────────────

    def _base_url(self) -> str:
        url = str(self.config.get("base_url", "")).rstrip("/")
        if not url:
            raise ValueError("base_url is required (e.g. http://arkitekten.example.org:8200)")
        return url

    def _timeout(self) -> float:
        return float(self.config.get("timeout", _DEFAULT_TIMEOUT))

    def _verify_ssl(self) -> bool:
        return self._as_bool(self.config.get("verify_ssl", True))

    @staticmethod
    def _as_bool(val: object) -> bool:
        """Config from the UI may arrive as a string ("false")."""
        if isinstance(val, str):
            return val.lower() not in ("false", "0", "no", "off", "")
        return bool(val)

    @staticmethod
    def _unwrap(payload: dict, key: str) -> object:
        """Unwrap Arkitekten's ``{ok, ...}`` envelope, raising on ``ok: false``.

        Never swallow a failure into an empty result: ``flow_service`` prunes
        records that are missing from a fetch, so a silently empty return would
        delete the mirror instead of leaving it alone.
        """
        if not isinstance(payload, dict) or not payload.get("ok"):
            raise RuntimeError(
                f"Arkitekten returned an error: {payload.get('error', payload) if isinstance(payload, dict) else payload!r}"
            )
        return payload.get(key)

    def _record(self, sammanfattning: dict, scen: dict | None) -> dict:
        """One flow → one record, in the shape the EA Application consumes.

        `external_id` is the upsert key in `flow_service`; Arkitekten's flow id
        is stable and derived from the name, so it is the right choice.

        Status and version label ("1.0", "2.1") are passed through as READ
        values. Arkitekten derives them from its version history and never
        stores them (its invariant 9) — recomputing them here would let the
        number drift from the status it describes. Note that they are unrelated
        to `DataRecordORM.version`, which is this platform's own change counter.
        """
        record = {
            "external_id": sammanfattning.get("id"),
            "name": sammanfattning.get("name"),
            "familj": sammanfattning.get("familj"),
            "actor": sammanfattning.get("actor"),
            "status": sammanfattning.get("status"),
            "beteckning": sammanfattning.get("beteckning"),
            "fastslagen_beteckning": sammanfattning.get("fastslagenBeteckning"),
            "step_count": sammanfattning.get("stepCount"),
            "version_count": sammanfattning.get("versionCount"),
            "saved_at": sammanfattning.get("savedAt"),
        }
        # The 2C8 prefix ("2.2.7") is the join key against EA's Process nodes,
        # which the 2c8 sync already populates. Only present for 2C8 sources.
        if sammanfattning.get("prefix"):
            record["prefix"] = sammanfattning["prefix"]
        # Where the flow is published in the EA portal ("Publicera i
        # EA-portalen" in Arkitekten). `ea_nod_id` is the EA node the portal
        # attaches the flowchart to; owner and description travel with the
        # flow because a 2C8-synced node is overwritten on every 2C8 sync.
        publicering = sammanfattning.get("publicering")
        if isinstance(publicering, dict) and publicering.get("eaNodId"):
            record["ea_nod_id"] = publicering["eaNodId"]
            record["ägare"] = publicering.get("ägare")
            record["beskrivning"] = publicering.get("beskrivning")
            record["publicerad_at"] = publicering.get("publiceradAt")
        if scen is not None:
            record["scen"] = scen
            # Lifted out of the scene so a consumer can size a canvas without
            # parsing the whole payload.
            record["bredd"] = scen.get("bredd")
            record["höjd"] = scen.get("höjd")
        return record

    # ── fetch ─────────────────────────────────────────────────────────────

    async def fetch(self, params: dict | None = None) -> list[dict]:
        mode = self.config.get("mode", "tjanst")
        if mode == "tjanst":
            return await self._fetch_tjanst()
        if mode == "2c8":
            return await self._fetch_2c8()
        raise ValueError(f"Unknown mode: {mode!r} (expected 'tjanst' or '2c8')")

    async def _fetch_tjanst(self) -> list[dict]:
        """Pull the flow index, then a scene per flow."""
        familj = self.config.get("familj", "2c8")
        include_scene = self.config.get("include_scene", True)
        version = self.config.get("version", "fastslagen")

        async with httpx.AsyncClient(
            timeout=self._timeout(), verify=self._verify_ssl()
        ) as client:
            resp = await client.get(f"{self._base_url()}/api/flows")
            resp.raise_for_status()
            flows = self._unwrap(resp.json(), "flows") or []

            if familj != "alla":
                flows = [f for f in flows if f.get("familj") == familj]

            if not flows:
                # Empty is almost always a misconfiguration (wrong familj,
                # empty FLOWS_DIR). Refuse rather than let the prune run.
                raise RuntimeError(
                    f"Arkitekten returned no flows for familj={familj!r}. "
                    "Refusing to report an empty result, which would prune the mirror."
                )

            # Only what someone has published to the EA portal. Filtered AFTER
            # the emptiness guard above: the guard protects against a broken
            # service, whereas "nothing published" is a legitimate answer and
            # must be allowed to prune an unpublished flow from the mirror.
            # Filtered BEFORE the scenes are fetched — routing is ~2 s per
            # large process, and an unpublished one is not worth it.
            if self._as_bool(self.config.get("endast_publicerade", False)):
                flows = [
                    f for f in flows
                    if isinstance(f.get("publicering"), dict) and f["publicering"].get("eaNodId")
                ]

            if not include_scene:
                return [self._record(f, None) for f in flows]

            # Bounded concurrency: routing is CPU-bound in a single Node
            # process, so more parallelism buys nothing and risks timeouts.
            gate = asyncio.Semaphore(int(self.config.get("concurrency", _DEFAULT_CONCURRENCY)))

            async def en(f: dict) -> dict:
                async with gate:
                    r = await client.get(
                        f"{self._base_url()}/api/flows/{f['id']}/scen",
                        params={"version": version},
                    )
                    r.raise_for_status()
                    return self._record(f, self._unwrap(r.json(), "scen"))

            return list(await asyncio.gather(*(en(f) for f in flows)))

    async def _fetch_2c8(self) -> list[dict]:
        """Turn 2C8 exports into scenes via the service's pure transform.

        `exports` holds raw 2C8 model extracts (vertices/edges/symbols, as
        the 2C8 export format Arkitekten documents). Nothing is
        read from or written to disk on either side — the endpoint is a pure
        function from export to scene.
        """
        exports = self.config.get("exports") or []
        if not exports:
            raise ValueError(
                "mode='2c8' requires an 'exports' list of 2C8 model extracts. "
                "Feed it from the 2c8 connector's vertices/edges fetch."
            )

        async with httpx.AsyncClient(
            timeout=self._timeout(), verify=self._verify_ssl()
        ) as client:
            gate = asyncio.Semaphore(int(self.config.get("concurrency", _DEFAULT_CONCURRENCY)))

            async def en(exp: dict) -> dict:
                async with gate:
                    r = await client.post(f"{self._base_url()}/api/scen/2c8", json=exp)
                    r.raise_for_status()
                    scen = self._unwrap(r.json(), "scen")
                    flöde = scen.get("flöde", {})
                    return self._record(
                        {
                            "id": flöde.get("id"),
                            "name": flöde.get("namn"),
                            "familj": "2c8",
                            "status": flöde.get("status"),
                            "beteckning": flöde.get("beteckning"),
                            "savedAt": flöde.get("sparad"),
                            "prefix": (exp.get("model") or {}).get("prefix"),
                        },
                        scen,
                    )

            return list(await asyncio.gather(*(en(e) for e in exports)))

    # ── connectivity ──────────────────────────────────────────────────────

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=10.0, verify=self._verify_ssl()
            ) as client:
                resp = await client.get(f"{self._base_url()}/health")
                return resp.status_code == 200 and bool(resp.json().get("ok"))
        except Exception:
            return False

    # ── config schema ─────────────────────────────────────────────────────

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "required": ["base_url"],
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "Arkitekten's flow service, e.g. http://arkitekten.example.org:8200",
                },
                "mode": {
                    "type": "string",
                    "enum": ["tjanst", "2c8"],
                    "default": "tjanst",
                    "description": "tjanst = pull stored flows; 2c8 = transform supplied 2C8 exports into scenes",
                },
                "familj": {
                    "type": "string",
                    "enum": ["2c8", "flodesschema", "alla"],
                    "default": "2c8",
                    "description": "Which family to fetch. 2c8 = processes, flodesschema = flowcharts drawn in Arkitekten.",
                },
                "endast_publicerade": {
                    "type": "boolean",
                    "default": False,
                    "description": "Only flows published to the EA portal from Arkitekten (they carry ea_nod_id, ägare, beskrivning).",
                },
                "include_scene": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include the rendered scene. Off gives a lightweight index only.",
                },
                "version": {
                    "type": "string",
                    "enum": ["fastslagen", "aktuell"],
                    "default": "fastslagen",
                    "description": "Which version to render. 'fastslagen' is the approved one an exported document would use.",
                },
                "exports": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Raw 2C8 model extracts (only for mode=2c8)",
                },
                "concurrency": {
                    "type": "integer",
                    "default": _DEFAULT_CONCURRENCY,
                    "description": "Parallel scene requests. Routing is CPU-bound in one Node process; higher is not faster.",
                },
                "timeout": {
                    "type": "number",
                    "default": _DEFAULT_TIMEOUT,
                    "description": "Per-request timeout in seconds. A 100-object process takes ~2 s to route.",
                },
                "verify_ssl": {
                    "type": "boolean",
                    "default": True,
                    "description": "Verify the server's TLS certificate.",
                },
            },
        }
