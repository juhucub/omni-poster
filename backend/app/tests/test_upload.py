from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def auth_cookies():
    username = f"asset_{int(time.time() * 1000000)}"
    response = client.post("/auth/register", json={"username": username, "password": "Password1"})
    assert response.status_code == 201
    return response.cookies


def test_social_account_dev_link_flow():
    cookies = auth_cookies()

    start = client.post("/social-accounts/youtube/connect/start", cookies=cookies)
    assert start.status_code == 200
    auth_url = start.json()["authorization_url"]
    assert "social-accounts/youtube/callback" in auth_url

    callback_path = auth_url.replace("http://localhost:8000", "")
    callback = client.get(callback_path, cookies=cookies)
    assert callback.status_code == 200
    assert callback.json()["platform"] == "youtube"

    listing = client.get("/social-accounts", cookies=cookies)
    assert listing.status_code == 200
    assert len(listing.json()["items"]) >= 1
