"""Lösenord och API-nycklar med bcrypt.

bcrypt läser högst 72 byte. Version 4 kapade resten själv, version 5 vägrar
längre indata – kapningen görs därför i auth_service, så att:
- ett långt lösenord går att sätta och logga in med,
- hashar från före bytet (gjorda på de första 72 byten) fortsätter fungera,
- ett felaktigt eller för långt värde ger "fel lösenord", inte ett serverfel.
"""
import bcrypt

from app.services.auth_service import hash_password, verify_password


def test_vanligt_losenord():
    h = hash_password("hemligt-123")
    assert verify_password("hemligt-123", h)
    assert not verify_password("fel", h)


def test_langt_losenord_fungerar():
    langt = "å" * 60  # 120 byte
    h = hash_password(langt)
    assert verify_password(langt, h)


def test_hash_fran_bcrypt_4_fungerar():
    langt = "x" * 100
    gammal = bcrypt.hashpw(langt.encode()[:72], bcrypt.gensalt()).decode()
    assert verify_password(langt, gammal)


def test_ogiltig_hash_ar_fel_losenord():
    assert not verify_password("vad som helst", "inte-en-hash")
