import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.upload import UPLOAD_DB, UPLOAD_DIR

client = TestClient(app)

@pytest.fixture(scope="function")
def auth_headers():
    """Create a test user and return auth headers."""
    # Register a test user
    response = client.post("/auth/register", json={
        "username": "testuser", 
        "password": "TestPass123"
    })
    assert response.status_code == 200
    
    # Login to get auth cookie
    response = client.post("/auth/login", json={
        "username": "testuser", 
        "password": "TestPass123"
    })
    assert response.status_code == 200
    
    # Extract cookies for subsequent requests
    return {"cookies": response.cookies}

@pytest.fixture(scope="function", autouse=True)
def cleanup_test_files():
    """Clean up test files before and after each test."""
    # Clean before test
    if os.path.exists(UPLOAD_DB):
        os.remove(UPLOAD_DB)
    if os.path.isdir(UPLOAD_DIR):
        for fn in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, fn)
            if os.path.isfile(path):
                os.remove(path)
    
    yield
    
    # Clean after test (optional, but good practice)
    #if os.path.exists(UPLOAD_DB):
    #    os.remove(UPLOAD_DB)
    #if os.path.isdir(UPLOAD_DIR):
    #    for