"""Excel i SharePoint – läser ett blad eller en tabell i en .xlsx-fil som ligger
i SharePoint/OneDrive, via Microsoft Graph.

Varje rad blir en post med kolumnrubrikerna som fält. Kolumnen som anges som
id-kolumn (förval: första kolumnen) blir postens external_id – det är den som
låter EA-portalen känna igen ett system mellan inläsningarna, så den måste
vara unik och stabil (radnumret duger inte: sorteras listan blir det fel).

Inloggning: OAuth2 client credentials, som SharePoint-kopplingen – tenant_id,
client_id och client_secret för en app-registrering med Microsoft Graph
Application-behörigheten Sites.Selected (läsrätt på just den siten) eller
Sites.Read.All/Files.Read.All, med admin consent.

Filen anges med sin adress:
  - direktadressen (Information → Sökväg → Kopiera), t.ex.
    https://contoso.sharepoint.com/sites/Arkitektur/Delade%20dokument/Systemlista.xlsx
    – slås upp via siten och dess dokumentbibliotek och fungerar med
    Sites.Selected;
  - en delningslänk (https://contoso.sharepoint.com/:x:/s/...) eller adressen
    när filen är öppen i Excel på webben (…/Doc.aspx?sourcedoc=…) – slås upp
    via /shares, vilket kräver Sites.Read.All eller Files.Read.All.

Plattformen anropar bara Microsofts adresser (login.microsoftonline.com,
graph.microsoft.com) och nedladdningsadressen Graph lämnar, som måste ligga
under sharepoint.com. Filadressen själv hämtas aldrig.
"""
from __future__ import annotations

import base64
import io
import re
import zipfile
from datetime import date, datetime, time
from urllib.parse import quote, unquote, urlsplit

import httpx
import structlog

from app.connectors.base import BaseConnector
from app.connectors.registry import register_connector
from app.connectors.sharepoint import GRAPH_BASE, TOKEN_URL

log = structlog.get_logger(__name__)

# Gränser mot orimliga filer: storleken på nedladdningen, och vad zip-filen
# packas upp till (en .xlsx är en zip med XML – en liten fil kan packas upp
# till väldigt mycket).
MAX_FILSTORLEK = 25 * 1024 * 1024
MAX_UPPACKAT = 250 * 1024 * 1024
MAX_RADER = 100_000

_FILTYPER = (".xlsx", ".xlsm")
_NEDLADDNINGSVÄRDAR = (".sharepoint.com", ".sharepoint.us", ".sharepoint.de", ".sharepoint.cn")
_SITEPREFIX = ("sites", "teams", "personal")


class ExcelFel(ValueError):
    """Ett fel att visa för den som sätter upp kopplingen."""


