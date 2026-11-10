"""Transform engine — chainable data operations for ETL/ELT pipelines.

Each operation takes a list of records (dicts) and returns a transformed list.
Operations are applied in order as pipeline stages.

Supported step types:
  - transform:    Field mappings, filters, computed fields (original)
  - add_column:   Create new columns from expressions/templates/concatenation
  - split_column: Split a field into multiple fields by delimiter
  - rename:       Rename fields
  - remove:       Remove fields
  - replace:      Find/replace in field values
  - substring:    Extract part of a string
  - math:         Arithmetic on numeric fields
  - combine:      Merge multiple fields into one
  - deduplicate:  Remove duplicate records by field(s)
  - sort:         Sort records by field
  - filter:       Filter records by condition
  - lookup:       Map values using a lookup table
"""
from __future__ import annotations

import re
import string
from datetime import datetime
from functools import lru_cache
from html import unescape
from typing import Any


# ── Gränser för användarens regex och mallar ──────────────────────────────────
#
# Stegen körs i en egen tråd (flow_service), så att en långsam regex inte
# hänger händelseloopen. Gränserna här stoppar det som annars kunde ta minnet
# eller tiden: mycket långa mönster och formatfält med enorm bredd ({x:>999999999}).
# Python-modulen re har ingen tidsgräns; paketet regex används inte.

MAX_REGEX_LÄNGD = 500
MAX_MALL_LÄNGD = 5000
MAX_FORMAT_BREDD = 1000


class TransformError(Exception):
    """Ett steg med en inställning som inte godtas. Meddelandet visas i körningen."""


@lru_cache(maxsize=256)
def _regex(mönster: str) -> re.Pattern:
    mönster = str(mönster)
    if len(mönster) > MAX_REGEX_LÄNGD:
        raise TransformError(f"Regex too long (max {MAX_REGEX_LÄNGD} characters)")
    return re.compile(mönster)


_TAL = re.compile(r"\d+")


@lru_cache(maxsize=256)
def _kontrollera_mall(mall: str) -> None:
    """Mallen för add_column/template: inga attribut, inga nästlade fält och
    ingen bredd eller precision över MAX_FORMAT_BREDD."""
    if len(mall) > MAX_MALL_LÄNGD:
        raise TransformError(f"Template too long (max {MAX_MALL_LÄNGD} characters)")
    try:
        delar = list(string.Formatter().parse(mall))
    except ValueError as e:
        raise TransformError(f"Invalid template: {e}") from e
    for _text, fält, spec, _konv in delar:
        if fält is None:
            continue
        if "." in fält:
            raise TransformError("Template fields may not use attribute access")
        if spec:
            if "{" in spec:
                raise TransformError("Template format specs may not contain fields")
            if any(int(t) > MAX_FORMAT_BREDD for t in _TAL.findall(spec)):
                raise TransformError(f"Template format width/precision over {MAX_FORMAT_BREDD}")


# ── Value transforms (used by field mappings) ─────────────────────────────────

_TRANSFORMS: dict[str, callable] = {
    "strip_html": lambda v: re.sub(r"<[^>]+>", "", unescape(str(v))) if v else v,
    "to_string": lambda v: str(v) if v is not None else "",
    "to_int": lambda v: int(float(v)) if v is not None else 0,
    "to_float": lambda v: float(v) if v is not None else 0.0,
    "to_lower": lambda v: str(v).lower() if v else v,
    "to_upper": lambda v: str(v).upper() if v else v,
    "trim": lambda v: str(v).strip() if v else v,
    "date_parse": lambda v: datetime.fromisoformat(str(v)).isoformat() if v else None,
    "to_bool": lambda v: str(v).lower() in ("true", "1", "yes", "ja") if v is not None else False,
}


def _get_nested(record: dict, path: str) -> Any:
    """Get a value from a nested dict using dot notation."""
    if not path:
        return None
    current = record
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


# ── Filter operators ──────────────────────────────────────────────────────────

