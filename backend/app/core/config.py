import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

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
    OAUTH_TOKEN_ENCRYPTION_KEY: str | None = None
    OAUTH_STATE_EXPIRE_MINUTES: int = 15
    FRONTEND_URL: str = "http://localhost:3000"
    MEDIA_DIR: str = "backend/storage"
    BUNDLED_MEDIA_DIR: str = "backend/storage"
    COOKIE_SECURE: bool = False
    TTS_SPEECH_RATE: int = 175
    TTS_ESPEAK_RATE: int = 155
    TTS_ESPEAK_PITCH: int = 45
    TTS_ESPEAK_WORD_GAP: int = 1
    TTS_ESPEAK_AMPLITUDE: int = 140
    TTS_ESPEAK_VOICE_SLOT_1: str = "en-us+f3"
    TTS_ESPEAK_VOICE_SLOT_2: str = "en-gb+m3"
    TTS_AUDIO_EXPORT_FPS: int = 44100
    TTS_AUDIO_EXPORT_BITRATE: str = "192k"
    OPENVOICE_ENABLED: bool = False
    OPENVOICE_REPO_DIR: str = ""
    OPENVOICE_CHECKPOINTS_DIR: str = ""
    OPENVOICE_DEVICE: str = "auto"
    OPENVOICE_DEFAULT_MODEL_ID: str = "openvoice_v2"
    VOICE_LAB_MAX_REFERENCE_AUDIO_SIZE_BYTES: int = 20 * 1024 * 1024
    VOICE_LAB_ALLOWED_AUDIO_TYPES: str = "audio/wav,audio/x-wav,audio/mpeg,audio/mp3,audio/flac,audio/mp4,audio/x-m4a"

    YOUTUBE_CLIENT_ID: str | None = None
    YOUTUBE_CLIENT_SECRET: str | None = None
    YOUTUBE_REDIRECT_URI: str | None = None
    YOUTUBE_OAUTH_SCOPE: str = (
        "https://www.googleapis.com/auth/youtube.upload "
        "https://www.googleapis.com/auth/youtube.readonly"
    )
    YOUTUBE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    YOUTUBE_CHANNELS_URL: str = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
    YOUTUBE_UPLOAD_URL: str = (
        "https://www.googleapis.com/upload/youtube/v3/videos?part=snippet,status&uploadType=multipart"
    )
    YOUTUBE_CONNECT_ENABLED: bool = True

    YT_API_KEY: str | None = None
    YT_UNITS_PER_MIN: int = 900
    IG_REQ_PER_MIN: int = 200
    TT_REQ_PER_MIN: int = 200

    SENTRY_DSN: str | None = None
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = "omniposter-api"

    AUTH_RATE_LIMIT_COUNT: int = 10
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60
    HEAVY_ENDPOINT_RATE_LIMIT_COUNT: int = 10
    HEAVY_ENDPOINT_RATE_LIMIT_WINDOW_SECONDS: int = 60

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT.lower() == "dev"

    def validate_runtime(self) -> None:
        if not self.is_dev and self.SECRET_KEY in {"dev-only-change-me", "dev-secret-key"}:
            raise RuntimeError("SECRET_KEY must be set to a non-default value outside dev.")
        if not self.is_dev and not self.OAUTH_TOKEN_ENCRYPTION_KEY:
            raise RuntimeError("OAUTH_TOKEN_ENCRYPTION_KEY is required outside dev.")
        if self.YOUTUBE_CONNECT_ENABLED:
            missing = [
                name
                for name, value in (
                    ("YOUTUBE_CLIENT_ID", self.YOUTUBE_CLIENT_ID),
                    ("YOUTUBE_CLIENT_SECRET", self.YOUTUBE_CLIENT_SECRET),
                    ("YOUTUBE_REDIRECT_URI", self.YOUTUBE_REDIRECT_URI),
                )
                if not value
            ]
            if missing and not self.is_dev:
                raise RuntimeError(f"Missing required YouTube OAuth settings: {', '.join(missing)}")


settings = Settings()
