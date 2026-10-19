"""Pull a subtree of 2C8 process models as self-contained export files.

The 2C8 connector fetches *lists* (models, symbols) for the EA sync. Arkitekten
needs something else: one file per model holding the whole diagram — vertices,
edges, layers, descriptions — in the 2C8 export format Arkitekten
documents. That shape is what ``importera-2c8.mts`` reads
and what ``POST /api/scen/2c8`` transforms into a drawable scene.

This script produces exactly those files. It runs inside the api container so
the stored 2C8 connection supplies base_url, repository and API key — the key
is decrypted server-side and never printed or written to disk.

    PYTHONPATH=/app python scripts/hamta_2c8_uttag.py --prefix 4.4 --out /tmp/uttag

``--prefix P`` selects the model numbered ``P`` and everything below it
(``P.1``, ``P.1.2``, …); add ``--exact`` for that one model only. Only the
model's CURRENT version is exported – see ``latest_version``. Read-only: only GET requests are made.

Two traps the 2C8 MT Backend sets, both handled here: ``maxResults`` defaults
to 10, and without ``projection=ALL`` fields are silently omitted.
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
from pathlib import Path

import httpx
from sqlalchemy import select

from app.database import async_session
from app.models.connection import ConnectionORM
from app.services.crypto_service import decrypt_credentials

API = "/mt-backend/api/v1"

# One request per list endpoint — 2C8's `startAt` offset is broken (anything
# above 0 returns nothing), so everything has to fit in a single response.
MAX_RESULTS = 20000

# `broken-down-from` can only be read backwards (per target model), so the
# drill-down map costs one request per model in the repository. Bounded so we
# don't flood a single 2C8 server.
CONCURRENCY = 8

SEQUENCE_EDGE_TYPES = {"FLOW", "IS_FOLLOWED_BY"}
ROLE_OBJECT_TYPES = {"ROLE", "POSITION", "FORUM"}


# ── connection ───────────────────────────────────────────────────────────────

async def load_connection(name: str | None) -> tuple[dict, dict]:
    """Read the stored 2C8 connection: config plus decrypted credentials."""
    async with async_session() as db:
        q = select(ConnectionORM).where(ConnectionORM.connector_type == "2c8")
        if name:
            q = q.where(ConnectionORM.name == name)
        row = (await db.execute(q)).scalars().first()
        if row is None:
            raise SystemExit("No 2c8 connection found in the Integration Platform.")
        if row.config.get("mode") != "api":
            raise SystemExit(
                f"Connection {row.name!r} is in mode {row.config.get('mode')!r}; "
                "this script needs mode 'api'."
            )
        creds = decrypt_credentials(row.credentials_encrypted) if row.credentials_encrypted else {}
        return dict(row.config), creds


# ── small helpers ────────────────────────────────────────────────────────────

def title_of(entity: dict, language: str) -> str:
    """2C8 keeps titles per language: ``titles[lang] = {"title": ...}``."""
    titles = entity.get("titles") or {}
    if not isinstance(titles, dict) or not titles:
        return ""
    entry = titles.get(language) or titles[sorted(titles)[0]]
    if isinstance(entry, dict):
        return entry.get("title") or ""
    return str(entry)


def html_to_text(raw: str) -> str:
    """Flatten 2C8's stored HTML description into readable plain text."""
    if not raw:
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def slug(text: str) -> str:
    """Filename slug: every character outside [a-z0-9] becomes a dash.

    Deliberately the same rule the first hand-made export used, so a re-export
    lands on the existing filenames instead of creating near-duplicates.
    """
    return re.sub(r"[^a-z0-9]", "-", text.lower())


