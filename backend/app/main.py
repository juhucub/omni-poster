from __future__ import annotations

import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.celery_app import celery
from app.core.config import settings
from app.db import engine
from app.infra.redis import redis_package_available, redis_ping, safe_redis_url
from app.api.assets import router as assets_router
from app.api.auth import router as auth_router
from app.api.character_presets import router as character_presets_router
from app.api.generation import router as generation_router
from app.api.history import router as history_router
from app.api.metadata import router as metadata_router
from app.api.productions import router as productions_router
from app.api.projects import router as projects_router
from app.api.publish import router as publish_router
from app.api.reviews import router as reviews_router
from app.api.routing import router as routing_router
from app.api.script_generation import router as script_generation_router
from app.api.scripts import router as scripts_router
from app.api.social_accounts import router as social_accounts_router
from app.services.tts import TTSOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _cors_allowed_origins() -> list[str]:
    origins = {settings.FRONTEND_URL}
    if settings.is_dev:
        origins.update({"http://localhost:3000", "http://127.0.0.1:3000"})
    return sorted(origin for origin in origins if origin)


def _csv_setting(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _migration_state() -> dict:
    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_cfg)
    expected_heads = set(script.get_heads())
    inspector = inspect(engine)
    if "alembic_version" not in inspector.get_table_names():
        return {"ok": False, "reason": "missing_alembic_version"}

    with engine.connect() as connection:
        current_rows = connection.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    current_heads = {row[0] for row in current_rows}
    return {"ok": current_heads == expected_heads, "current": sorted(current_heads), "expected": sorted(expected_heads)}


def _check_payload(ok: bool, **payload: object) -> dict:
    status_value = "ok" if ok else "error"
    if payload.get("optional") and not ok:
        status_value = "degraded"
    return {"status": status_value, "ok": ok, **payload}


def _database_check() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        migrations = _migration_state()
        return _check_payload(bool(migrations.get("ok")), connectivity="reachable", migrations=migrations)
    except Exception as exc:
        return _check_payload(False, connectivity="unreachable", error=f"{type(exc).__name__}: {exc}")


def _redis_check() -> dict:
    if not redis_package_available():
        return _check_payload(False, reason="redis_package_missing")
    try:
        pong = redis_ping(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        return _check_payload(bool(pong), url=safe_redis_url(settings.REDIS_URL))
    except Exception as exc:
        return _check_payload(False, url=safe_redis_url(settings.REDIS_URL), error=f"{type(exc).__name__}: {exc}")


def _celery_check() -> dict:
    try:
        inspector = celery.control.inspect(timeout=1.0)
        ping = inspector.ping() or {}
        active_queues = inspector.active_queues() or {}
        queues = sorted(
            {
                queue.get("name")
                for worker_queues in active_queues.values()
                for queue in worker_queues
                if isinstance(queue, dict) and queue.get("name")
            }
        )
        return _check_payload(bool(ping), workers=sorted(ping.keys()), queues=queues)
    except Exception as exc:
        return _check_payload(False, error=f"{type(exc).__name__}: {exc}")


def _storage_check() -> dict:
    media_dir = Path(settings.MEDIA_DIR)
    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        probe = media_dir / ".health_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return _check_payload(True, media_dir=str(media_dir), bundled_media_dir=settings.BUNDLED_MEDIA_DIR, writable=True)
    except Exception as exc:
        return _check_payload(False, media_dir=str(media_dir), bundled_media_dir=settings.BUNDLED_MEDIA_DIR, writable=False, error=f"{type(exc).__name__}: {exc}")


def _binary_check(binary_name: str) -> dict:
    path = shutil.which(binary_name)
    return _check_payload(bool(path), binary=path, reason=None if path else "missing_binary")


def _provider_checks() -> dict:
    state = TTSOrchestrator().provider_state()
    return {
        "tts_providers": _check_payload(any((item or {}).get("available") for item in state.values()), providers=state),
        "tts_fallback": _check_payload(bool((state.get("espeak") or {}).get("available")), **(state.get("espeak") or {})),
        "openvoice": _check_payload(
            bool((state.get("openvoice") or {}).get("available")),
            optional=True,
            enabled=settings.OPENVOICE_ENABLED,
            repo_dir=settings.OPENVOICE_REPO_DIR,
            checkpoints_dir=settings.OPENVOICE_CHECKPOINTS_DIR,
            **(state.get("openvoice") or {}),
        ),
        "xtts": _check_payload(bool((state.get("xtts") or {}).get("available")), optional=True, enabled=settings.XTTS_ENABLED, **(state.get("xtts") or {})),
        "rvc": _check_payload(bool((state.get("rvc") or {}).get("available")), optional=True, enabled=settings.RVC_ENABLED, **(state.get("rvc") or {})),
    }


def _overall_status(checks: dict[str, dict]) -> str:
    required = {"api", "database", "redis", "storage", "ffmpeg", "ffprobe", "tts_fallback"}
    if any((checks.get(name) or {}).get("status") == "error" for name in required):
        return "error"
    if any((check or {}).get("status") in {"error", "degraded"} for check in checks.values()):
        return "degraded"
    return "ok"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_runtime()
    logger.info("Runtime media directory: %s", settings.MEDIA_DIR)
    logger.info("Bundled media directory: %s", settings.BUNDLED_MEDIA_DIR)
    yield


app = FastAPI(title="Omni-poster", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=_csv_setting(settings.CORS_ALLOWED_METHODS),
    allow_headers=_csv_setting(settings.CORS_ALLOWED_HEADERS),
)

app.include_router(auth_router)
app.include_router(social_accounts_router)
app.include_router(projects_router)
app.include_router(productions_router)
app.include_router(assets_router)
app.include_router(character_presets_router)
app.include_router(script_generation_router)
app.include_router(scripts_router)
app.include_router(generation_router)
app.include_router(metadata_router)
app.include_router(routing_router)
app.include_router(reviews_router)
app.include_router(publish_router)
app.include_router(history_router)


@app.get("/health")
def healthcheck():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    migrations = _migration_state()
    if not migrations["ok"]:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ok": False, "database": "reachable", "migrations": migrations},
        )
    return {"ok": True, "database": "reachable", "migrations": migrations}


@app.get("/health/deep")
def deep_healthcheck():
    checks = {
        "api": _check_payload(True, role=settings.ENVIRONMENT),
        "database": _database_check(),
        "redis": _redis_check(),
        "celery": _celery_check(),
        "storage": _storage_check(),
        "ffmpeg": _binary_check("ffmpeg"),
        "ffprobe": _binary_check("ffprobe"),
        **_provider_checks(),
    }
    return {
        "status": _overall_status(checks),
        "checks": checks,
        "config": {
            "environment": settings.ENVIRONMENT,
            "media_dir": settings.MEDIA_DIR,
            "bundled_media_dir": settings.BUNDLED_MEDIA_DIR,
            "openvoice_enabled": settings.OPENVOICE_ENABLED,
            "xtts_enabled": settings.XTTS_ENABLED,
            "rvc_enabled": settings.RVC_ENABLED,
            "ollama_enabled": settings.OLLAMA_ENABLED,
            "render_profiling_enabled": settings.RENDER_PROFILING_ENABLED,
        },
    }


@app.get("/health/live", status_code=status.HTTP_200_OK)
def liveness():
    return {"ok": True}
