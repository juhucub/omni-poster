from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def unique_username(prefix: str = "user") -> str:
    return f"{prefix}_{int(time.time() * 1000000)}"


def create_authenticated_client() -> TestClient:
    username = unique_username()
    response = client.post("/auth/register", json={"username": username, "password": "Password1"})
    assert response.status_code == 201
    authed = TestClient(app)
    authed.cookies = response.cookies
    return authed


def test_auth_register_login_and_me():
    username = unique_username("auth")
    register = client.post("/auth/register", json={"username": username, "password": "Password1"})
    assert register.status_code == 201
    assert register.cookies.get("access_token")

    me = client.get("/auth/me", cookies=register.cookies)
    assert me.status_code == 200
    assert me.json()["username"] == username

    login = client.post("/auth/login", json={"username": username, "password": "Password1"})
    assert login.status_code == 200


def test_project_script_asset_and_metadata_flow():
    authed = create_authenticated_client()

    project = authed.post("/projects", json={"name": "First Project", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    script = authed.put(
        f"/projects/{project_id}/script",
        json={"raw_text": "<Host> Hello there\n<Guest> General Kenobi", "source": "manual"},
    )
    assert script.status_code == 200
    assert len(script.json()["current_revision"]["parsed_lines"]) == 2

    metadata = authed.post(f"/projects/{project_id}/metadata/youtube/suggest")
    assert metadata.status_code == 200
    assert metadata.json()["platform"] == "youtube"
