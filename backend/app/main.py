from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import Base, engine
from app.routers.assets import router as assets_router
from app.routers.auth import router as auth_router
from app.routers.generation import router as generation_router
from app.routers.history import router as history_router
from app.routers.metadata import router as metadata_router
from app.routers.preferences import router as preferences_router
from app.routers.projects import router as projects_router
from app.routers.publish import router as publish_router
from app.routers.scripts import router as scripts_router
from app.routers.social_accounts import router as social_accounts_router

app = FastAPI(title="Omni-poster")
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(preferences_router)
app.include_router(social_accounts_router)
app.include_router(projects_router)
app.include_router(assets_router)
app.include_router(scripts_router)
app.include_router(generation_router)
app.include_router(metadata_router)
app.include_router(publish_router)
app.include_router(history_router)


@app.get("/health")
def healthcheck():
    return {"ok": True}
