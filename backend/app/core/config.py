from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Sparestracker Marketing Agent"
    environment: str = "development"
    owner_email: str = ""
    session_signing_key: str = ""
    token_encryption_key: str = ""
    database_url: str = "sqlite:///./marketing_agent.db"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    crawler_max_pages: int = 100
    crawler_max_requests: int = 500
    crawler_max_response_bytes: int = 1_048_576
    crawler_timeout_seconds: float = 8.0
    crawler_delay_seconds: float = 0.25
    crawler_max_duration_seconds: float = 120.0
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    public_base_url: str = ""

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "Sparestracker Marketing Agent"),
            environment=os.getenv("APP_ENV", "development"),
            owner_email=os.getenv("OWNER_EMAIL", "").strip().casefold(),
            session_signing_key=os.getenv("SESSION_SIGNING_KEY", ""),
            token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY", ""),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./marketing_agent.db"),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
            google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", ""),
            crawler_max_pages=int(os.getenv("CRAWLER_MAX_PAGES", "100")),
            crawler_max_requests=int(os.getenv("CRAWLER_MAX_REQUESTS", "500")),
            crawler_max_response_bytes=int(os.getenv("CRAWLER_MAX_RESPONSE_BYTES", "1048576")),
            crawler_timeout_seconds=float(os.getenv("CRAWLER_TIMEOUT_SECONDS", "8")),
            crawler_delay_seconds=float(os.getenv("CRAWLER_DELAY_SECONDS", "0.25")),
            crawler_max_duration_seconds=float(os.getenv("CRAWLER_MAX_DURATION_SECONDS", "120")),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
        )


def get_settings() -> Settings:
    return Settings.from_environment()


settings = get_settings()
