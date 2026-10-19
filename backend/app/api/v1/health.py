"""Health check and discovery endpoints."""
from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "integration-platform", "version": settings.APP_VERSION}


@router.get("/operations")
async def list_operations():
    """List all available pipeline operations with descriptions and config schemas."""
    return {
        "operations": [
            {
                "type": "transform",
                "label": "Field Mapping",
                "description": "Map source fields to target fields, apply value transforms, filter records, add computed fields",
                "category": "core",
            },
            {
                "type": "add_column",
                "label": "Add Column",
                "description": "Create a new column using a template, concatenation, copy, static value, or conditional logic",
                "category": "columns",
                "modes": ["static", "template", "concat", "copy", "conditional"],
            },
            {
                "type": "split_column",
                "label": "Split Column",
                "description": "Split a field into multiple fields by a delimiter (e.g. comma, semicolon)",
                "category": "columns",
            },
            {
                "type": "rename",
                "label": "Rename Fields",
                "description": "Rename one or more fields",
                "category": "columns",
            },
            {
                "type": "remove",
                "label": "Remove Fields",
                "description": "Remove unwanted fields from records",
                "category": "columns",
            },
            {
                "type": "replace",
                "label": "Find & Replace",
                "description": "Find and replace text within a field's values (supports regex)",
                "category": "text",
            },
            {
                "type": "substring",
                "label": "Extract Substring",
                "description": "Extract part of a text field by position or regex pattern",
                "category": "text",
            },
            {
                "type": "math",
                "label": "Math Operation",
                "description": "Arithmetic on numeric fields: add, subtract, multiply, divide, round, percentage",
                "category": "numeric",
                "operations": ["add", "subtract", "multiply", "divide", "round", "abs", "percent", "min", "max"],
            },
            {
                "type": "combine",
                "label": "Combine Fields",
                "description": "Merge multiple fields into one with a separator",
                "category": "columns",
            },
            {
                "type": "deduplicate",
                "label": "Deduplicate",
                "description": "Remove duplicate records based on one or more fields",
                "category": "rows",
            },
            {
                "type": "sort",
                "label": "Sort",
                "description": "Sort records by a field (ascending or descending, text or numeric)",
                "category": "rows",
            },
            {
                "type": "filter",
                "label": "Filter Rows",
                "description": "Keep only records that match conditions",
                "category": "rows",
            },
            {
                "type": "lookup",
                "label": "Value Lookup",
                "description": "Map field values using a lookup table (e.g. status codes to labels)",
                "category": "transform",
            },
        ]
    }