@register_connector
class ExcelSharePointConnector(BaseConnector):
    connector_type = "excel_sharepoint"

    # ── Inloggning ────────────────────────────────────────────────────────

    async def _token(self, client: httpx.AsyncClient) -> str:
        tenant_id = str(self.credentials.get("tenant_id", "")).strip()
        client_id = str(self.credentials.get("client_id", "")).strip()
        client_secret = str(self.credentials.get("client_secret", "")).strip()
        if not all([tenant_id, client_id, client_secret]):
            raise ExcelFel("Tenant ID, Client ID och Client Secret måste anges")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", tenant_id):
            raise ExcelFel("Tenant ID ser inte ut som ett tenant-id")
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
            fel = _json(resp)
            text = fel.get("error_description") or fel.get("error") or resp.text[:300]
            raise ExcelFel(f"Inloggningen mot Entra misslyckades: {text}")
        token = resp.json().get("access_token")
        if not token:
            raise ExcelFel("Entra lämnade ingen åtkomsttoken")
        return token

    # ── Hitta filen ───────────────────────────────────────────────────────

    async def _hitta_fil(self, client: httpx.AsyncClient, rubriker: dict) -> dict:
        adress = str(self.config.get("file_url", "")).strip()
        if not adress:
            raise ExcelFel("Ange adressen till Excelfilen")
        delar = urlsplit(adress)
        värd = (delar.hostname or "").lower()
        if delar.scheme != "https" or not värd.endswith(_NEDLADDNINGSVÄRDAR):
            raise ExcelFel("Adressen ska vara en https-adress till SharePoint (…sharepoint.com/…)")

        direkt = _direktsökväg(delar.path)
        if direkt:
            return await self._via_sökväg(client, rubriker, värd, *direkt)
        return await self._via_delning(client, rubriker, adress)

    async def _via_sökväg(
        self, client: httpx.AsyncClient, rubriker: dict, värd: str, sitesökväg: str, filsökväg: str,
    ) -> dict:
        """Siten → dess dokumentbibliotek → filen. Kräver bara läsrätt på siten."""
        site_url = f"{GRAPH_BASE}/sites/{värd}:" + (f"/{quote(sitesökväg)}" if sitesökväg else "/")
        resp = await client.get(site_url, headers=rubriker, params={"$select": "id,webUrl"})
        _kontrollera(resp, "siten")
        site = resp.json()

        resp = await client.get(
            f"{GRAPH_BASE}/sites/{site['id']}/drives", headers=rubriker,
            params={"$select": "id,name,webUrl"},
        )
        _kontrollera(resp, "sitens dokumentbibliotek")
        # Jämförs utan skiftläge (som SharePoint), men sökvägen skickas som den skrevs.
        filadress = f"https://{värd}/" + "/".join(d for d in (sitesökväg, filsökväg) if d)
        jämför = filadress.lower()
        bibliotek = None
        for drive in resp.json().get("value", []):
            bas = _normalisera(drive.get("webUrl", ""))
            if bas and jämför.startswith(bas + "/") and (bibliotek is None or len(bas) > len(bibliotek[1])):
                bibliotek = (drive, bas)
        if bibliotek is None:
            raise ExcelFel("Hittade inget dokumentbibliotek på siten som filen ligger i – kontrollera adressen")
        drive, bas = bibliotek
        relativ = filadress[len(bas) + 1:]
        resp = await client.get(
            f"{GRAPH_BASE}/drives/{drive['id']}/root:/{quote(relativ)}", headers=rubriker,
        )
        _kontrollera(resp, "filen")
        return resp.json()

    async def _via_delning(self, client: httpx.AsyncClient, rubriker: dict, adress: str) -> dict:
        kod = "u!" + base64.urlsafe_b64encode(adress.encode()).decode().rstrip("=")
        resp = await client.get(f"{GRAPH_BASE}/shares/{kod}/driveItem", headers=rubriker)
        if resp.status_code in (401, 403):
            raise ExcelFel(
                "Microsoft nekade åtkomst till filen via länken. En delningslänk kräver behörigheten "
                "Sites.Read.All eller Files.Read.All. Med Sites.Selected: använd filens direktadress "
                "(i SharePoint: filens Information → Sökväg → Kopiera)."
            )
        _kontrollera(resp, "filen")
        return resp.json()

    # ── Ladda ner och läsa ────────────────────────────────────────────────

    async def _ladda_ner(self, client: httpx.AsyncClient, fil: dict) -> bytes:
        namn = str(fil.get("name", ""))
        if "folder" in fil:
            raise ExcelFel(f"Adressen pekar på en mapp ({namn}), inte en fil")
        if not namn.lower().endswith(_FILTYPER):
            raise ExcelFel(f"Filen {namn!r} är ingen .xlsx-fil (äldre .xls och .csv läses inte)")
        storlek = int(fil.get("size") or 0)
        if storlek > MAX_FILSTORLEK:
            raise ExcelFel(f"Filen är för stor ({storlek // 1024 // 1024} MB, högst {MAX_FILSTORLEK // 1024 // 1024} MB)")
        url = fil.get("@microsoft.graph.downloadUrl", "")
        delar = urlsplit(url)
        if delar.scheme != "https" or not (delar.hostname or "").lower().endswith(_NEDLADDNINGSVÄRDAR):
            raise ExcelFel("Microsoft lämnade ingen nedladdningsadress för filen")
        # Nedladdningsadressen är förautentiserad – ingen token skickas med.
        innehåll = bytearray()
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise ExcelFel(f"Nedladdningen av filen misslyckades ({resp.status_code})")
            async for bit in resp.aiter_bytes():
                innehåll += bit
                if len(innehåll) > MAX_FILSTORLEK:
                    raise ExcelFel("Filen är för stor")
        return bytes(innehåll)

    async def _hämta_arbetsbok(self) -> bytes:
        async with httpx.AsyncClient(timeout=60.0) as client:
            token = await self._token(client)
            rubriker = {"Authorization": f"Bearer {token}"}
            fil = await self._hitta_fil(client, rubriker)
            data = await self._ladda_ner(client, fil)
            log.info("excel_sharepoint.downloaded", file=fil.get("name"), bytes=len(data))
            return data

    async def fetch(self, params: dict | None = None) -> list[dict]:
        data = await self._hämta_arbetsbok()
        return läs_arbetsbok(
            data,
            blad=str(self.config.get("sheet", "") or "").strip(),
            tabell=str(self.config.get("table", "") or "").strip(),
            idkolumn=str(self.config.get("id_column", "") or "").strip(),
        )

    async def test_connection(self) -> bool:
        # Hela vägen: inloggning, filen, bladet/tabellen och id-kolumnen. Fel
        # går vidare som undantag så att texten visas.
        await self.fetch()
        return True

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_url": {"type": "string", "description": "Adressen till .xlsx-filen i SharePoint"},
                "sheet": {"type": "string", "description": "Blad (tomt = första bladet)"},
                "table": {"type": "string", "description": "Tabell (Formatera som tabell) – går före bladet"},
                "id_column": {"type": "string", "description": "Kolumnen med unikt id (tomt = första kolumnen)"},
            },
            "required": ["file_url"],
        }


