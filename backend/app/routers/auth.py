from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_rate_limit import enforce_rate_limit, request_identity
from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import AuthRequest, AuthResponse, MeResponse, SessionInfo, UserSummary
from app.services.auth import authenticate_user, create_access_token, create_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    payload: AuthRequest = Body(...),
    response: Response = None,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        "auth.register",
        request_identity(request),
        limit=settings.AUTH_RATE_LIMIT_COUNT,
        window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    user = create_user(db, payload.username, payload.password)
    token, expires_at = create_access_token(user)
    _set_session_cookie(response, token)
    return AuthResponse(user=UserSummary(id=user.id, username=user.username), session=SessionInfo(expires_at=expires_at))


@router.post("/login", response_model=AuthResponse)
def login(
    request: Request,
    payload: AuthRequest = Body(...),
    response: Response = None,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        "auth.login",
        request_identity(request),
        limit=settings.AUTH_RATE_LIMIT_COUNT,
        window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    user = authenticate_user(db, payload.username, payload.password)
    token, expires_at = create_access_token(user)
    _set_session_cookie(response, token)
    return AuthResponse(user=UserSummary(id=user.id, username=user.username), session=SessionInfo(expires_at=expires_at))


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)):
    preferences = current_user.preferences
    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        preferences_summary={
            "default_platform": preferences.default_platform if preferences else "youtube",
            "default_social_account_id": preferences.default_social_account_id if preferences else None,
            "metadata_style": preferences.metadata_style if preferences else "default",
            "auto_select_default_account": preferences.auto_select_default_account if preferences else True,
        },
    )


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}
