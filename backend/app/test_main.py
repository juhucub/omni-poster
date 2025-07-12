from fastapi.testclient import TestClient
from .main import app #import FastAPI app

client = TestClient(app)

def test_upload_success():
    files = {
        "video": ("test_video.mp4", b"dummy", "video/mp4"),
        "audio": ("test_audio.mp3", b"dummy", "audio/mpeg"),
    }
    response = client.post("/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert "project_id" in data

def test_upload_unsupported_media_type():
    files = {
    "video": ("test_video.mp4", b"dummy", "text/plain"),  # Unsupported type
    "audio": ("test_audio.mp3", b"dummy", "audio/mpeg"),
}
    response = client.post("/upload", files=files)  
    assert response.status_code == 415

def test_generate_video_not_found():
    files = {
        "audio": ("test_audio.mp3", b"dummy", "audio/mpeg"),
    }
    response = client.post("/upload", files=files)
    assert response.status_code == 422

def test_generate_video_success():
    # Assuming the generate_video endpoint is implemented
    response = client.post("/generate_video", json={"project_id": "some_project_id"})
    assert response.status_code == 200
    data = response.json()
    assert "video_url" in data

def test_register_and_cookie():
    response = client.post("/auth/register", json={"username": "testuser", "password": "John123!"})
    assert response.status_code == 200 and response.cookies.get("access_token")

def test_register_dup_username():
    client.post('/auth/register', json={'username':'dup','password':'Password1'})
    r = client.post('/auth/register', json={'username':'dup','password':'Password1'})
    assert r.status_code == 400


def test_login_success():
    client.post('/auth/register', json={'username':'user1','password':'Password1'})
    r = client.post('/auth/login', json={'username':'user1','password':'Password1'})
    assert r.status_code == 200


def test_login_invalid():
    r = client.post('/auth/login', json={'username':'nouser','password':'wrongpass'})
    assert r.status_code == 401


def test_me_endpoint1():
    client.post('/auth/register', json={'username':'alice','password':'Password1'})
    r = client.get('/auth/me')  # supports GET now
    assert r.status_code == 200 and r.json()['username']=='alice'

def test_me_endpoint2():
    # register then me
    client.post('/auth/register', json={'username':'alice','password':'Password1!'})
    response=client.post('/auth/me', json={'username':'alice','password':'Password1!'})
    assert response.status_code==200
    data=response.json()
    assert data['username']=='alice' and 'access_token' in data