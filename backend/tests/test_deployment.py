from dataclasses import replace

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.core.deployment import RAILWAY_WEEKLY_CRON_UTC, validate_production_settings


def production_settings(**updates):
    config = Settings(
        environment="production", owner_email="owner@example.com", session_signing_key="s" * 40,
        token_encryption_key=Fernet.generate_key().decode(), database_url="postgresql+psycopg://owner:secret@db:5432/app",
        google_client_id="client", google_client_secret="secret", google_redirect_uri="https://growth.example.com/api/auth/google/callback",
        openai_api_key="sk-test", public_base_url="https://growth.example.com",
    )
    return replace(config, **updates)


def test_valid_production_configuration_passes_and_cron_matches_eat_monday_morning():
    validate_production_settings(production_settings())
    assert RAILWAY_WEEKLY_CRON_UTC == "0 5 * * 1"


@pytest.mark.parametrize("field", ["owner_email", "session_signing_key", "token_encryption_key", "google_client_id", "google_client_secret", "google_redirect_uri", "openai_api_key", "public_base_url"])
def test_missing_production_secret_is_rejected(field):
    with pytest.raises(RuntimeError, match="Missing required production settings"):
        validate_production_settings(production_settings(**{field: ""}))


def test_mismatched_oauth_callback_and_non_postgres_database_are_rejected():
    with pytest.raises(RuntimeError, match="GOOGLE_REDIRECT_URI"):
        validate_production_settings(production_settings(google_redirect_uri="https://other.example/api/auth/google/callback"))
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        validate_production_settings(production_settings(database_url="sqlite:///./app.db"))