def latest_version(rows: list[dict], key: str) -> tuple[list[dict], int]:
    """Keep only the rows of the model's CURRENT version.

    2C8 returns a model's vertices, edges and descriptions for EVERY version
    it has had, one block per version in ascending order, with no version
    field to tell them apart (``symbol.version`` is the symbol's own counter,
    not the model's). A row's uuid is unique within a version, so a block
    ends where a uuid comes back. Keeping them all gave Arkitekten several
    drawings on top of each other: 2.2.1 came out as 1 250 vertices for 130
    objects, each with up to seven positions and names.

    Returns the last block and the number of blocks seen.
    """
    blocks: list[list[dict]] = []
    seen: set = set()
    for r in rows:
        k = r.get(key)
        if not blocks or k in seen:
            blocks.append([])
            seen = set()
        seen.add(k)
        blocks[-1].append(r)
    return (blocks[-1] if blocks else []), len(blocks)


def in_subtree(prefix: str, root: str) -> bool:
    return bool(prefix) and (prefix == root or prefix.startswith(root + "."))


# ── fetching ─────────────────────────────────────────────────────────────────

class C8Client:
    def __init__(self, client: httpx.AsyncClient, base: str, repo: str, headers: dict):
        self.client = client
        self.base = base
        self.repo = repo
        self.headers = headers

    async def get(self, path: str) -> object:
        resp = await self.client.get(
            f"{self.base}{API}{path}",
            headers=self.headers,
            params={"projection": "ALL", "startAt": 0, "maxResults": MAX_RESULTS},
        )
        resp.raise_for_status()
        return resp.json()

    async def list(self, path: str) -> list[dict]:
        payload = await self.get(path)
        if isinstance(payload, list):
            return payload
        items = payload.get("data") or payload.get("values") or payload.get("results") or []
        total = payload.get("total")
        if isinstance(total, int) and total > len(items):
            raise SystemExit(
                f"{path}: server reports {total} rows but returned {len(items)}. "
                f"Raise MAX_RESULTS (currently {MAX_RESULTS})."
            )
        return items

    def repo_path(self, tail: str) -> str:
        return f"/repositories/{self.repo}{tail}"


async def drilldown_map(c8: C8Client, models: list[dict]) -> dict[str, list[dict]]:
    """symbol uuid → the models it breaks down into.

    2C8 stores the break-down relation on the *target* model, so it can only be
    read backwards: ask every model what it is broken down from, then invert.
    """
    gate = asyncio.Semaphore(CONCURRENCY)
    mapping: dict[str, list[dict]] = {}

    async def one(model: dict) -> None:
        async with gate:
            rows = await c8.list(c8.repo_path(f"/models/{model['uuid']}/broken-down-from"))
        for row in rows:
            symbol_uuid = (row.get("symbol") or {}).get("uuid") or row.get("uuid")
            if not symbol_uuid:
                continue
            mapping.setdefault(symbol_uuid, []).append(
                {
                    "model_id": model["uuid"],
                    "name": model["name"],
                    "prefix": model.get("prefix") or None,
                    "is_primary": bool(row.get("owning")),
                }
            )

    await asyncio.gather(*(one(m) for m in models))
    # A symbol owned by one model and reused by others: the owning entry first,
    # so picking [0] gives the diagram that actually defines the breakdown.
    for entries in mapping.values():
        entries.sort(key=lambda e: not e["is_primary"])
    return mapping


