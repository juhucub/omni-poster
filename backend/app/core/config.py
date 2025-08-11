from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENVIRONMENT: str = "dev"
    API_PORT: int = 8000
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    YT_API_KEY: str | None = None
    YT_UNITS_PER_MIN: int = 900
    IG_REQ_PER_MIN: int = 200
    TT_REQ_PER_MIN: int = 200

    SENTRY_DSN: str | None = None
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = "omniposter-api"

    class Config:
        env_file = ".env.dev"

settings = Settings()
