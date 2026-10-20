from urllib.parse import urlsplit

from app.core.config import Settings


REQUIRED_PRODUCTION_SECRETS = (
    "OWNER_EMAIL",
    "SESSION_SIGNING_KEY",
    "TOKEN_ENCRYPTION_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI",
    "OPENAI_API_KEY",
)
RAILWAY_WEEKLY_CRON_UTC = "0 5 * * 1"


def validate_production_settings(config: Settings) -> None:
    if config.environment.casefold() != "production":
        return
    missing = [name for name in REQUIRED_PRODUCTION_SECRETS if not getattr(config, _setting_name(name))]
    if not config.public_base_url:
        missing.append("PUBLIC_BASE_URL")
    if missing:
        raise RuntimeError("Missing required production settings: " + ", ".join(missing))
    parsed = urlsplit(config.public_base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or parsed.port is not None:
        raise RuntimeError("PUBLIC_BASE_URL must be an HTTPS origin without a path")
    expected_callback = f"{config.public_base_url}/api/auth/google/callback"
    if config.google_redirect_uri != expected_callback:
        raise RuntimeError("GOOGLE_REDIRECT_URI must match PUBLIC_BASE_URL/api/auth/google/callback")
    if not config.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("Production DATABASE_URL must use PostgreSQL")
    if len(config.session_signing_key) < 32:
        raise RuntimeError("SESSION_SIGNING_KEY must contain at least 32 characters")
    from cryptography.fernet import Fernet, InvalidToken
    try:
        Fernet(config.token_encryption_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError, InvalidToken) as exc:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc


def _setting_name(environment_name: str) -> str:
    return environment_name.casefold()


if __name__ == "__main__":
    from app.core.config import get_settings
    validate_production_settings(get_settings())
    print(f"Deployment configuration valid; weekly cron UTC: {RAILWAY_WEEKLY_CRON_UTC}")
