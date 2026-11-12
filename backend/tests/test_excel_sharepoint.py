"""Excel i SharePoint: inläsning av blad/tabell och uppslag via Graph."""
from __future__ import annotations

import io
import json
from datetime import datetime

import httpx
import openpyxl
import pytest
from openpyxl.worksheet.table import Table

from app.connectors import excel_sharepoint as ex
from app.connectors.registry import get_connector_class, list_connector_types


def _bok(rader: list[list], blad: str = "System", tabell: str | None = None, summarad: bool = False) -> bytes:
    bok = openpyxl.Workbook()
    ark = bok.active
    ark.title = blad
    for rad in rader:
        ark.append(rad)
    if tabell:
        sista = openpyxl.utils.get_column_letter(len(rader[0]))
        t = Table(displayName=tabell, ref=f"A1:{sista}{len(rader)}")
        if summarad:
            t.totalsRowCount = 1
        ark.add_table(t)
    ut = io.BytesIO()
    bok.save(ut)
    return ut.getvalue()


SYSTEM = [
    ["System-ID", "Namn", "Ägare", "Driftstart"],
    ["S1", "Ekonomisystem", "Ekonomi", datetime(2020, 1, 1)],
    ["S2", "HR-system", None, None],
]


class TestRegistrering:
    def test_registrerad(self):
        assert "excel_sharepoint" in list_connector_types()
        assert get_connector_class("excel_sharepoint") is ex.ExcelSharePointConnector


class TestLäsArbetsbok:
    def test_rader_blir_poster(self):
        poster = ex.läs_arbetsbok(_bok(SYSTEM))
        assert poster == [
            {"System-ID": "S1", "Namn": "Ekonomisystem", "Ägare": "Ekonomi", "Driftstart": "2020-01-01", "external_id": "S1"},
            {"System-ID": "S2", "Namn": "HR-system", "Ägare": None, "Driftstart": None, "external_id": "S2"},
        ]

    def test_vald_idkolumn_skiftlägesokänslig(self):
        poster = ex.läs_arbetsbok(_bok(SYSTEM), idkolumn="namn")
        assert [p["external_id"] for p in poster] == ["Ekonomisystem", "HR-system"]

    def test_okänd_idkolumn(self):
        with pytest.raises(ex.ExcelFel, match="Id-kolumnen 'Nyckel' finns inte"):
            ex.läs_arbetsbok(_bok(SYSTEM), idkolumn="Nyckel")

    def test_dubbla_id_stoppar(self):
        with pytest.raises(ex.ExcelFel, match="flera rader"):
            ex.läs_arbetsbok(_bok([["Id", "Namn"], ["1", "A"], ["1", "B"]]))

    def test_tal_som_id_utan_decimal(self):
        poster = ex.läs_arbetsbok(_bok([["Id", "Namn"], [12.0, "A"], [7, "B"]]))
        assert [p["external_id"] for p in poster] == ["12", "7"]

    def test_tomma_rader_och_rader_utan_id_hoppas_över(self):
        poster = ex.läs_arbetsbok(_bok([[None, None], ["Id", "Namn"], ["1", "A"], [None, None], [None, "utan id"], ["2", "B"]]))
        assert [p["external_id"] for p in poster] == ["1", "2"]

    def test_dubbla_rubriker_får_nummer(self):
        poster = ex.läs_arbetsbok(_bok([["Id", "Namn", "Namn"], ["1", "A", "B"]]))
        assert poster[0]["Namn"] == "A" and poster[0]["Namn (2)"] == "B"

    def test_blad_som_saknas(self):
        with pytest.raises(ex.ExcelFel, match="Bladen i filen: System"):
            ex.läs_arbetsbok(_bok(SYSTEM), blad="Annat")

    def test_tabell_utan_summarad(self):
        data = _bok(SYSTEM + [["Totalt", "", "", None]], tabell="Systemlista", summarad=True)
        poster = ex.läs_arbetsbok(data, tabell="systemlista")
        assert [p["external_id"] for p in poster] == ["S1", "S2"]

    def test_tabell_som_saknas(self):
        with pytest.raises(ex.ExcelFel, match="Tabellerna i filen: Systemlista"):
            ex.läs_arbetsbok(_bok(SYSTEM, tabell="Systemlista"), tabell="Annan")

    def test_inte_en_xlsx(self):
        with pytest.raises(ex.ExcelFel, match="går inte att läsa"):
            ex.läs_arbetsbok(b"inte en zip")

    def test_zipbomb_stoppas(self, monkeypatch):
        monkeypatch.setattr(ex, "MAX_UPPACKAT", 100)
        with pytest.raises(ex.ExcelFel, match="för stor uppackad"):
            ex.läs_arbetsbok(_bok(SYSTEM))