def _eval_filter(value: Any, operator: str, target: Any) -> bool:
    try:
        if operator == "eq":
            return _safe_str(value) == _safe_str(target)
        elif operator == "neq":
            return _safe_str(value) != _safe_str(target)
        elif operator == "gt":
            return value is not None and float(value) > float(target)
        elif operator == "lt":
            return value is not None and float(value) < float(target)
        elif operator == "gte":
            return value is not None and float(value) >= float(target)
        elif operator == "lte":
            return value is not None and float(value) <= float(target)
        elif operator == "contains":
            return _safe_str(target).lower() in _safe_str(value).lower()
        elif operator == "not_contains":
            return _safe_str(target).lower() not in _safe_str(value).lower()
        elif operator == "starts_with":
            return _safe_str(value).lower().startswith(_safe_str(target).lower())
        elif operator == "ends_with":
            return _safe_str(value).lower().endswith(_safe_str(target).lower())
        elif operator == "in":
            return value in target if isinstance(target, list) else False
        elif operator == "regex":
            return bool(_regex(str(target)).search(str(value))) if value else False
        elif operator == "exists":
            return value is not None and value != ""
        elif operator == "not_exists":
            return value is None or value == ""
        elif operator == "is_empty":
            return value is None or value == "" or value == 0
        elif operator == "is_not_empty":
            return value is not None and value != "" and value != 0
    except (ValueError, TypeError):
        return False
    return True


# ── Operation: transform (original — field mappings + filters + computed) ─────

def apply_mappings(records: list[dict], mappings: list[dict]) -> list[dict]:
    if not mappings:
        return records
    result = []
    for record in records:
        mapped = {}
        for m in mappings:
            source = m.get("source_field", "")
            target = m.get("target_field", source)
            transform_fn = m.get("transform")
            value = _get_nested(record, source)
            if transform_fn and transform_fn in _TRANSFORMS:
                value = _TRANSFORMS[transform_fn](value)
            mapped[target] = value
        result.append(mapped)
    return result


def apply_filters(records: list[dict], filters: list[dict]) -> list[dict]:
    if not filters:
        return records
    return [
        r for r in records
        if all(
            _eval_filter(_get_nested(r, f.get("field", "")), f.get("operator", "eq"), f.get("value"))
            for f in filters
        )
    ]


def apply_computed_fields(records: list[dict], computed: list[dict]) -> list[dict]:
    if not computed:
        return records
    for record in records:
        for c in computed:
            record[c["field"]] = c["value"]
    return records


# ── Operation: add_column ─────────────────────────────────────────────────────

def op_add_column(records: list[dict], config: dict) -> list[dict]:
    """Add a new column to every record.

    Config:
      column: str          — new field name
      mode: str            — "template", "concat", "copy", "static", "conditional"
      template: str        — template string with {field_name} placeholders (mode=template)
      fields: list[str]    — fields to concatenate (mode=concat)
      separator: str       — separator for concat (default: " ")
      source_field: str    — field to copy from (mode=copy)
      value: str           — static value (mode=static)
      condition_field: str — field to check (mode=conditional)
      condition_op: str    — operator (mode=conditional)
      condition_value: str — value to compare (mode=conditional)
      true_value: str      — value if condition is true
      false_value: str     — value if condition is false
    """
    column = config.get("column", "")
    mode = config.get("mode", "static")

    for record in records:
        if mode == "static":
            record[column] = config.get("value", "")

        elif mode == "template":
            template = config.get("template", "")
            _kontrollera_mall(str(template))
            try:
                record[column] = template.format(**{k: _safe_str(v) for k, v in record.items()})
            except (KeyError, IndexError):
                record[column] = template

        elif mode == "concat":
            fields = config.get("fields", [])
            sep = config.get("separator", " ")
            parts = [_safe_str(record.get(f, "")) for f in fields]
            record[column] = sep.join(p for p in parts if p)

        elif mode == "copy":
            record[column] = _get_nested(record, config.get("source_field", ""))

        elif mode == "conditional":
            field_val = _get_nested(record, config.get("condition_field", ""))
            op = config.get("condition_op", "exists")
            cond_val = config.get("condition_value", "")
            if _eval_filter(field_val, op, cond_val):
                record[column] = config.get("true_value", "")
            else:
                record[column] = config.get("false_value", "")

    return records


# ── Operation: split_column ───────────────────────────────────────────────────

