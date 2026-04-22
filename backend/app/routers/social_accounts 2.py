from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.dependencies import get_current_user, get_db
from app.models import SocialAccount, User
from app.schemas import OAuthStartResponse, OkResponse, SocialAccountListResponse, SocialAccountSummary

router = APIRouter(prefix="/social-accounts", tags=["social_accounts"])


def to_social_summary(account: SocialAccount) -> SocialAccountSummary:
    return SocialAccountSummary(
        id=account.id,
        platform=account.platform,
        channel_id=account.channel_id,
        channel_title=account.channel_title,
        status=account.status,
        last_validated_at=account.last_validated_at,
    )


@router.get("", response_model=SocialAccountListResponse)
def list_social_accounts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == current_user.id, SocialAccount.status != "revoked")
        .order_by(SocialAccount.created_at.desc())
        .all()
    )
    return SocialAccountListResponse(items=[to_social_summary(account) for account in accounts])


@router.post("/youtube/connect/start", response_model=OAuthStartResponse)
def start_youtube_connect(current_user: User = Depends(get_current_user)):
    if settings.YOUTUBE_CLIENT_ID and settings.YOUTUBE_REDIRECT_URI:
        query = urlencode(
            {
                "client_id": settings.YOUTUBE_CLIENT_ID,
                "redirect_uri": settings.YOUTUBE_REDIRECT_URI,
                "response_type": "code",
                "scope": "https://www.googleapis.com/auth/youtube.upload",
                "access_type": "offline",
                "prompt": "consent",
                "state": str(current_user.id),
            }
        )
        return OAuthStartResponse(authorization_url=f"https://accounts.google.com/o/oauth2/v2/auth?{query}")

    dev_query = urlencode(
        {
            "channel_id": f"demo-channel-{current_user.id}",
            "channel_title": f"{current_user.username} Demo Channel",
            "state": str(current_user.id),
        }
    )
    return OAuthStartResponse(
        authorization_url=f"http://localhost:8000/social-accounts/youtube/callback?{dev_query}"
    )


@router.get("/youtube/callback", response_model=SocialAccountSummary)
def youtube_callback(
    channel_id: str = Query(...),
    channel_title: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(SocialAccount)
        .filter(
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == "youtube",
            SocialAccount.channel_id == channel_id,
        )
        .one_or_none()
    )
    if not account:
        account = SocialAccount(
            user_id=current_user.id,
            platform="youtube",
            channel_id=channel_id,
            channel_title=channel_title,
        )
        db.add(account)
    account.channel_title = channel_title
    account.status = "linked"
    account.last_validated_at = datetime.utcnow()
    account.token_expires_at = datetime.utcnow() + timedelta(days=30)
    db.commit()
    db.refresh(account)
    return to_social_summary(account)


@router.post("/{account_id}/refresh", response_model=SocialAccountSummary)
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
    account.status = "linked"
    account.last_validated_at = datetime.utcnow()
    account.token_expires_at = datetime.utcnow() + timedelta(days=30)
    db.commit()
    db.refresh(account)
    return to_social_summary(account)


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
        raise HTTPException(status_code=404, detail="Social account not found")
    account.status = "revoked"
    db.commit()
    return OkResponse()
