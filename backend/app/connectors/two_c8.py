"""2C8 connector — fetches process/model data from 2C8 MT Backend REST API.

API documentation: https://developer.2c8.com/
Base path: /mt-backend/api/v1

The 2C8 API organises data as:
  Repositories → Models (process diagrams) → Symbols (objects on diagrams)
                                            → Edges (connections between symbols)
                                            → Descriptions (rich text attached to models/symbols)
                                            → Vertices (graphical positions)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from app.connectors import natverk
from app.connectors import two_c8_diagram as diagram
from app.connectors.base import BaseConnector
from app.connectors.registry import register_connector

# 2C8's MT Backend reports a `total` per response and accepts an arbitrarily
# large `maxResults`, but its `startAt` offset parameter is currently broken
# (startAt > 0 returns no rows). So we fetch everything in a single request
# with a high `maxResults` and verify we got all `total` rows. Override via
# the `max_results` config field for very large repositories.
_DEFAULT_MAX_RESULTS = 10000

# Diagrams cost several requests per model, and one more per model in the
# repository for the drill-down map. Bounded so a fetch does not flood a single
# 2C8 server; the timeout is per request and generous because the symbol list
# of a whole repository comes back in one response.
_DIAGRAM_CONCURRENCY = 8
_DIAGRAM_TIMEOUT = 180.0
_DIAGRAM_MAX_RESULTS = 20000


def _resolve_parent_prefix(prefix: str, available_prefixes) -> str:
    """Derive the parent prefix for a 2C8 model's `prefix` value.

    2C8 users mix two conventions side-by-side:
      - Plain numbering (`0`, `2`, `2.1`): the parent of `2.1` is `2`.
      - Chapter-root suffix `.0` (`1.0`, `2.1.0`): used when the literal
        parent slot is occupied by a non-model concept. Sibling diagrams
        treat the `.0` entry as their parent.

    Resolution order for a prefix `P`:
      1. Direct strip-last-segment parent (`P.rsplit(".",1)[0]`) if it
         exists as a model prefix.
      2. The chapter-root sibling `<direct>.0` if it exists — and is not
         `P` itself. This lets `1.1` find `1.0`, and `2.1.5` fall back
         to `2.1.0` when `2.1` is missing.
      3. Otherwise no parent (top-level).

    The chapter-root suffix is NOT a top-level marker on its own:
    `2.1.0` resolves to parent `2.1`, not "" — only the literal first-
    level chapter root (`1.0`, with no `1` model present) falls through
    to top-level because there is nothing above it.
    """
    if not prefix or "." not in prefix:
        return ""
    direct = prefix.rsplit(".", 1)[0]
    if direct in available_prefixes:
        return direct
    chapter_root = f"{direct}.0"
    if chapter_root != prefix and chapter_root in available_prefixes:
        return chapter_root
    return ""


@register_connector
class TwoC8Connector(BaseConnector):
    connector_type = "2c8"

    # ── helpers ───────────────────────────────────────────────────────────

    def _base_url(self) -> str:
        url = self.config.get("base_url", "").rstrip("/")
        if not url:
            raise ValueError("base_url is required for API mode")
        return url

    def _headers(self) -> dict[str, str]:
        api_key = self.credentials.get("api_key", "")
        return {
            "Accept": "application/json",
            "X-API-Key": api_key,
        }

    def _verify_ssl(self) -> bool:
        # Default to verifying. Allow opt-out for self-signed certs on AD-issued
        # internal hosts where the system trust store can't validate the chain.
        # Tolerate stringified booleans coming from a JSON config form.
        val = self.config.get("verify_ssl", True)
        if isinstance(val, str):
            return val.lower() not in ("false", "0", "no", "off")
        return bool(val)

    async def _get_paginated(
        self, client: httpx.AsyncClient, path: str, params: dict | None = None
    ) -> list[dict]:
        """Fetch a 2C8 list endpoint.

        2C8 wraps list responses as `{"startAt": N, "maxResults": M, "total": T, "data": [...]}`,
        with variant keys `values` / `results` on some endpoints. The MT Backend
        currently ignores `startAt > 0`, so we send one large request and warn
        if the server reports more rows than fit in our `max_results` cap.
        """
        max_results = int(self.config.get("max_results", _DEFAULT_MAX_RESULTS))
        extra = params or {}

        resp = await client.get(
            f"{self._base_url()}{path}",
            headers=self._headers(),
            params={"startAt": 0, "maxResults": max_results, **extra},
        )
        resp.raise_for_status()
        payload = resp.json()

        if isinstance(payload, list):
            return payload

        items = payload.get("data") or payload.get("values") or payload.get("results") or []
        if isinstance(items, dict):
            items = [items]

        total = payload.get("total")
        if isinstance(total, int) and total > len(items):
            # Server reports more rows than we got — surface this clearly rather
            # than silently truncating. The caller can bump `max_results` in
            # the connection config.
            import structlog
            structlog.get_logger().warning(
                "two_c8.truncated",
                path=path,
                fetched=len(items),
                total=total,
                max_results=max_results,
            )
        return items

    # ── fetch ─────────────────────────────────────────────────────────────

    async def fetch(self, params: dict | None = None) -> list[dict]:
        mode = self.config.get("mode", "mock")
        if mode == "mock":
            return self._fetch_mock()
        return await self._fetch_api()

    def _fetch_mock(self) -> list[dict]:
        seed_path = Path(__file__).resolve().parents[2] / "seed" / "2c8_processes.json"
        return json.loads(seed_path.read_text(encoding="utf-8"))

    async def _fetch_api(self) -> list[dict]:
        """Fetch data from the 2C8 MT Backend REST API.

        The fetch strategy depends on the configured `resource_type`:
        - "models"  — list all models (process diagrams) in the repository
        - "symbols" — list all symbols (objects) in the repository
        - "lists"   — execute a pre-defined 2C8 list/query
        - "diagrams" — every model's whole drawing (vertices, edges,
                       descriptions), the current version and the approved one
        """
        repository_id = self.config.get("repository_id", "")
        if not repository_id:
            raise ValueError("repository_id is required for API mode")

        resource_type = self.config.get("resource_type", "models")

        if resource_type == "diagrams":
            async with natverk.klient(timeout=_DIAGRAM_TIMEOUT, verify=self._verify_ssl()) as client:
                return await self._fetch_diagrams(client, repository_id)

        async with natverk.klient(timeout=30.0, verify=self._verify_ssl()) as client:
            if resource_type == "models":
                return await self._fetch_models(client, repository_id)
            elif resource_type == "symbols":
                return await self._fetch_symbols(client, repository_id)
            elif resource_type == "lists":
                return await self._fetch_list(client, repository_id)
            else:
                raise ValueError(f"Unknown resource_type: {resource_type}")

    async def _fetch_models(self, client: httpx.AsyncClient, repo_id: str) -> list[dict]:
        """Fetch all models (process diagrams) from a repository.

        Field mapping vs. the raw 2C8 model:
          - external_id     ← uuid
          - name            ← titles[language_id].title (or first language found)
          - prefix          ← prefix          ("3.3" — the position in the process tree)
          - parent_prefix   ← derived from prefix by stripping the last segment
          - parent_name     ← name of the model whose prefix == parent_prefix
          - model_type      ← modelType        (e.g. PROCESS_MODEL)
          - workflow_state  ← workflowState    (e.g. APPROVED), promoted to
                               "APPROVED" if the current version isn't but an
                               earlier version of the model was (see
                               `_has_approved_version`)
          - current_workflow_state ← workflowState as 2C8 reports it, never
                               promoted — APPROVED only when the current
                               version itself is approved, so consumers can
                               tell a published process from one mid-revision
        """
        configured_lang = self.config.get("language_id") or None

        models = await self._get_paginated(
            client, f"/mt-backend/api/v1/repositories/{repo_id}/models"
        )

        # First pass: pick a name for each model.
        def pick_name(model: dict) -> str:
            titles = model.get("titles") or {}
            if isinstance(titles, dict) and titles:
                if configured_lang and configured_lang in titles:
                    entry = titles[configured_lang]
                else:
                    # Stable choice: first language by sorted key order.
                    first_key = sorted(titles.keys())[0]
                    entry = titles[first_key]
                if isinstance(entry, dict):
                    return entry.get("title") or ""
                return str(entry)
            # Fallback for older / variant shapes.
            return model.get("title") or model.get("name") or ""

        names_by_uuid: dict[str, str] = {}
        prefix_to_name: dict[str, str] = {}
        for m in models:
            name = pick_name(m)
            uuid = m.get("uuid") or ""
            prefix = m.get("prefix") or ""
            if uuid:
                names_by_uuid[uuid] = name
            if prefix:
                prefix_to_name[prefix] = name

        records = []
        for m in models:
            prefix = m.get("prefix") or ""
            parent_prefix = _resolve_parent_prefix(prefix, prefix_to_name)
            uuid = m.get("uuid", "")
            workflow_state = m.get("workflowState", "")

            # `workflowState` here only reflects the model's current/latest
            # version. A model mid-revision (EDITABLE/UNDER_APPROVAL/
            # UNDER_REVISION) can still have an earlier, locked version that
            # was APPROVED and remains the live published process — so it
            # should still be treated as approved rather than dropped.
            if workflow_state != "APPROVED" and uuid:
                if await self._has_approved_version(client, repo_id, uuid):
                    workflow_state = "APPROVED"

            record: dict = {
                "external_id": uuid,
                "name": pick_name(m),
                "prefix": prefix,
                "parent_prefix": parent_prefix,
                "parent_name": prefix_to_name.get(parent_prefix, "") if parent_prefix else "",
                "model_type": m.get("modelType", ""),
                "workflow_state": workflow_state,
                "current_workflow_state": m.get("workflowState", ""),
            }
            records.append(record)
        return records

    async def _has_approved_version(
        self, client: httpx.AsyncClient, repo_id: str, model_uuid: str
    ) -> bool:
        """Check whether any version of a model has ever reached APPROVED.

        2C8 exposes per-version history as a `logItems` log of workflow
        transitions per version; we treat "APPROVED ever appeared" as proof
        that an approved version exists (and is still the published one)
        even if the model has since moved on to a newer, unapproved version.
        """
        versions = await self._get_paginated(
            client, f"/mt-backend/api/v1/repositories/{repo_id}/models/{model_uuid}/versions"
        )
        return any(
            log_item.get("workflowState") == "APPROVED"
            for version in versions
            for log_item in version.get("logItems", [])
        )

    # ── diagrams ──────────────────────────────────────────────────────────

    async def _get_all(
        self, client: httpx.AsyncClient, path: str, *, complete: bool = True
    ) -> list[dict]:
        """A whole list with every field, or an error.

        Unlike `_get_paginated` this refuses a truncated answer: half a drawing
        is worse than none, and the 2C8 backend omits fields without
        `projection=ALL`. `complete=False` is for the version log, where 2C8's
        `total` also counts versions it does not return.
        """
        max_results = int(self.config.get("max_results", _DIAGRAM_MAX_RESULTS))
        resp = await client.get(
            f"{self._base_url()}{path}",
            headers=self._headers(),
            params={"projection": "ALL", "startAt": 0, "maxResults": max_results},
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list):
            return payload
        items = payload.get("data") or payload.get("values") or payload.get("results") or []
        if isinstance(items, dict):
            items = [items]
        total = payload.get("total")
        if complete and isinstance(total, int) and total > len(items):
            raise RuntimeError(
                f"2C8 reports {total} rows for {path} but returned {len(items)}. "
                f"Raise max_results (currently {max_results}) on the connection."
            )
        return items

    async def _fetch_diagrams(self, client: httpx.AsyncClient, repo_id: str) -> list[dict]:
        """Every model's drawing: the current version and the approved one.

        One record per model:
          - external_id, name, prefix, model_type
          - workflow_state      ← the CURRENT version's state, never promoted
          - version             ← the current version number
          - approved_version    ← the latest APPROVED version number, or null
          - approved_is_current ← true when those two are the same version
          - current             ← the current version's diagram
          - approved            ← the approved version's diagram when it is an
                                  OLDER version; null when it is the current
                                  one (read `current`) or when none is approved
          - approved_missing    ← true when an older version is approved but
                                  2C8 no longer returns its rows

        The diagram format is described in `two_c8_diagram.build_export`.
        Config: `model_types` (default PROCESS_MODEL), `prefix_root` (only that
        model and the ones numbered below it), `language_id`, `concurrency`.
        """
        repo = f"/mt-backend/api/v1/repositories/{repo_id}"
        language = self.config.get("language_id") or None
        if not language:
            languages = await self._get_all(client, f"{repo}/languages")
            language = next(
                (l.get("uuid") for l in languages if l.get("defaultLanguage")),
                languages[0].get("uuid") if languages else None,
            )

        all_models = await self._get_all(client, f"{repo}/models")
        if not all_models:
            # Empty is a broken answer, not an empty repository worth mirroring:
            # reporting it would prune every stored diagram.
            raise RuntimeError("2C8 returned no models. Refusing to report an empty result.")

        typer = self.config.get("model_types") or ["PROCESS_MODEL"]
        if isinstance(typer, str):
            typer = [t.strip() for t in typer.split(",") if t.strip()]
        rot = str(self.config.get("prefix_root") or "").strip()

        def vald(m: dict) -> bool:
            if m.get("modelType") not in typer:
                return False
            if not rot:
                return True
            prefix = m.get("prefix") or ""
            return prefix == rot or prefix.startswith(rot + ".")

        models = [m for m in all_models if m.get("uuid") and vald(m)]

        symbols = {
            s["uuid"]: s for s in await self._get_all(client, f"{repo}/symbols") if s.get("uuid")
        }
        layer_types = {
            lt["uuid"]: lt for lt in await self._get_all(client, f"{repo}/layer-types") if lt.get("uuid")
        }

        gate = asyncio.Semaphore(int(self.config.get("concurrency", _DIAGRAM_CONCURRENCY)))

        # symbol uuid → the models it breaks down into. 2C8 stores the relation
        # on the TARGET model, so it can only be read backwards: ask every
        # model what it is broken down from, then invert.
        drilldowns: dict[str, list[dict]] = {}

        async def nedbrytning(m: dict) -> None:
            async with gate:
                rows = await self._get_all(client, f"{repo}/models/{m['uuid']}/broken-down-from")
            for row in rows:
                symbol_uuid = (row.get("symbol") or {}).get("uuid") or row.get("uuid")
                if not symbol_uuid:
                    continue
                drilldowns.setdefault(symbol_uuid, []).append({
                    "model_id": m["uuid"],
                    "name": diagram.title_of(m, language),
                    "prefix": m.get("prefix") or None,
                    "is_primary": bool(row.get("owning")),
                })

        await asyncio.gather(*(nedbrytning(m) for m in all_models if m.get("uuid")))
        for entries in drilldowns.values():
            # The owning model first, then a stable order.
            entries.sort(key=lambda e: (not e["is_primary"], e["prefix"] or "", e["model_id"]))

        async def en(m: dict) -> dict:
            base = f"{repo}/models/{m['uuid']}"
            async with gate:
                vertices = await self._get_all(client, f"{base}/vertices")
                edges = await self._get_all(client, f"{base}/edges")
                descriptions = await self._get_all(client, f"{base}/descriptions")
                model_layers = await self._get_all(client, f"{base}/layers")
                current = int(m.get("version") or 0)
                state = m.get("workflowState") or ""
                # The version log is only needed when the current version is
                # not the approved one and there is an older one to look at.
                versions = (
                    await self._get_all(client, f"{base}/versions", complete=False)
                    if state != diagram.APPROVED and current > 0
                    else []
                )

            approved = diagram.approved_version(m, versions)
            name = diagram.title_of(m, language)
            v_blocks = diagram.split_versions(vertices, "uuid")
            e_blocks = diagram.split_versions(edges, "uuid")
            d_blocks = diagram.split_versions(descriptions, "descriptionType")

            def export(version: int, workflow_state: str) -> dict | None:
                v = diagram.block_for(v_blocks, version, current)
                if v is None:
                    return None
                return diagram.build_export(
                    model=m,
                    name=name,
                    version=version,
                    workflow_state=workflow_state,
                    vertices=v,
                    edges=diagram.block_for(e_blocks, version, current) or [],
                    descriptions=diagram.block_for(d_blocks, version, current) or [],
                    model_layers=model_layers,
                    symbols=symbols,
                    layer_types=layer_types,
                    drilldowns=drilldowns,
                    language=language,
                )

            older = approved is not None and approved != current
            approved_export = export(approved, diagram.APPROVED) if older else None
            return {
                "external_id": m["uuid"],
                "name": name,
                "prefix": m.get("prefix") or "",
                "model_type": m.get("modelType", ""),
                "workflow_state": state,
                "version": current,
                "approved_version": approved,
                "approved_is_current": approved is not None and approved == current,
                "approved_missing": older and approved_export is None,
                "last_modified": m.get("lastModified"),
                "current": export(current, state),
                "approved": approved_export,
            }

        return list(await asyncio.gather(*(en(m) for m in models)))

    async def _fetch_symbols(self, client: httpx.AsyncClient, repo_id: str) -> list[dict]:
        """Fetch all symbols (objects) from a repository."""
        configured_lang = self.config.get("language_id") or None
        symbols = await self._get_paginated(
            client, f"/mt-backend/api/v1/repositories/{repo_id}/symbols"
        )

        def pick_name(s: dict) -> str:
            titles = s.get("titles") or {}
            if isinstance(titles, dict) and titles:
                if configured_lang and configured_lang in titles:
                    entry = titles[configured_lang]
                else:
                    entry = titles[sorted(titles.keys())[0]]
                if isinstance(entry, dict):
                    return entry.get("title") or ""
                return str(entry)
            return s.get("title") or s.get("name") or ""

        records = []
        for s in symbols:
            records.append({
                "external_id": s.get("uuid", ""),
                "name": pick_name(s),
                "symbol_type": s.get("symbolType", ""),
            })
        return records

    async def _fetch_list(self, client: httpx.AsyncClient, repo_id: str) -> list[dict]:
        """Execute a pre-defined 2C8 list and return its results.

        Requires `list_id` in config. Optionally accepts `language_id` and `columns`.
        """
        list_id = self.config.get("list_id", "")
        if not list_id:
            raise ValueError("list_id is required for resource_type 'lists'")

        language_id = self.config.get("language_id")
        columns = self.config.get("columns", [])

        body: dict = {}
        if language_id:
            body["language"] = language_id
        if columns:
            body["columns"] = columns

        resp = await client.post(
            f"{self._base_url()}/mt-backend/api/v1/repositories/{repo_id}/lists/{list_id}/execute",
            headers=self._headers(),
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()

        # Normalise list results into records
        items = data if isinstance(data, list) else data.get("values", data.get("results", []))
        if isinstance(items, dict):
            items = [items]

        records = []
        for item in items:
            record = {
                "external_id": item.get("uuid", item.get("id", "")),
                "name": item.get("title", item.get("name", "")),
                **{k: v for k, v in item.items() if k not in ("uuid", "id")},
            }
            records.append(record)
        return records

    # ── test ──────────────────────────────────────────────────────────────

    async def test_connection(self) -> bool:
        mode = self.config.get("mode", "mock")
        if mode == "mock":
            return True
        try:
            async with natverk.klient(timeout=10.0, verify=self._verify_ssl()) as client:
                # Hit the versions endpoint — lightweight and auth-required
                resp = await client.get(
                    f"{self._base_url()}/mt-backend/api/v1/versions",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ── config schema ─────────────────────────────────────────────────────

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["mock", "api"],
                    "default": "mock",
                    "description": "mock = use seed data, api = connect to 2C8 MT Backend",
                },
                "base_url": {
                    "type": "string",
                    "description": "2C8 server URL, e.g. https://your-2c8-server.com",
                },
                "repository_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID of the 2C8 repository to fetch from",
                },
                "resource_type": {
                    "type": "string",
                    "enum": ["models", "symbols", "lists", "diagrams"],
                    "default": "models",
                    "description": "What to fetch: models (the list of process models), symbols (objects), lists (pre-defined queries), or diagrams (every model's whole drawing: the current version and the approved one)",
                },
                "model_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["PROCESS_MODEL"],
                    "description": "Model types to include (only for resource_type=diagrams)",
                },
                "prefix_root": {
                    "type": "string",
                    "description": "Only the model with this number and the ones below it, e.g. 4.4 (only for resource_type=diagrams)",
                },
                "concurrency": {
                    "type": "integer",
                    "default": _DIAGRAM_CONCURRENCY,
                    "description": "Simultaneous requests to 2C8 (only for resource_type=diagrams)",
                },
                "list_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID of the 2C8 list to execute (only for resource_type=lists)",
                },
                "language_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Optional language UUID for multi-language repositories",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional column names to include in list results",
                },
                "verify_ssl": {
                    "type": "boolean",
                    "default": True,
                    "description": "Verify the server's TLS certificate. Disable only for internal AD-issued self-signed certs.",
                },
                "max_results": {
                    "type": "integer",
                    "default": _DEFAULT_MAX_RESULTS,
                    "description": "Upper bound on rows fetched per call. 2C8's startAt-paging is broken, so we ask for everything in one request.",
                },
            },
        }