def op_split_column(records: list[dict], config: dict) -> list[dict]:
    """Split a field into multiple fields by delimiter.

    Config:
      source_field: str     — field to split
      delimiter: str        — split delimiter (default: ",")
      target_fields: list   — names for each resulting part
      keep_source: bool     — keep the original field (default: true)
    """
    source = config.get("source_field", "")
    delimiter = config.get("delimiter", ",")
    targets = config.get("target_fields", [])
    keep = config.get("keep_source", True)

    for record in records:
        value = _safe_str(record.get(source, ""))
        parts = value.split(delimiter)
        for i, target in enumerate(targets):
            record[target] = parts[i].strip() if i < len(parts) else ""
        if not keep and source in record:
            del record[source]

    return records


# ── Operation: rename ─────────────────────────────────────────────────────────

def op_rename(records: list[dict], config: dict) -> list[dict]:
    """Rename fields.

    Config:
      renames: list of {"from": "old_name", "to": "new_name"}
    """
    renames = config.get("renames", [])
    for record in records:
        for r in renames:
            old = r.get("from", "")
            new = r.get("to", "")
            if old in record and old != new:
                record[new] = record.pop(old)
    return records


# ── Operation: remove ─────────────────────────────────────────────────────────

def op_remove(records: list[dict], config: dict) -> list[dict]:
    """Remove fields from records.

    Config:
      fields: list[str]  — fields to remove
    """
    fields = set(config.get("fields", []))
    return [{k: v for k, v in r.items() if k not in fields} for r in records]


# ── Operation: replace ────────────────────────────────────────────────────────

def op_replace(records: list[dict], config: dict) -> list[dict]:
    """Find/replace in field values.

    Config:
      field: str          — field to modify
      find: str           — text to find
      replace_with: str   — replacement text
      use_regex: bool     — treat find as regex (default: false)
    """
    field = config.get("field", "")
    find = config.get("find", "")
    replace_with = config.get("replace_with", "")
    use_regex = config.get("use_regex", False)

    for record in records:
        if field in record and record[field] is not None:
            val = _safe_str(record[field])
            if use_regex:
                record[field] = _regex(find).sub(replace_with, val)
            else:
                record[field] = val.replace(find, replace_with)
    return records


# ── Operation: substring ──────────────────────────────────────────────────────

def op_substring(records: list[dict], config: dict) -> list[dict]:
    """Extract part of a string.

    Config:
      field: str           — field to extract from
      target_field: str    — where to put the result (default: overwrites source)
      start: int           — start index (default: 0)
      end: int|null        — end index (default: None = to end)
      regex: str           — extract via regex group instead of start/end
    """
    field = config.get("field", "")
    target = config.get("target_field", field)
    regex_pattern = config.get("regex", "")

    for record in records:
        val = _safe_str(record.get(field, ""))
        if regex_pattern:
            m = _regex(regex_pattern).search(val)
            record[target] = m.group(1) if m and m.groups() else (m.group(0) if m else "")
        else:
            start = config.get("start", 0)
            end = config.get("end")
            record[target] = val[start:end]
    return records


# ── Operation: math ───────────────────────────────────────────────────────────

def op_math(records: list[dict], config: dict) -> list[dict]:
    """Arithmetic on numeric fields.

    Config:
      target_field: str   — where to store the result
      operation: str      — "add", "subtract", "multiply", "divide", "round", "abs", "percent"
      field_a: str        — first operand field
      field_b: str        — second operand field (not needed for round/abs)
      value: float        — constant operand (alternative to field_b)
      decimals: int       — decimal places for round (default: 0)
    """
    target = config.get("target_field", "")
    operation = config.get("operation", "add")

    for record in records:
        try:
            a = float(record.get(config.get("field_a", ""), 0) or 0)
            b_field = config.get("field_b", "")
            b = float(record.get(b_field, 0) or 0) if b_field else float(config.get("value", 0))

            if operation == "add":
                record[target] = a + b
            elif operation == "subtract":
                record[target] = a - b
            elif operation == "multiply":
                record[target] = a * b
            elif operation == "divide":
                record[target] = a / b if b != 0 else None
            elif operation == "round":
                decimals = config.get("decimals", 0)
                record[target] = round(a, decimals)
            elif operation == "abs":
                record[target] = abs(a)
            elif operation == "percent":
                record[target] = (a / b * 100) if b != 0 else None
            elif operation == "min":
                record[target] = min(a, b)
            elif operation == "max":
                record[target] = max(a, b)
        except (ValueError, TypeError):
            record[target] = None

    return records


# ── Operation: combine ────────────────────────────────────────────────────────

