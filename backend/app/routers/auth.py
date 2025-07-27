from fastapi import APIRouter, Depends, HTTPException, status, Response, Body, Cookie
from pydantic import BaseModel
from app.services.auth import create_user, authenticate_user, _users_db, SECRET_KEY, ALGORITHM
import jwt

from app.models import User, UserResponse, TokenResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth")

class AuthPayload(BaseModel):
    username: str
    password: str

@router.post("/register", response_model=TokenResponse)
async def register(
    payload: AuthPayload = Body(...),
    response: Response = None
):
    """
    Register a new user via JSON payload, set access_token cookie, and return user info.
    """
    user = create_user(payload.username, payload.password)
    token = authenticate_user(payload.username, payload.password)
    response.set_cookie(key="access_token", value=token, httponly=True, secure=True, samesite="lax")
    
    return TokenResponse(access_token=token, token_type="bearer")

@router.post("/login", response_model=TokenResponse)
async def login(
    payload: AuthPayload = Body(...),
    response: Response = None
):
    """
    Authenticate via JSON payload, set access_token cookie.
    """
    token = authenticate_user(payload.username, payload.password)
    response.set_cookie(key="access_token", value=token, httponly=True, secure=True, samesite="lax")
    return TokenResponse(access_token=token, token_type="bearer")

@router.get("/me", response_model=UserResponse)
async def me_get(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user from cookie-based session.
    """
    return UserResponse(username=current_user.username)

@router.post("/logout")
async def logout(response: Response):
    """
    Logout user by clearing the HTTP-only cookie.
    """
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}

@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(payload: AuthPayload = Body(...)):
    """
    OAuth2-compatible token endpoint (no cookie, just token).
    Useful for API clients that only want tokens.
    """
    token = authenticate_user(payload.username, payload.password)
    return TokenResponse(access_token=token, token_type="bearer")
