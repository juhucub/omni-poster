from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_preferences_round_trip():
    username = f"prefs_{int(time.time() * 1000000)}"
    register = client.post("/auth/register", json={"username": username, "password": "Password1"})
    assert register.status_code == 201

    get_response = client.get("/preferences", cookies=register.cookies)
    assert get_response.status_code == 200
    assert get_response.json()["preferences"]["default_platform"] == "youtube"

    patch_response = client.patch(
        "/preferences",
        json={"metadata_style": "punchy", "auto_select_default_account": False},
        cookies=register.cookies,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["preferences"]["metadata_style"] == "punchy"