class TestDirektsökväg:
    @pytest.mark.parametrize("path,väntat", [
        ("/sites/Arkitektur/Delade%20dokument/Systemlista.xlsx", ("sites/Arkitektur", "Delade dokument/Systemlista.xlsx")),
        ("/teams/IT/Shared%20Documents/Mapp/lista.XLSX", ("teams/IT", "Shared Documents/Mapp/lista.XLSX")),
        ("/Shared%20Documents/lista.xlsx", ("", "Shared Documents/lista.xlsx")),
        ("/:x:/s/Arkitektur/EabcDEF", None),
        ("/:x:/r/sites/Arkitektur/_layouts/15/Doc.aspx", None),
        ("/sites/Arkitektur/Delade%20dokument/", None),
    ])
    def test_tolkning(self, path, väntat):
        assert ex._direktsökväg(path) == väntat


# ── Graph, med en falsk transport ─────────────────────────────────────────

UPPGIFTER = {"tenant_id": "contoso.onmicrosoft.com", "client_id": "c", "client_secret": "s"}
NEDLADDNING = "https://contoso.sharepoint.com/download/abc"


@pytest.fixture
def graph(monkeypatch):
    """Byter httpx.AsyncClient i kopplingen mot en med MockTransport. Svaren
    styrs av `svar` (en funktion av anropet); alla anrop sparas i `anrop`."""
    tillstånd: dict = {"anrop": [], "fil": _bok(SYSTEM), "status": {}}
    äkta = httpx.AsyncClient

    def hantera(req: httpx.Request) -> httpx.Response:
        tillstånd["anrop"].append(req)
        url = str(req.url)
        for nyckel, status in tillstånd["status"].items():
            if nyckel in url:
                return httpx.Response(status, json={"error": {"message": "nej"}})
        if url.startswith("https://login.microsoftonline.com/"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/sites/contoso.sharepoint.com:/sites/Arkitektur" in url:
            return httpx.Response(200, json={"id": "site1", "webUrl": "https://contoso.sharepoint.com/sites/Arkitektur"})
        if url.endswith("/sites/site1/drives?%24select=id%2Cname%2CwebUrl"):
            return httpx.Response(200, json={"value": [
                {"id": "d0", "webUrl": "https://contoso.sharepoint.com/sites/Arkitektur/Delade%20dokument%20gamla"},
                {"id": "d1", "webUrl": "https://contoso.sharepoint.com/sites/Arkitektur/Delade%20dokument"},
            ]})
        if "/drives/d1/root:/" in url or "/shares/u!" in url:
            return httpx.Response(200, json={
                "name": "Systemlista.xlsx", "size": len(tillstånd["fil"]),
                "@microsoft.graph.downloadUrl": tillstånd.get("nedladdning", NEDLADDNING),
            })
        if url == tillstånd.get("nedladdning", NEDLADDNING):
            assert "authorization" not in req.headers
            return httpx.Response(200, content=tillstånd["fil"])
        return httpx.Response(404, json={"error": {"message": f"okänd {url}"}})

    def fabrik(**kwargs):
        return äkta(transport=httpx.MockTransport(hantera), **kwargs)

    monkeypatch.setattr(ex.httpx, "AsyncClient", fabrik)
    return tillstånd


def _koppling(**config) -> ex.ExcelSharePointConnector:
    return ex.ExcelSharePointConnector(connection_config=config, credentials=dict(UPPGIFTER))


class TestGraph:
    async def test_direktadress_via_site_och_bibliotek(self, graph):
        k = _koppling(file_url="https://contoso.sharepoint.com/sites/Arkitektur/Delade%20dokument/Mapp/Systemlista.xlsx")
        poster = await k.fetch()
        assert [p["external_id"] for p in poster] == ["S1", "S2"]
        urls = [str(r.url) for r in graph["anrop"]]
        assert any("/drives/d1/root:/Mapp/Systemlista.xlsx" in u for u in urls)
        assert not any("/shares/" in u for u in urls)
        assert graph["anrop"][1].headers["authorization"] == "Bearer tok"

    async def test_delningslänk_via_shares(self, graph):
        k = _koppling(file_url="https://contoso.sharepoint.com/:x:/s/Arkitektur/EabcDEF?e=xyz")
        assert len(await k.fetch()) == 2
        assert any("/shares/u!" in str(r.url) for r in graph["anrop"])

    async def test_delningslänk_nekad_förklarar_sites_selected(self, graph):
        graph["status"]["/shares/"] = 403
        k = _koppling(file_url="https://contoso.sharepoint.com/:x:/s/Arkitektur/EabcDEF")
        with pytest.raises(ex.ExcelFel, match="direktadress"):
            await k.fetch()

    async def test_site_nekad(self, graph):
        graph["status"]["/sites/contoso.sharepoint.com:"] = 403
        k = _koppling(file_url="https://contoso.sharepoint.com/sites/Arkitektur/Delade%20dokument/Systemlista.xlsx")
        with pytest.raises(ex.ExcelFel, match="Sites.Selected"):
            await k.test_connection()

    async def test_inloggning_misslyckas(self, graph):
        graph["status"]["login.microsoftonline.com"] = 401
        k = _koppling(file_url="https://contoso.sharepoint.com/sites/Arkitektur/Delade%20dokument/Systemlista.xlsx")
        with pytest.raises(ex.ExcelFel, match="Inloggningen mot Entra"):
            await k.fetch()

    @pytest.mark.parametrize("adress", [
        "http://contoso.sharepoint.com/sites/A/D/x.xlsx",
        "https://evil.example.com/sites/A/D/x.xlsx",
        "https://contoso.sharepoint.com.evil.example/sites/A/D/x.xlsx",
        "",
    ])
    async def test_bara_sharepointadresser(self, graph, adress):
        with pytest.raises(ex.ExcelFel):
            await _koppling(file_url=adress).fetch()
        assert not any("evil" in str(r.url) for r in graph["anrop"])

    async def test_nedladdning_bara_från_sharepoint(self, graph):
        graph["nedladdning"] = "https://evil.example.com/fil"
        k = _koppling(file_url="https://contoso.sharepoint.com/:x:/s/Arkitektur/EabcDEF")
        with pytest.raises(ex.ExcelFel, match="nedladdningsadress"):
            await k.fetch()
        assert not any("evil" in str(r.url) for r in graph["anrop"])

    async def test_uppgifter_saknas(self, graph):
        k = ex.ExcelSharePointConnector(connection_config={"file_url": "https://contoso.sharepoint.com/:x:/s/A/E"}, credentials={})
        with pytest.raises(ex.ExcelFel, match="måste anges"):
            await k.fetch()
        assert graph["anrop"] == []

    async def test_konstigt_tenant_id_stoppas(self, graph):
        k = ex.ExcelSharePointConnector(
            connection_config={"file_url": "https://contoso.sharepoint.com/:x:/s/A/E"},
            credentials={**UPPGIFTER, "tenant_id": "x/../../annat"},
        )
        with pytest.raises(ex.ExcelFel, match="tenant-id"):
            await k.fetch()
        assert graph["anrop"] == []

    def test_schema(self):
        assert json.dumps(ex.ExcelSharePointConnector.config_schema())
