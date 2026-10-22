"""SharePoint connector — fetches list data from Microsoft Graph API.

Authentication uses OAuth2 client credentials flow:
  - The connector stores tenant_id, client_id, and client_secret
  - On each fetch it requests a fresh access token from Azure AD
  - No manual token management needed

How to set up:
  1. Register an app in Azure Portal → Microsoft Entra ID → App registrations
  2. Add API permission: Microsoft Graph → Application → Sites.Read.All
  3. Grant admin consent
  4. Create a client secret
  5. Provide tenant_id, client_id, client_secret to the connector
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import structlog

from app.connectors.base import BaseConnector
from app.connectors.registry import register_connector

log = structlog.get_logger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


@register_connector
class SharePointConnector(BaseConnector):
    connector_type = "sharepoint"

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        """Request an access token using OAuth2 client credentials flow."""
        tenant_id = self.credentials.get("tenant_id", "")
        client_id = self.credentials.get("client_id", "")
        client_secret = self.credentials.get("client_secret", "")

        if not all([tenant_id, client_id, client_secret]):
            raise ValueError("Missing credentials: tenant_id, client_id, and client_secret are all required")

        resp = await client.post(
            TOKEN_URL.format(tenant_id=tenant_id),
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        if resp.status_code != 200:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error_desc = body.get("error_description", body.get("error", resp.text[:500]))
            raise ValueError(f"Azure AD token error: {error_desc}")
        token = resp.json().get("access_token")
        if not token:
            raise ValueError("No access_token in Azure AD response")
        return token

    async def fetch(self, params: dict | None = None) -> list[dict]:
        mode = self.config.get("mode", "mock")
        if mode == "mock":
            return self._fetch_mock()
        return await self._fetch_api()

    def _fetch_mock(self) -> list[dict]:
        seed_path = Path(__file__).resolve().parents[2] / "seed" / "sharepoint_systems.json"
        return json.loads(seed_path.read_text(encoding="utf-8"))

    def _decode_field_name(self, name: str) -> str:
        """Decode SharePoint's _xHHHH_ encoded field names back to readable text.

        E.g. Po_x00e4_ng → Poäng, Bed_x00f6_mning → Bedömning
        """
        import re
        def _replace(m: re.Match) -> str:
            return chr(int(m.group(1), 16))
        return re.sub(r"_x([0-9a-fA-F]{4})_", _replace, name)

    _SKIP_PREFIXES = ("_", "odata", "App", "Author", "Editor", "ItemChild", "FolderChild")
    _SKIP_EXACT = {"Edit", "Attachments", "ContentType", "@odata.etag", "id"}

    def _is_skipped_field(self, key: str) -> bool:
        """Internal/metadata fields that never reach the records."""
        return key in self._SKIP_EXACT or key.startswith(self._SKIP_PREFIXES)

    def _clean_fields(self, fields: dict) -> dict:
        """Clean up SharePoint fields: decode names, resolve lookups, remove metadata."""
        # First pass: collect resolved lookup values
        # Key by both the original display name AND a normalized no-space version
        resolved = {}
        resolved_nospace = {}
        for key, value in fields.items():
            if key.startswith("_resolved_"):
                display_name = key[len("_resolved_"):]
                resolved[display_name] = value
                resolved_nospace[display_name.replace(" ", "").lower()] = (display_name, value)

        cleaned = {}
        for key, value in fields.items():
            # Skip internal/metadata fields
            if self._is_skipped_field(key):
                continue

            decoded_key = self._decode_field_name(key)

            # Skip LookupId fields — use resolved display value if available
            if decoded_key.endswith("LookupId"):
                base_name = decoded_key[:-len("LookupId")]
                base_nospace = base_name.replace(" ", "").lower()

                # Try exact match, then no-space match, then prefix match
                if base_name in resolved:
                    cleaned[base_name] = resolved[base_name]
                elif base_nospace in resolved_nospace:
                    display_name, display_val = resolved_nospace[base_nospace]
                    cleaned[display_name] = display_val
                else:
                    # Try prefix match (SP truncates long internal names)
                    found = False
                    for rkey, (display_name, display_val) in resolved_nospace.items():
                        if rkey.startswith(base_nospace) or base_nospace.startswith(rkey):
                            cleaned[display_name] = display_val
                            found = True
                            break
                    if not found:
                        cleaned[base_name + "_id"] = value
                continue

            cleaned[decoded_key] = value

        return cleaned

    def _column_record_keys(self, columns: list[dict]) -> list[str]:
        """The record key each list column ends up under after _clean_fields.

        Lookup and person columns surface under their display name (resolved
        value); everything else under the decoded internal name.
        """
        keys = []
        for col in columns:
            internal = col.get("name", "")
            if not internal or self._is_skipped_field(internal):
                continue
            if "lookup" in col or "personOrGroup" in col:
                keys.append(col.get("displayName") or internal)
            else:
                keys.append(self._decode_field_name(internal))
        return keys

    async def _fetch_api(self) -> list[dict]:
        site_id = self.config.get("site_id", "").strip()
        list_id = self.config.get("list_id", "").strip().strip("{}")

        if not site_id or not list_id:
            raise ValueError("site_id and list_id are required for API mode")

        async with httpx.AsyncClient(timeout=30.0) as client:
            token = await self._get_access_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            # Step 1: Fetch list columns to find lookup columns and their referenced lists
            columns_url = f"{GRAPH_BASE}/sites/{site_id}/lists/{list_id}/columns"
            col_resp = await client.get(columns_url, headers=headers)
            col_resp.raise_for_status()
            columns = col_resp.json().get("value", [])

            # Map: display name → { ref_list_id, internal_name }
            # Also build internal_name → display_name map for matching
            lookup_columns: dict[str, dict] = {}
            all_col_map: dict[str, str] = {}  # internal_name → display_name
            person_columns: set[str] = set()  # display names of person/user columns
            user_columns: list[dict] = []  # user-defined columns, to emit even when empty

            for col in columns:
                col_display = col.get("displayName", col.get("name", ""))
                col_internal = col.get("name", "")
                all_col_map[col_internal] = col_display
                if not col.get("readOnly") and not col.get("hidden"):
                    user_columns.append(col)

                lookup_info = col.get("lookup")
                if lookup_info and lookup_info.get("listId"):
                    lookup_columns[col_display] = {
                        "internal_name": col_internal,
                        "ref_list_id": lookup_info["listId"],
                    }

                # Detect person columns (personOrGroup type)
                person_info = col.get("personOrGroup")
                if person_info:
                    person_columns.add(col_display)

            log.info("sharepoint.columns", total=len(columns),
                     lookups=list(lookup_columns.keys()),
                     person_columns=list(person_columns))

            # Step 2: Fetch all items
            all_items: list[dict] = []
            url: str | None = f"{GRAPH_BASE}/sites/{site_id}/lists/{list_id}/items?$expand=fields&$top=200"

            while url:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("value", [])
                all_items.extend(items)
                url = data.get("@odata.nextLink")

            # Step 3: Discover ALL lookup fields from the data and match to columns
            skip_system = {"AuthorLookupId", "EditorLookupId", "AppAuthorLookupId", "AppEditorLookupId"}
            all_lookup_keys: set[str] = set()
            for item in all_items:
                for fk in item.get("fields", {}):
                    if fk.endswith("LookupId") and fk not in skip_system:
                        all_lookup_keys.add(fk)

            # Build matching helpers: column display name without spaces → (display_name, ref_list_id)
            # SharePoint internal names strip spaces and truncate, so we match by stripping spaces
            col_nospace_map: dict[str, tuple[str, str | None]] = {}
            for col_display, info in lookup_columns.items():
                key = col_display.replace(" ", "").lower()
                col_nospace_map[key] = (col_display, info["ref_list_id"])
            # Also add person columns — they reference the User Information List
            for col_display in person_columns:
                key = col_display.replace(" ", "").lower()
                if key not in col_nospace_map:
                    col_nospace_map[key] = (col_display, "__user_info__")

            # Also build from all_col_map (internal_name → display_name)
            for internal, display in all_col_map.items():
                key = display.replace(" ", "").lower()
                if key not in col_nospace_map:
                    col_nospace_map[key] = (display, None)

            # Match each LookupId field to a column
            lookup_field_map: dict[str, tuple[str, str | None]] = {}
            unmatched_keys: list[str] = []
            for encoded_key in all_lookup_keys:
                decoded = self._decode_field_name(encoded_key)
                base_decoded = decoded[:-len("LookupId")]
                base_nospace = base_decoded.replace(" ", "").lower()

                # Try exact match first, then prefix match (SP truncates long names)
                matched = False
                for col_key, (col_display, ref_id) in col_nospace_map.items():
                    if col_key == base_nospace or col_key.startswith(base_nospace) or base_nospace.startswith(col_key):
                        lookup_field_map[encoded_key] = (col_display, ref_id)
                        matched = True
                        break

                if not matched:
                    # Unmatched but still a LookupId — likely a person field not in columns API
                    # Use the decoded name and assume User Information List
                    lookup_field_map[encoded_key] = (base_decoded, "__user_info__")
                    log.info("sharepoint.assumed_person_lookup", encoded_key=encoded_key, decoded=base_decoded)

            log.info("sharepoint.lookup_field_map",
                     mapping={k: v[0] for k, v in lookup_field_map.items()})

            # Step 4: Fetch referenced lookup list items to resolve IDs → display values
            lookup_cache: dict[str, dict[str, str]] = {}
            ref_list_ids_needed: set[str] = set()
            needs_user_info = False
            for _, (_, ref_id) in lookup_field_map.items():
                if ref_id == "__user_info__":
                    needs_user_info = True
                elif ref_id:
                    ref_list_ids_needed.add(ref_id)

            # Fetch each referenced list
            for ref_list_id in ref_list_ids_needed:
                if ref_list_id in lookup_cache:
                    continue
                try:
                    ref_url = f"{GRAPH_BASE}/sites/{site_id}/lists/{ref_list_id}/items?$expand=fields&$top=500"
                    ref_resp = await client.get(ref_url, headers=headers)
                    if ref_resp.status_code == 200:
                        ref_items = ref_resp.json().get("value", [])
                        cache_map = {}
                        for ri in ref_items:
                            rf = ri.get("fields", {})
                            display = rf.get("Title", "")
                            if not display:
                                for fk, fv in rf.items():
                                    if isinstance(fv, str) and fv and not fk.startswith("_") and fk not in ("ContentType", "Edit", "id"):
                                        display = fv
                                        break
                            cache_map[str(ri["id"])] = display or f"Item {ri['id']}"
                        lookup_cache[ref_list_id] = cache_map
                        log.info("sharepoint.lookup_loaded", ref_list=ref_list_id, items=len(ref_items))
                except Exception as e:
                    log.warning("sharepoint.lookup_fetch_failed", ref_list=ref_list_id, error=str(e))

            # Fetch User Information List for person fields
            if needs_user_info:
                try:
                    # The User Information List is at the root site
                    # We can access it via /sites/{site_id}/lists('User Information List')/items
                    # or via the site users endpoint
                    user_url = f"{GRAPH_BASE}/sites/{site_id}/lists/User%20Information%20List/items?$expand=fields($select=Title)&$top=500"
                    user_resp = await client.get(user_url, headers=headers)
                    if user_resp.status_code == 200:
                        user_items = user_resp.json().get("value", [])
                        user_cache = {
                            str(ui["id"]): ui.get("fields", {}).get("Title", f"User {ui['id']}")
                            for ui in user_items
                        }
                        lookup_cache["__user_info__"] = user_cache
                        log.info("sharepoint.user_list_loaded", users=len(user_items))
                    else:
                        log.warning("sharepoint.user_list_error", status=user_resp.status_code)
                except Exception as e:
                    log.warning("sharepoint.user_list_failed", error=str(e))

            log.info("sharepoint.fetched", items=len(all_items), lookup_lists_resolved=len(lookup_cache))

            # Graph omits empty fields, so a column nobody has filled in yet would
            # never reach the records — and the pipeline editor, which derives its
            # field list from stored records, could never offer it.
            empty_record_keys = self._column_record_keys(user_columns)

            # Step 5: Process items — resolve lookups and clean fields
            records = []
            debug_first = True
            for item in all_items:
                fields = item.get("fields", {})

                # Inject resolved lookup display values before cleaning
                for encoded_key, (display_name, ref_list_id) in lookup_field_map.items():
                    lookup_id = str(fields.get(encoded_key, ""))
                    if not lookup_id:
                        continue
                    if ref_list_id and ref_list_id in lookup_cache:
                        display_val = lookup_cache[ref_list_id].get(lookup_id)
                        if display_val:
                            fields[f"_resolved_{display_name}"] = display_val
                        elif debug_first:
                            log.warning("sharepoint.lookup_id_not_found",
                                        field=display_name, lookup_id=lookup_id, ref_list=ref_list_id,
                                        cache_size=len(lookup_cache.get(ref_list_id, {})))
                    elif debug_first:
                        log.warning("sharepoint.no_cache_for_ref",
                                    field=display_name, ref_list_id=ref_list_id,
                                    available_caches=list(lookup_cache.keys()))

                if debug_first:
                    resolved_keys = [k for k in fields if k.startswith("_resolved_")]
                    log.info("sharepoint.first_record_resolved", resolved=resolved_keys)
                    debug_first = False

                cleaned = self._clean_fields(fields)
                for key in empty_record_keys:
                    cleaned.setdefault(key, None)
                cleaned["external_id"] = str(item.get("id", ""))
                records.append(cleaned)
            return records

    async def test_connection(self) -> bool:
        mode = self.config.get("mode", "mock")
        if mode == "mock":
            return True
        # Let exceptions propagate so the API returns the actual error message
        site_id = self.config.get("site_id", "").strip()
        async with httpx.AsyncClient(timeout=10.0) as client:
            token = await self._get_access_token(client)
            resp = await client.get(
                f"{GRAPH_BASE}/sites/{site_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return True
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error_msg = body.get("error", {}).get("message", resp.text[:300])
            raise ValueError(f"SharePoint API error ({resp.status_code}): {error_msg}")

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["mock", "api"],
                    "default": "mock",
                    "description": "mock = seed data, api = live Microsoft Graph API",
                },
                "site_id": {
                    "type": "string",
                    "description": "SharePoint site ID in format: hostname,site-collection-id,web-id",
                },
                "list_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "SharePoint list GUID",
                },
            },
        }
