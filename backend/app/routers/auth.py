from fastapi import APIRouter, HTTPException, status, Response, Body, Cookie
from pydantic import BaseModel
from app.services.auth import create_user, authenticate_user, _users_db, SECRET_KEY, ALGORITHM
import jwt

from app.models import UserResponse

router = APIRouter(prefix="/auth")

class AuthPayload(BaseModel):
    username: str
    password: str

@router.post("/register", status_code=200, response_model=UserResponse)
async def register(
    payload: AuthPayload = Body(...),
    response: Response = None
):
    """
    Register a new user via JSON payload, set access_token cookie, and return user info.
    """
    user = create_user(payload.username, payload.password)
    token = authenticate_user(payload.username, payload.password)
    response.set_cookie(key="access_token", value=token, httponly=True)
    return UserResponse(username=user.username)

@router.post("/login", status_code=200)
async def login(
    payload: AuthPayload = Body(...),
    response: Response = None
):
    """
    Authenticate via JSON payload, set access_token cookie.
    """
    token = authenticate_user(payload.username, payload.password)
    response.set_cookie(key="access_token", value=token, httponly=True)
    return {"message": "login successful"}

@router.get("/me", status_code=200, response_model=UserResponse)
async def me_get(
    access_token: str = Cookie(None)
):
    """
    Get current user from cookie-based session.
    """
    if not access_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username or username not in _users_db:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
        return UserResponse(username=username)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

@router.post("/me", status_code=200, response_model=UserResponse)
async def me_post(
    payload: AuthPayload = Body(...),
    response: Response = None
):
    """
    Refresh authentication and cookie via JSON payload.
    """
    token = authenticate_user(payload.username, payload.password)
    response.set_cookie(key="access_token", value=token, httponly=True)
    return UserResponse(username=payload.username)