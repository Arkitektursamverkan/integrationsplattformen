"""2C8 diagrams — a model's whole drawing, per version.

The list endpoints the connector reads for `models` and `symbols` say that a
process exists. A consumer that wants to DRAW it needs the diagram: where each
symbol stands (vertices), how they are connected (edges), the descriptions and
which symbols lead down into another model. This module turns 2C8's raw rows
into one self-contained export per model version. Everything here is a pure
function — the HTTP calls live in the connector.

Two properties of the 2C8 MT Backend shape the code:

  * A model's vertices, edges and descriptions come back for EVERY version the
    model has had, one block per version in ascending order, with no version
    field to tell them apart (`symbol.version` is the symbol's own counter). A
    row's key is unique within a version, so a block ends where a key comes
    back. See `split_versions`.
  * `workflowState` on the model only describes the CURRENT version. A model
    under revision usually has an earlier, locked version that was approved
    and is still the one that applies. The per-version log (`logItems`) says
    which. See `approved_version`.
"""
from __future__ import annotations

import html
import re

SEQUENCE_EDGE_TYPES = {"FLOW", "IS_FOLLOWED_BY"}
ROLE_OBJECT_TYPES = {"ROLE", "POSITION", "FORUM"}
APPROVED = "APPROVED"


def title_of(entity: dict, language: str | None) -> str:
    """2C8 keeps titles per language: ``titles[lang] = {"title": ...}``."""
    titles = entity.get("titles") or {}
    if not isinstance(titles, dict) or not titles:
        return ""
    entry = titles.get(language) if language else None
    if entry is None:
        entry = titles[sorted(titles)[0]]
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


def split_versions(rows: list[dict], key: str) -> list[list[dict]]:
    """Split a per-model list into one block per model version, oldest first.

    A new block starts where a key that the current block already holds comes
    back. Rows without the key stay in the block they arrive in.
    """
    blocks: list[list[dict]] = []
    seen: set = set()
    for row in rows:
        k = row.get(key)
        if not blocks or (k is not None and k in seen):
            blocks.append([])
            seen = set()
        if k is not None:
            seen.add(k)
        blocks[-1].append(row)
    return blocks


def block_for(blocks: list[list[dict]], version: int, current_version: int) -> list[dict] | None:
    """The block holding `version`, counted from the END of the list.

    The last block is always the current version; an older version lies as many
    blocks before it as its number is lower. Counting from the end keeps the
    current version right even if 2C8 should ever leave out early blocks.
    Returns None when the list does not reach that far back. A model with no
    rows at all has no blocks; that is an empty drawing, not a missing one.
    """
    if not blocks:
        return [] if version == current_version else None
    index = len(blocks) - 1 - (current_version - version)
    if index < 0 or index >= len(blocks):
        return None
    return blocks[index]


def approved_version(model: dict, versions: list[dict]) -> int | None:
    """The number of the latest APPROVED version of a model, or None.

    The current version is approved exactly when the model's own
    `workflowState` says so — its log may hold an earlier approval that has
    since been withdrawn. An older version is locked, so an APPROVED entry in
    its log stands.
    """
    current = int(model.get("version") or 0)
    if model.get("workflowState") == APPROVED:
        return current
    best: int | None = None
    for v in versions:
        number = v.get("version")
        if not isinstance(number, int) or number >= current:
            continue
        if any(item.get("workflowState") == APPROVED for item in v.get("logItems") or []):
            best = number if best is None else max(best, number)
    return best


def build_export(
    *,
    model: dict,
    name: str,
    version: int,
    workflow_state: str,
    vertices: list[dict],
    edges: list[dict],
    descriptions: list[dict],
    model_layers: list[dict],
    symbols: dict[str, dict],
    layer_types: dict[str, dict],
    drilldowns: dict[str, list[dict]],
    language: str | None,
) -> dict:
    """One model version as a self-contained diagram.

    `nodes[].id` is the vertex uuid — what `edges[].from`/`to` point at. The
    same symbol can stand in several places, so `symbol_id` is not unique.
    `geometry` is 2C8's own coordinates, y growing downwards.
    """
    used_layers = {v.get("layer") for v in vertices if v.get("layer")}
    layers = []
    for layer in model_layers:
        if layer.get("uuid") not in used_layers:
            continue
        lt = layer_types.get(layer.get("layerType") or "", {})
        # Stored as a semicolon-terminated list: "ROLE;POSITION;FORUM;".
        object_types = [t for t in re.split(r"[;,\s]+", str(lt.get("objectTypes") or "")) if t]
        layers.append({
            "id": layer.get("uuid"),
            "name": title_of(lt, language),
            "applies_to_object_types": object_types,
        })

    nodes = []
    for v in vertices:
        symbol_uuid = (v.get("symbol") or {}).get("uuid") or ""
        symbol = symbols.get(symbol_uuid, {})
        # The vertex carries its own title only when the diagram overrides the
        # object's name; otherwise the symbol is the source.
        label = title_of(v, language) or title_of(symbol, language)
        breakdown = drilldowns.get(symbol_uuid) or []
        nodes.append({
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
        })

    by_vertex = {n["id"]: n for n in nodes}

    out_edges = []
    for e in edges:
        labels = e.get("labels") or {}
        entry = (labels.get(language) if language else None) or (
            labels[sorted(labels)[0]] if labels else {}
        )
        edge_type = e.get("edgeType") or ""
        out_edges.append({
            "id": e.get("uuid"),
            "from": e.get("fromVertex"),
            "to": e.get("toVertex"),
            "edge_type": edge_type,
            "label": (entry or {}).get("title") or "" if isinstance(entry, dict) else str(entry or ""),
            "is_sequence": edge_type in SEQUENCE_EDGE_TYPES,
            "waypoints": list(e.get("points") or []),
        })

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
        raci.append({
            "role": role["label"],
            "role_node": role["id"],
            "relation": e["edge_type"][len("RACI_"):],
            "target": target["label"],
            "target_node": target["id"],
            "target_type": target["object_type"],
        })

    def _text(d: dict) -> str:
        content = d.get("content") or {}
        entry = (content.get(language) if language else None) or (
            content[sorted(content)[0]] if content else {}
        )
        return (entry or {}).get("text") or "" if isinstance(entry, dict) else ""

    return {
        "model": {
            "id": model.get("uuid"),
            "name": name,
            "prefix": model.get("prefix") or None,
            "model_type": model.get("modelType"),
            "workflow_state": workflow_state,
            "version": version,
        },
        "descriptions": [
            {"type_id": d.get("descriptionType"), "html": _text(d), "text": html_to_text(_text(d))}
            for d in descriptions
        ],
        "layers": layers,
        "nodes": nodes,
        "edges": out_edges,
        "derived": {"raci": raci},
    }