# ── Hjälpare ──────────────────────────────────────────────────────────────


def _json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _kontrollera(resp: httpx.Response, vad: str) -> None:
    if resp.status_code == 200:
        return
    fel = _json(resp).get("error", {})
    text = fel.get("message", "") if isinstance(fel, dict) else ""
    if resp.status_code in (401, 403):
        raise ExcelFel(
            f"Microsoft nekade åtkomst till {vad}. Kontrollera att appen har Microsoft Graph-behörigheten "
            "Sites.Selected med läsrätt på siten (eller Sites.Read.All) och att admin consent är givet."
            + (f" ({text})" if text else "")
        )
    if resp.status_code == 404:
        raise ExcelFel(f"Hittade inte {vad} – kontrollera adressen." + (f" ({text})" if text else ""))
    raise ExcelFel(f"Microsoft Graph svarade med fel ({resp.status_code}) för {vad}." + (f" {text}" if text else ""))


def _normalisera(url: str) -> str:
    return unquote(url).rstrip("/").lower()


def _direktsökväg(path: str) -> tuple[str, str] | None:
    """(sitens sökväg, filens sökväg från siten) för en direktadress, annars
    None (delningslänkar /:x:/…, Doc.aspx och andra _layouts-adresser)."""
    delar = [unquote(d) for d in path.split("/") if d]
    if not delar or delar[0].startswith(":") or "_layouts" in delar:
        return None
    if not delar[-1].lower().endswith(_FILTYPER):
        return None
    if delar[0].lower() in _SITEPREFIX and len(delar) >= 3:
        return f"{delar[0]}/{delar[1]}", "/".join(delar[2:])
    return "", "/".join(delar)


def _värde(v: object) -> object:
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return v or None
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == time(0) else v.isoformat()
    if isinstance(v, (date, time)):
        return v.isoformat()
    return v


def _som_id(v: object) -> str:
    v = _värde(v)
    return "" if v is None else str(v)