async def build_export(
    c8: C8Client,
    model: dict,
    symbols: dict[str, dict],
    language: str,
    layer_types: dict[str, dict],
    drilldowns: dict[str, list[dict]],
) -> dict:
    model_id = model["uuid"]
    vertices, edges, descriptions, model_layers = await asyncio.gather(
        c8.list(c8.repo_path(f"/models/{model_id}/vertices")),
        c8.list(c8.repo_path(f"/models/{model_id}/edges")),
        c8.list(c8.repo_path(f"/models/{model_id}/descriptions")),
        c8.list(c8.repo_path(f"/models/{model_id}/layers")),
    )

    # Only the current version – see latest_version. The block count must match
    # the model's version number; if 2C8 ever breaks that, say so rather than
    # silently exporting a drawing that may be the wrong one.
    vertices, v_blocks = latest_version(vertices, "uuid")
    edges, e_blocks = latest_version(edges, "uuid")
    descriptions, _ = latest_version(descriptions, "descriptionType")
    expected = (model.get("version") or 0) + 1
    if v_blocks != expected or (edges and e_blocks != expected):
        print(
            f"  ! {model.get('prefix')}: {v_blocks} vertex / {e_blocks} edge blocks, "
            f"model version {expected - 1} – kept the last block"
        )
    used_layers = {v.get("layer") for v in vertices if v.get("layer")}
    model_layers = [l for l in model_layers if l.get("uuid") in used_layers]

    layers = []
    for layer in model_layers:
        lt = layer_types.get(layer.get("layerType") or "", {})
        # 2C8 stores these as a semicolon-terminated list: "ROLE;POSITION;FORUM;".
        object_types = [t for t in re.split(r"[;,\s]+", str(lt.get("objectTypes") or "")) if t]
        layers.append(
            {
                "id": layer.get("uuid"),
                "name": title_of(lt, language),
                "applies_to_object_types": object_types,
            }
        )

    nodes = []
    for v in vertices:
        symbol_uuid = (v.get("symbol") or {}).get("uuid") or ""
        symbol = symbols.get(symbol_uuid, {})
        # The vertex carries its own title only when the diagram overrides the
        # object's name; otherwise the symbol is the source.
        label = title_of(v, language) or title_of(symbol, language)
        breakdown = drilldowns.get(symbol_uuid) or []
        nodes.append(
            {
                "id": v.get("uuid"),
                "symbol_id": symbol_uuid,
                "label": label,
                "object_type": symbol.get("objectType") or "",
                "geometry": {
                    "x": v.get("x"),
                    "y": v.get("y"),
                    "width": v.get("width"),
                    "height": v.get("height"),
                    "z": v.get("zOrder"),
                },
                "layer_id": v.get("layer"),
                "drilldown": breakdown[0] if breakdown else None,
                "symbol_created": symbol.get("created"),
                "symbol_last_modified": symbol.get("lastModified"),
            }
        )

    by_vertex = {n["id"]: n for n in nodes}

    out_edges = []
    for e in edges:
        labels = e.get("labels") or {}
        entry = labels.get(language) or (labels[sorted(labels)[0]] if labels else {})
        edge_type = e.get("edgeType") or ""
        out_edges.append(
            {
                "id": e.get("uuid"),
                "from": e.get("fromVertex"),
                "to": e.get("toVertex"),
                "edge_type": edge_type,
                "label": (entry or {}).get("title") or "",
                "is_sequence": edge_type in SEQUENCE_EDGE_TYPES,
                "waypoints": list(e.get("points") or []),
            }
        )

    object_type_counts: dict[str, int] = {}
    for n in nodes:
        object_type_counts[n["object_type"]] = object_type_counts.get(n["object_type"], 0) + 1
    edge_type_counts: dict[str, int] = {}
    for e in out_edges:
        edge_type_counts[e["edge_type"]] = edge_type_counts.get(e["edge_type"], 0) + 1

    raci = []
    for e in out_edges:
        if not e["edge_type"].startswith("RACI_"):
            continue
        a, b = by_vertex.get(e["from"]), by_vertex.get(e["to"])
        if not a or not b:
            continue
        role, target = (a, b) if a["object_type"] in ROLE_OBJECT_TYPES else (b, a)
        if role["object_type"] not in ROLE_OBJECT_TYPES:
            continue
        raci.append(
            {
                "role": role["label"],
                "role_node": role["id"],
                "relation": e["edge_type"][len("RACI_"):],
                "target": target["label"],
                "target_node": target["id"],
                "target_type": target["object_type"],
            }
        )

    return {
        "_note": "Exported read-only from the 2C8 MT Backend REST API. See README.md.",
        "source": {
            "base_url": c8.base,
            "repository_id": c8.repo,
            "model_id": model_id,
            "api": API,
        },
        "model": {
            "id": model_id,
            "name": model["name"],
            "prefix": model.get("prefix"),
            "model_type": model.get("modelType"),
            "workflow_state": model.get("workflowState"),
            "version": model.get("version"),
            "created": model.get("created"),
            "last_modified": model.get("lastModified"),
        },
        "descriptions": [
            {
                "type_id": d.get("descriptionType"),
                "type_name": "",
                "html": ((d.get("content") or {}).get(language) or {}).get("text") or "",
                "text": html_to_text(
                    ((d.get("content") or {}).get(language) or {}).get("text") or ""
                ),
            }
            for d in descriptions
        ],
        "layers": layers,
        "nodes": nodes,
        "edges": out_edges,
        "derived": {
            "object_type_counts": object_type_counts,
            "edge_type_counts": edge_type_counts,
            "raci": raci,
        },
    }


