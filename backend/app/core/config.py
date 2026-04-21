from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import os

# Load .env from parent directory
REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_ENV = REPO_ROOT / ".env.dev"
ENV_PATH = Path(os.getenv("ENV_FILE", DEFAULT_ENV if DEFAULT_ENV.exists() else REPO_ROOT / ".env"))
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    ENVIRONMENT: str = "dev"
    API_PORT: int = 8000
    DATABASE_URL: str = "sqlite:///./omniposter.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-only-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    FRONTEND_URL: str = "http://localhost:3000"
    MEDIA_DIR: str = "backend/storage"
    COOKIE_SECURE: bool = False

    YOUTUBE_CLIENT_ID: str | None = None
    YOUTUBE_CLIENT_SECRET: str | None = None
    YOUTUBE_REDIRECT_URI: str | None = None

    YT_API_KEY: str | None = None
    YT_UNITS_PER_MIN: int = 900
    IG_REQ_PER_MIN: int = 200
    TT_REQ_PER_MIN: int = 200

    SENTRY_DSN: str | None = None
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = "omniposter-api"

settings = Settings()
