"""ARKITEKTEN_URL tolkas som full adress eller som Renders interna värd[:port]."""
import pytest

from app.services.arkitekten_kalla import bas_url


@pytest.mark.parametrize("värde, väntat", [
    ("", ""),
    ("  ", ""),
    ("arkitekten", "http://arkitekten:8200"),
    ("arkitekten-abcd:8200", "http://arkitekten-abcd:8200"),
    ("arkitekten:10000", "http://arkitekten:10000"),
    ("http://ark.example.org:8200/", "http://ark.example.org:8200"),
    ("https://ark.example.org", "https://ark.example.org:8200"),
    ("http://ark:8200/bas", "http://ark:8200/bas"),
])
def test_bas_url(värde, väntat):
    assert bas_url(värde) == väntat