# ── main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prefix", required=True, help="Root of the subtree to export, e.g. 4.4")
    ap.add_argument("--out", required=True, help="Directory to write flow_*.json into")
    ap.add_argument(
        "--exact",
        action="store_true",
        help="Only the model numbered PREFIX, not the models below it",
    )
    ap.add_argument("--connection", default=None, help="Connection name (default: the 2c8 one)")
    args = ap.parse_args()

    config, creds = await load_connection(args.connection)
    base = str(config["base_url"]).rstrip("/")
    repo = str(config["repository_id"])
    verify = config.get("verify_ssl", True)
    if isinstance(verify, str):
        verify = verify.lower() not in ("false", "0", "no", "off")

    headers = {"Accept": "application/json", "X-API-Key": creds.get("api_key", "")}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=180.0, verify=bool(verify)) as client:
        c8 = C8Client(client, base, repo, headers)

        languages = await c8.list(c8.repo_path("/languages"))
        language = next(
            (l["uuid"] for l in languages if l.get("defaultLanguage")),
            languages[0]["uuid"] if languages else "",
        )

        raw_models = await c8.list(c8.repo_path("/models"))
        models = [
            {**m, "name": title_of(m, language)}
            for m in raw_models
        ]
        chosen = sorted(
            (
                m
                for m in models
                if ((m.get("prefix") or "") == args.prefix if args.exact else in_subtree(m.get("prefix") or "", args.prefix))
            ),
            key=lambda m: [int(p) if p.isdigit() else p for p in m["prefix"].split(".")],
        )
        if not chosen:
            raise SystemExit(f"No models with prefix {args.prefix} or below it.")
        print(f"{len(chosen)} model(s) under {args.prefix}:")
        for m in chosen:
            print(f"  {m['prefix']}  {m['name']}  [{m.get('workflowState')}]")

        raw_symbols = await c8.list(c8.repo_path("/symbols"))
        symbols = {s["uuid"]: s for s in raw_symbols if s.get("uuid")}
        layer_types = {lt["uuid"]: lt for lt in await c8.list(c8.repo_path("/layer-types"))}

        print(f"\nMapping drill-downs across {len(models)} models…")
        drilldowns = await drilldown_map(c8, models)

        manifest_flows = []
        for m in chosen:
            export = await build_export(c8, m, symbols, language, layer_types, drilldowns)
            # `4.4.1` → `4_4_1`, matching the existing export's filenames.
            filename = f"flow_{re.sub(r'[^0-9a-z]', '_', m['prefix'].lower())}_{slug(m['name'])}.json"
            (out_dir / filename).write_text(
                json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            manifest_flows.append(
                {
                    "file": filename,
                    "prefix": m["prefix"],
                    "name": m["name"],
                    "workflow_state": export["model"]["workflow_state"],
                    "nodes": len(export["nodes"]),
                    "edges": len(export["edges"]),
                    "drilldowns": sum(1 for n in export["nodes"] if n["drilldown"]),
                }
            )
            print(
                f"  → {filename}  {len(export['nodes'])} nodes / {len(export['edges'])} edges"
                f" / {manifest_flows[-1]['drilldowns']} drill-downs"
            )

        (out_dir / "manifest.json").write_text(
            json.dumps(
                {"exported_from": base, "repository_id": repo, "flows": manifest_flows},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n{len(manifest_flows)} file(s) + manifest.json written to {out_dir}")


asyncio.run(main())