def _kontrollera_zip(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            uppackat = sum(i.file_size for i in z.infolist())
    except zipfile.BadZipFile as e:
        raise ExcelFel("Filen går inte att läsa som .xlsx") from e
    if uppackat > MAX_UPPACKAT:
        raise ExcelFel("Filen är för stor uppackad")


def läs_arbetsbok(data: bytes, blad: str = "", tabell: str = "", idkolumn: str = "") -> list[dict]:
    """Raderna i ett blad eller en tabell som poster. Rubrikraden ger fälten."""
    import openpyxl  # tung import – bara när en Excelfil faktiskt läses

    _kontrollera_zip(data)
    try:
        bok = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as e:  # openpyxl har inget eget undantag för trasiga filer
        raise ExcelFel(f"Filen går inte att läsa som .xlsx ({e.__class__.__name__})") from e

    if tabell:
        rader = _tabellrader(bok, tabell)
    else:
        if blad:
            if blad not in bok.sheetnames:
                raise ExcelFel(f"Bladet {blad!r} finns inte. Bladen i filen: {', '.join(bok.sheetnames)}")
            ark = bok[blad]
        else:
            ark = bok.worksheets[0]
        rader = list(ark.iter_rows(values_only=True))

    # Rubrikraden: den första raden med något i.
    while rader and all(_värde(c) is None for c in rader[0]):
        rader.pop(0)
    if not rader:
        return []
    rubriker: list[str | None] = []
    sedda: dict[str, int] = {}
    for c in rader[0]:
        namn = _som_id(c)
        if not namn:
            rubriker.append(None)
            continue
        sedda[namn] = sedda.get(namn, 0) + 1
        rubriker.append(namn if sedda[namn] == 1 else f"{namn} ({sedda[namn]})")
    kolumner = [r for r in rubriker if r]
    if not kolumner:
        raise ExcelFel("Rubrikraden är tom")

    if idkolumn:
        träff = next((r for r in kolumner if r.lower() == idkolumn.lower()), None)
        if träff is None:
            raise ExcelFel(f"Id-kolumnen {idkolumn!r} finns inte. Kolumnerna: {', '.join(kolumner)}")
        idkolumn = träff
    else:
        idkolumn = kolumner[0]

    poster: list[dict] = []
    sedda_id: dict[str, int] = {}
    utan_id = 0
    for nr, rad in enumerate(rader[1:], start=2):
        post = {r: _värde(c) for r, c in zip(rubriker, rad) if r}
        for r in kolumner:
            post.setdefault(r, None)
        if all(v is None for v in post.values()):
            continue
        ext = _som_id(post.get(idkolumn))
        if not ext:
            utan_id += 1
            continue
        if ext in sedda_id:
            raise ExcelFel(
                f"Id {ext!r} i kolumnen {idkolumn!r} förekommer på flera rader "
                f"({sedda_id[ext]} och {nr}) – id-kolumnen måste vara unik"
            )
        sedda_id[ext] = nr
        post["external_id"] = ext
        poster.append(post)
        if len(poster) > MAX_RADER:
            raise ExcelFel(f"Fler än {MAX_RADER} rader")
    if utan_id:
        log.warning("excel_sharepoint.rows_without_id", id_column=idkolumn, rows=utan_id)
    return poster


def _tabellrader(bok, tabell: str) -> list[tuple]:
    namn = []
    for ark in bok.worksheets:
        for t in ark.tables.values():
            namn.append(t.name)
            if t.name.lower() == tabell.lower():
                rader = [tuple(c.value for c in rad) for rad in ark[t.ref]]
                # En summarad hör inte till datat.
                return rader[: len(rader) - (t.totalsRowCount or 0)]
    if namn:
        raise ExcelFel(f"Tabellen {tabell!r} finns inte. Tabellerna i filen: {', '.join(namn)}")
    raise ExcelFel(f"Tabellen {tabell!r} finns inte – filen har inga tabeller. Lämna Tabell tomt för att läsa bladet.")
