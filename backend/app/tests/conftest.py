from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_omniposter.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("OAUTH_TOKEN_ENCRYPTION_KEY", "test-oauth-encryption-key")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("MEDIA_DIR", "test_storage")
os.environ.setdefault("YOUTUBE_CLIENT_ID", "youtube-client-id")
os.environ.setdefault("YOUTUBE_CLIENT_SECRET", "youtube-client-secret")
os.environ.setdefault("YOUTUBE_REDIRECT_URI", "http://testserver/social-accounts/youtube/callback")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.http_rate_limit import _WINDOWS
from app.db import Base, engine
from app.main import app

TEST_DB_PATH = Path("test_omniposter.db")
TEST_MEDIA_DIR = Path("test_storage")
ALEMBIC_REVISION = "20260421_0001"


@pytest.fixture(autouse=True)
def reset_environment():
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": ALEMBIC_REVISION},
        )
    _WINDOWS.clear()
    if TEST_MEDIA_DIR.exists():
        shutil.rmtree(TEST_MEDIA_DIR)
    TEST_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    yield
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    if TEST_MEDIA_DIR.exists():
        shutil.rmtree(TEST_MEDIA_DIR)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def unique_username(prefix: str = "user") -> str:
    return f"{prefix}_{int(time.time() * 1000000)}"


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    username = unique_username()
    response = client.post("/auth/register", json={"username": username, "password": "Password1"})
    assert response.status_code == 201
    authed = TestClient(app)
    authed.cookies = response.cookies
    try:
        yield authed
    finally:
        authed.close()
