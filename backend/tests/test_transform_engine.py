"""Tests for the transform engine — all pipeline operations."""
import pytest
from app.services.transform_engine import apply_operation


# ── Transform (field mapping) ────────────────────────────────────────────────

class TestTransformOperation:
    def test_field_mapping(self):
        records = [{"first_name": "Alice", "last_name": "Smith", "age": "30"}]
        result = apply_operation(records, "transform", {
            "mappings": [
                {"source_field": "first_name", "target_field": "name"},
                {"source_field": "age", "target_field": "age", "transform": "to_int"},
            ],
        })
        assert len(result) == 1
        assert result[0]["name"] == "Alice"
        assert result[0]["age"] == 30

    def test_computed_fields(self):
        records = [{"x": 1}]
        result = apply_operation(records, "transform", {
            "mappings": [{"source_field": "x", "target_field": "x"}],
            "computed_fields": [{"field": "source", "value": "test"}],
        })
        assert result[0]["source"] == "test"

    def test_strip_html_transform(self):
        records = [{"desc": "<p>Hello <b>World</b></p>"}]
        result = apply_operation(records, "transform", {
            "mappings": [{"source_field": "desc", "target_field": "desc", "transform": "strip_html"}],
        })
        assert result[0]["desc"] == "Hello World"


# ── Filter ───────────────────────────────────────────────────────────────────

class TestFilterOperation:
    def test_equals(self):
        records = [{"status": "active"}, {"status": "inactive"}, {"status": "active"}]
        result = apply_operation(records, "filter", {
            "filters": [{"field": "status", "operator": "eq", "value": "active"}],
        })
        assert len(result) == 2

    def test_contains(self):
        records = [{"name": "Alice B"}, {"name": "Bob C"}, {"name": "Alice D"}]
        result = apply_operation(records, "filter", {
            "filters": [{"field": "name", "operator": "contains", "value": "Alice"}],
        })
        assert len(result) == 2

    def test_gt(self):
        records = [{"age": 20}, {"age": 30}, {"age": 10}]
        result = apply_operation(records, "filter", {
            "filters": [{"field": "age", "operator": "gt", "value": "15"}],
        })
        assert len(result) == 2

    def test_exists(self):
        records = [{"name": "Alice"}, {"name": ""}, {"other": "x"}]
        result = apply_operation(records, "filter", {
            "filters": [{"field": "name", "operator": "exists"}],
        })
        assert len(result) == 1
        assert result[0]["name"] == "Alice"


# ── Add Column ───────────────────────────────────────────────────────────────

class TestAddColumn:
    def test_static_value(self):
        records = [{"x": 1}]
        result = apply_operation(records, "add_column", {
            "column": "source", "mode": "static", "value": "test",
        })
        assert result[0]["source"] == "test"

    def test_copy_mode(self):
        records = [{"name": "Alice"}]
        result = apply_operation(records, "add_column", {
            "column": "display_name", "mode": "copy", "source_field": "name",
        })
        assert result[0]["display_name"] == "Alice"

    def test_template_mode(self):
        records = [{"first": "Alice", "last": "Smith"}]
        result = apply_operation(records, "add_column", {
            "column": "full", "mode": "template", "template": "{first} {last}",
        })
        assert result[0]["full"] == "Alice Smith"


# ── Remove ───────────────────────────────────────────────────────────────────

class TestRemove:
    def test_remove_fields(self):
        records = [{"a": 1, "b": 2, "c": 3}]
        result = apply_operation(records, "remove", {"fields": ["b", "c"]})
        assert result[0] == {"a": 1}


# ── Rename ───────────────────────────────────────────────────────────────────

class TestRename:
    def test_rename_fields(self):
        records = [{"old_name": "Alice"}]
        result = apply_operation(records, "rename", {
            "renames": [{"from": "old_name", "to": "new_name"}],
        })
        assert "new_name" in result[0]
        assert "old_name" not in result[0]


# ── Sort ─────────────────────────────────────────────────────────────────────

class TestSort:
    def test_sort_ascending(self):
        records = [{"n": "c"}, {"n": "a"}, {"n": "b"}]
        result = apply_operation(records, "sort", {"field": "n", "ascending": True})
        assert [r["n"] for r in result] == ["a", "b", "c"]

    def test_sort_descending(self):
        records = [{"n": "c"}, {"n": "a"}, {"n": "b"}]
        result = apply_operation(records, "sort", {"field": "n", "ascending": False})
        assert [r["n"] for r in result] == ["c", "b", "a"]


# ── Deduplicate ──────────────────────────────────────────────────────────────

class TestDeduplicate:
    def test_dedup_by_field(self):
        records = [{"id": 1, "v": "a"}, {"id": 1, "v": "b"}, {"id": 2, "v": "c"}]
        result = apply_operation(records, "deduplicate", {"fields": ["id"], "keep": "first"})
        assert len(result) == 2
        assert result[0]["v"] == "a"


# ── Replace ──────────────────────────────────────────────────────────────────

class TestReplace:
    def test_find_replace(self):
        records = [{"text": "Hello World"}]
        result = apply_operation(records, "replace", {
            "field": "text", "find": "World", "replace_with": "Python",
        })
        assert result[0]["text"] == "Hello Python"


# ── Combine ──────────────────────────────────────────────────────────────────

class TestCombine:
    def test_combine_fields(self):
        records = [{"a": "Hello", "b": "World"}]
        result = apply_operation(records, "combine", {
            "fields": ["a", "b"], "target_field": "full", "separator": " ",
        })
        assert result[0]["full"] == "Hello World"


# ── Lookup ───────────────────────────────────────────────────────────────────

class TestLookup:
    def test_lookup_mapping(self):
        records = [{"status": "1"}, {"status": "2"}, {"status": "9"}]
        result = apply_operation(records, "lookup", {
            "field": "status",
            "mapping": {"1": "Active", "2": "Inactive"},
            "default": "Unknown",
        })
        assert result[0]["status"] == "Active"
        assert result[1]["status"] == "Inactive"
        assert result[2]["status"] == "Unknown"


# ── Math ─────────────────────────────────────────────────────────────────────

class TestMath:
    def test_add(self):
        records = [{"a": 10, "b": 5}]
        result = apply_operation(records, "math", {
            "field_a": "a", "field_b": "b", "operation": "add", "target_field": "sum",
        })
        assert result[0]["sum"] == 15

    def test_multiply_constant(self):
        records = [{"price": 100}]
        result = apply_operation(records, "math", {
            "field_a": "price", "operation": "multiply", "value": 1.25, "target_field": "total",
        })
        assert result[0]["total"] == 125.0


# ── Trim ─────────────────────────────────────────────────────────────────────

class TestTrim:
    def test_trim_all(self):
        records = [{"a": "  hello  ", "b": " world "}]
        result = apply_operation(records, "trim", {})
        assert result[0]["a"] == "hello"
        assert result[0]["b"] == "world"


# ── Split Column ─────────────────────────────────────────────────────────────

class TestSplitColumn:
    def test_split(self):
        records = [{"full": "Alice,Smith,30"}]
        result = apply_operation(records, "split_column", {
            "source_field": "full",
            "delimiter": ",",
            "target_fields": ["first", "last", "age"],
        })
        assert result[0]["first"] == "Alice"
        assert result[0]["last"] == "Smith"
        assert result[0]["age"] == "30"
