"""CSV connector — imports data from uploaded CSV files.

Unlike other connectors that fetch from external APIs, the CSV connector
reads from files uploaded via the /api/v1/csv/upload endpoint. The uploaded
data is stored directly as data records for the associated flow.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from app.connectors.base import BaseConnector
from app.connectors.registry import register_connector


@register_connector
class CsvConnector(BaseConnector):
    connector_type = "csv"

    async def fetch(self, params: dict | None = None) -> list[dict]:
        """CSV connector doesn't fetch — data is pushed via upload endpoint."""
        return []

    async def test_connection(self) -> bool:
        return True

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "delimiter": {
                    "type": "string",
                    "default": "auto",
                    "description": "CSV delimiter: 'auto' (detect), ',' (comma), ';' (semicolon), '\\t' (tab)",
                },
                "encoding": {
                    "type": "string",
                    "default": "utf-8",
                    "description": "File encoding: utf-8, latin-1, etc.",
                },
            },
        }


def parse_csv(content: str | bytes, delimiter: str = "auto", encoding: str = "utf-8") -> list[dict]:
    """Parse CSV content into a list of dicts.

    Handles:
    - Auto-detection of delimiter (comma vs semicolon vs tab)
    - UTF-8 with BOM and Latin-1 fallback
    - Stripping whitespace from headers and values
    """
    if isinstance(content, bytes):
        # Try UTF-8 first, then Latin-1
        try:
            text = content.decode("utf-8-sig")  # handles BOM
        except UnicodeDecodeError:
            text = content.decode(encoding if encoding != "utf-8" else "latin-1")
    else:
        text = content

    text = text.strip()
    if not text:
        return []

    # Auto-detect delimiter
    if delimiter == "auto":
        first_line = text.split("\n")[0]
        semicolons = first_line.count(";")
        commas = first_line.count(",")
        tabs = first_line.count("\t")
        if tabs > commas and tabs > semicolons:
            delimiter = "\t"
        elif semicolons > commas:
            delimiter = ";"
        else:
            delimiter = ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    records = []
    for i, row in enumerate(reader):
        record: dict = {}
        for key, value in row.items():
            if key is None:
                continue
            clean_key = key.strip()
            if not clean_key:
                continue
            clean_value = value.strip() if value else ""
            # Try to parse numbers
            if clean_value:
                try:
                    if "." in clean_value or "," in clean_value:
                        record[clean_key] = float(clean_value.replace(",", "."))
                    else:
                        record[clean_key] = int(clean_value)
                    continue
                except ValueError:
                    pass
            record[clean_key] = clean_value

        # Add an external_id if not present
        if "external_id" not in record and "id" not in record and "ID" not in record:
            record["external_id"] = str(i + 1)
        elif "id" in record:
            record["external_id"] = str(record["id"])
        elif "ID" in record:
            record["external_id"] = str(record["ID"])

        records.append(record)

    return records
