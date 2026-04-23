from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.core.config import settings
from app.db import engine
from app.routers.assets import router as assets_router
from app.routers.auth import router as auth_router
from app.routers.character_presets import router as character_presets_router
from app.routers.generation import router as generation_router
from app.routers.history import router as history_router
from app.routers.metadata import router as metadata_router
from app.routers.projects import router as projects_router
from app.routers.publish import router as publish_router
from app.routers.reviews import router as reviews_router
from app.routers.routing import router as routing_router
from app.routers.scripts import router as scripts_router
from app.routers.social_accounts import router as social_accounts_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_runtime()
    logger.info("Runtime media directory: %s", settings.MEDIA_DIR)
    logger.info("Bundled media directory: %s", settings.BUNDLED_MEDIA_DIR)
    yield


app = FastAPI(title="Omni-poster", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(social_accounts_router)
app.include_router(projects_router)
app.include_router(assets_router)
app.include_router(character_presets_router)
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


@app.get("/health/live", status_code=status.HTTP_200_OK)
def liveness():
    return {"ok": True}
