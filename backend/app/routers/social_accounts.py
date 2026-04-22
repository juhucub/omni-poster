from __future__ import annotations

from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_rate_limit import enforce_rate_limit, request_identity
from app.dependencies import get_current_user, get_db
from app.models import SocialAccount, User
from app.schemas import OAuthStartResponse, OkResponse, SocialAccountListResponse
from app.services.routing import is_account_routing_eligible, to_social_account_summary
from app.services.youtube_accounts import (
    YouTubeOAuthError,
    build_authorization_url,
    connect_account_from_code,
    ensure_valid_access_token,
)

router = APIRouter(prefix="/social-accounts", tags=["social_accounts"])


@router.get("", response_model=SocialAccountListResponse)
def list_social_accounts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == current_user.id, SocialAccount.status != "revoked")
        .order_by(SocialAccount.default_preference_rank.asc(), SocialAccount.created_at.desc())
        .all()
    )
    return SocialAccountListResponse(
        items=[
            to_social_account_summary(account).model_copy(
                update={"routing_eligible": is_account_routing_eligible(account, platform=account.platform)}
            )
            for account in accounts
        ]
    )


@router.post("/youtube/connect/start", response_model=OAuthStartResponse)
def start_youtube_connect(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    if not settings.YOUTUBE_CONNECT_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="YouTube linking is disabled.")
    if not settings.YOUTUBE_CLIENT_ID or not settings.YOUTUBE_REDIRECT_URI:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube OAuth is not configured.",
        )

    enforce_rate_limit(
        "oauth.youtube.start",
        f"{current_user.id}:{request_identity(request)}",
        limit=settings.HEAVY_ENDPOINT_RATE_LIMIT_COUNT,
        window_seconds=settings.HEAVY_ENDPOINT_RATE_LIMIT_WINDOW_SECONDS,
    )
    authorization_url, state = build_authorization_url(current_user.id)
    return OAuthStartResponse(authorization_url=authorization_url, state=state)


@router.get("/youtube/callback")
def youtube_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        account = connect_account_from_code(db, code=code, state=state)
        db.commit()
        target = f"{settings.FRONTEND_URL.rstrip('/')}/accounts?youtube_oauth=success&account_id={account.id}"
    except YouTubeOAuthError as exc:
        db.rollback()
        target = (
            f"{settings.FRONTEND_URL.rstrip('/')}/accounts?youtube_oauth=error&message="
            f"{quote_plus(str(exc))}"
        )
    except Exception:
        db.rollback()
        target = f"{settings.FRONTEND_URL.rstrip('/')}/accounts?youtube_oauth=error&message=OAuth%20exchange%20failed"
    return RedirectResponse(url=target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post("/{account_id}/refresh")
def refresh_social_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.id == account_id, SocialAccount.user_id == current_user.id)
        .one_or_none()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Social account not found")

    try:
        ensure_valid_access_token(db, account)
        db.commit()
    except YouTubeOAuthError as exc:
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.refresh(account)
    return to_social_account_summary(account)


@router.delete("/{account_id}", response_model=OkResponse)
def disconnect_social_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.id == account_id, SocialAccount.user_id == current_user.id)
        .one_or_none()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")
    account.status = "revoked"
    account.token_status = "revoked"
    db.commit()
    return OkResponse()
