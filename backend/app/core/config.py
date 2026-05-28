import os
from pathlib import Path
from urllib.parse import urlparse

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
    CORS_ALLOWED_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    CORS_ALLOWED_HEADERS: str = "Authorization,Content-Type"
    TTS_SPEECH_RATE: int = 175
    TTS_ESPEAK_RATE: int = 155
    TTS_ESPEAK_PITCH: int = 45
    TTS_ESPEAK_WORD_GAP: int = 1
    TTS_ESPEAK_AMPLITUDE: int = 140
    TTS_ESPEAK_VOICE_SLOT_1: str = "en-us+f3"
    TTS_ESPEAK_VOICE_SLOT_2: str = "en-gb+m3"
    TTS_AUDIO_EXPORT_FPS: int = 44100
    TTS_AUDIO_EXPORT_BITRATE: str = "192k"
    RENDER_PROFILING_ENABLED: bool = True
    RENDER_PREVIEW_WIDTH: int = 1080
    RENDER_PREVIEW_HEIGHT: int = 1920
    RENDER_PREVIEW_FPS_CAP: int = 24
    RENDER_EXPORT_WIDTH: int = 1080
    RENDER_EXPORT_HEIGHT: int = 1920
    RENDER_EXPORT_FPS_CAP: int = 30
    RENDER_FFMPEG_THREAD_CAP: int = 8
    RENDER_DRAFT_WIDTH: int = 540
    RENDER_DRAFT_HEIGHT: int = 960
    RENDER_DRAFT_FPS_CAP: int = 12
    RENDER_DRAFT_ENCODE_PRESET: str = "ultrafast"
    RENDER_DRAFT_CRF: int = 30
    RENDER_PREVIEW_ENCODE_PRESET: str = "veryfast"
    RENDER_PREVIEW_CRF: int = 24
    RENDER_EXPORT_ENCODE_PRESET: str = "faster"
    RENDER_EXPORT_CRF: int = 22
    OPENVOICE_ENABLED: bool = False
    OPENVOICE_REPO_DIR: str = ""
    OPENVOICE_CHECKPOINTS_DIR: str = ""
    OPENVOICE_DEVICE: str = "auto"
    OPENVOICE_DEFAULT_MODEL_ID: str = "openvoice_v2"
    VOICE_LAB_MAX_REFERENCE_AUDIO_SIZE_BYTES: int = 150 * 1024 * 1024
    VOICE_LAB_ALLOWED_AUDIO_TYPES: str = "audio/wav,audio/x-wav,audio/mpeg,audio/mp3,audio/flac,audio/mp4,audio/x-m4a"
    VOICE_LAB_MAX_REFERENCE_EMBEDDING_SECONDS: float = 60.0
    VOICE_LAB_REFERENCE_CHUNK_SECONDS: float = 10.0
    VOICE_LAB_MIN_REFERENCE_CHUNK_SECONDS: float = 2.0
    VOICE_LAB_REFERENCE_SILENCE_THRESHOLD_DB: str = "-40dB"
    VOICE_LAB_REFERENCE_SILENCE_MIN_SECONDS: float = 0.35
    VOICE_MODELS_DIR: str = "backend/storage/voice_models"
    XTTS_ENABLED: bool = False
    XTTS_MODEL_DIR: str = ""
    XTTS_DEVICE: str = "auto"
    XTTS_WORKER_CACHE_ENABLED: bool = True
    XTTS_WORKER_CACHE_MAX_ENTRIES: int = 2
    XTTS_TORCH_INFERENCE_MODE_ENABLED: bool = True
    XTTS_CPU_NUM_THREADS: int = 0
    XTTS_CPU_INTEROP_THREADS: int = 0
    XTTS_PREVIEW_SPLIT_SENTENCES_OVERRIDE: str = ""
    RVC_ENABLED: bool = False
    RVC_MODELS_DIR: str = ""
    RVC_RMVPE_PATH: str = ""
    RVC_INFER_COMMAND: str = ""
    OLLAMA_ENABLED: bool = True
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"
    OLLAMA_TIMEOUT_SECONDS: float = 120.0
    OLLAMA_DRAFT_TIMEOUT_SECONDS: float = 35.0
    OLLAMA_TEMPERATURE: float = 0.7
    OLLAMA_SCRIPT_TEMPERATURE: float = 0.2
    OLLAMA_NUM_PREDICT: int = 800
    OLLAMA_NUM_CTX: int = 4096

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
    RATE_LIMIT_BACKEND: str = "redis"
    TRUST_PROXY_HEADERS: bool = False
    MAX_ACTIVE_GENERATION_JOBS_PER_USER: int = 2
    MAX_QUEUED_GENERATION_JOBS_TOTAL: int = 50
    MAX_ACTIVE_GENERATION_JOBS_TOTAL: int = 20
    BACKGROUND_UPLOAD_MAX_SIZE_BYTES: int = 100 * 1024 * 1024
    BACKGROUND_VIDEO_MAX_DURATION_SECONDS: float = 600.0
    PROJECT_STORAGE_QUOTA_BYTES: int = 2 * 1024 * 1024 * 1024
    SCRIPT_IMPORT_MAX_SIZE_BYTES: int = 256 * 1024
    SCRIPT_IMPORT_ALLOWED_TYPES: str = "text/plain,text/markdown,application/octet-stream"
    SCRIPT_IMPORT_ALLOWED_SUFFIXES: str = ".txt,.md,.markdown"
    CELERY_GENERATION_TASK_SOFT_TIME_LIMIT_SECONDS: int = 840
    CELERY_GENERATION_TASK_HARD_TIME_LIMIT_SECONDS: int = 900

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT.lower() == "dev"

    def validate_runtime(self) -> None:
        if not self.is_dev and self.SECRET_KEY in {"dev-only-change-me", "dev-secret-key"}:
            raise RuntimeError("SECRET_KEY must be set to a non-default value outside dev.")
        if not self.is_dev and not self.OAUTH_TOKEN_ENCRYPTION_KEY:
            raise RuntimeError("OAUTH_TOKEN_ENCRYPTION_KEY is required outside dev.")
        if not self.is_dev and not self.COOKIE_SECURE:
            raise RuntimeError("COOKIE_SECURE must be true outside dev.")
        if not self.is_dev and self.RATE_LIMIT_BACKEND.lower() != "redis":
            raise RuntimeError("RATE_LIMIT_BACKEND must be redis outside dev.")
        frontend_url = urlparse(self.FRONTEND_URL)
        if not self.is_dev and frontend_url.hostname in {"localhost", "127.0.0.1"}:
            raise RuntimeError("FRONTEND_URL must not point at localhost outside dev.")
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