def op_combine(records: list[dict], config: dict) -> list[dict]:
    """Merge multiple fields into one (alias for add_column concat mode)."""
    return op_add_column(records, {**config, "mode": "concat", "column": config.get("target_field", "combined")})


# ── Operation: deduplicate ────────────────────────────────────────────────────

def op_deduplicate(records: list[dict], config: dict) -> list[dict]:
    """Remove duplicate records based on field(s).

    Config:
      fields: list[str]  — fields to check for uniqueness
      keep: str           — "first" or "last" (default: "first")
    """
    fields = config.get("fields", [])
    keep = config.get("keep", "first")

    if not fields:
        return records

    seen: dict[tuple, int] = {}
    for i, record in enumerate(records):
        key = tuple(_safe_str(record.get(f, "")) for f in fields)
        if key not in seen:
            seen[key] = i
        elif keep == "last":
            seen[key] = i

    indices = sorted(seen.values())
    return [records[i] for i in indices]


# ── Operation: sort ───────────────────────────────────────────────────────────

def op_sort(records: list[dict], config: dict) -> list[dict]:
    """Sort records by field.

    Config:
      field: str         — field to sort by
      ascending: bool    — sort direction (default: true)
      numeric: bool      — sort as numbers (default: false)
    """
    field = config.get("field", "")
    ascending = config.get("ascending", True)
    numeric = config.get("numeric", False)

    def sort_key(r: dict) -> Any:
        v = r.get(field, "")
        if numeric:
            try:
                return float(v) if v else 0
            except (ValueError, TypeError):
                return 0
        return _safe_str(v).lower()

    return sorted(records, key=sort_key, reverse=not ascending)


# ── Operation: lookup ─────────────────────────────────────────────────────────

def op_lookup(records: list[dict], config: dict) -> list[dict]:
    """Map values using a lookup table.

    Config:
      field: str                       — field to look up
      target_field: str                — where to put the result (default: overwrites field)
      mapping: dict[str, str]          — value → replacement mapping
      default: str|null                — value if not found in mapping (default: keep original)
    """
    field = config.get("field", "")
    target = config.get("target_field", field)
    mapping = config.get("mapping", {})
    default = config.get("default")

    for record in records:
        val = _safe_str(record.get(field, ""))
        if val in mapping:
            record[target] = mapping[val]
        elif default is not None:
            record[target] = default
        elif target != field:
            record[target] = record.get(field)

    return records


# ── Operation registry ────────────────────────────────────────────────────────

def op_trim(records: list[dict], config: dict) -> list[dict]:
    """Trim whitespace from field values.

    Config:
      fields: list[str] | None  — specific fields to trim (default: all string fields)
    """
    target_fields = config.get("fields") or None

    for record in records:
        for key in (target_fields or list(record.keys())):
            if key in record and isinstance(record[key], str):
                record[key] = record[key].strip()
    return records


OPERATIONS: dict[str, callable] = {
    "add_column": op_add_column,
    "split_column": op_split_column,
    "rename": op_rename,
    "remove": op_remove,
    "replace": op_replace,
    "substring": op_substring,
    "math": op_math,
    "combine": op_combine,
    "deduplicate": op_deduplicate,
    "sort": op_sort,
    "filter": lambda records, config: apply_filters(records, config.get("filters", [])),
    "lookup": op_lookup,
    "trim": op_trim,
}


# ── Public API ────────────────────────────────────────────────────────────────

def transform(records: list[dict], step_config: dict) -> list[dict]:
    """Apply the original transform step: mappings -> filters -> computed fields."""
    records = apply_mappings(records, step_config.get("mappings", []))
    records = apply_filters(records, step_config.get("filters", []))
    records = apply_computed_fields(records, step_config.get("computed_fields", []))
    return records


def apply_operation(records: list[dict], step_type: str, config: dict) -> list[dict]:
    """Apply a single pipeline operation."""
    if step_type == "transform":
        return transform(records, config)
    op_fn = OPERATIONS.get(step_type)
    if op_fn:
        return op_fn(records, config)
    return records


def apply_operations(records: list[dict], steps: list[tuple[str, dict]]) -> list[dict]:
    """Alla steg i ordning. Synkron – anropas i en tråd (anyio.to_thread), så
    att ett långsamt steg inte hänger händelseloopen."""
    for step_type, config in steps:
        records = apply_operation(records, step_type, config)
    return records
