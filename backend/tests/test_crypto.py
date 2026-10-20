import pytest

from app.core.crypto import decrypt_secret, encrypt_secret


def test_token_round_trips_through_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")

    encrypted = encrypt_secret("refresh-token-secret")

    assert encrypted != "refresh-token-secret"
    assert decrypt_secret(encrypted) == "refresh-token-secret"
