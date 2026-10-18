"""B5: salted PBKDF2 for new PINs; legacy SHA-256 still verifies."""

from __future__ import annotations

import hashlib

from app.services.qr_download import hash_pin, verify_pin


def test_legacy_sha256_pin_hash_still_verifies():
    pin = "123456"
    legacy = hashlib.sha256(pin.encode("utf-8")).hexdigest()
    assert verify_pin(pin, legacy) is True
    assert verify_pin("000000", legacy) is False


def test_new_pin_stores_pbkdf2_salt_format():
    stored = hash_pin("654321")
    assert stored.startswith("pbkdf2$")
    parts = stored.split("$")
    assert len(parts) == 4
    assert parts[0] == "pbkdf2"
    assert parts[1].isdigit()
    assert len(parts[2]) == 32  # 16-byte salt hex
    assert len(parts[3]) == 64  # sha256 hex
    assert verify_pin("654321", stored) is True
    assert verify_pin("000000", stored) is False
