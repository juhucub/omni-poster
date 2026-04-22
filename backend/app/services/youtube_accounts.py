from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import SocialAccount
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.platforms import capability_for


class YouTubeOAuthError(RuntimeError):
    pass


def build_oauth_state(user_id: int) -> str:
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OAUTH_STATE_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "purpose": "youtube_oauth", "exp": expires_at}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def parse_oauth_state(state: str) -> int:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError as exc:
        raise YouTubeOAuthError("Invalid or expired OAuth state.") from exc

    if payload.get("purpose") != "youtube_oauth" or not payload.get("sub"):
        raise YouTubeOAuthError("Invalid OAuth state payload.")
    return int(payload["sub"])


def build_authorization_url(user_id: int) -> tuple[str, str]:
    state = build_oauth_state(user_id)
    query = urlencode(
        {
            "client_id": settings.YOUTUBE_CLIENT_ID,
            "redirect_uri": settings.YOUTUBE_REDIRECT_URI,
            "response_type": "code",
            "scope": settings.YOUTUBE_OAUTH_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}", state


def exchange_code_for_tokens(code: str) -> dict:
    response = httpx.post(
        settings.YOUTUBE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.YOUTUBE_CLIENT_ID,
            "client_secret": settings.YOUTUBE_CLIENT_SECRET,
            "redirect_uri": settings.YOUTUBE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def refresh_tokens(refresh_token: str) -> dict:
    response = httpx.post(
        settings.YOUTUBE_TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": settings.YOUTUBE_CLIENT_ID,
            "client_secret": settings.YOUTUBE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_channel_identity(access_token: str) -> dict:
    response = httpx.get(
        settings.YOUTUBE_CHANNELS_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items") or []
    if not items:
        raise YouTubeOAuthError("No YouTube channel is available for this Google account.")
    channel = items[0]
    return {
        "channel_id": channel["id"],
        "channel_title": channel["snippet"]["title"],
    }


def _expires_at_from_payload(payload: dict) -> datetime | None:
    expires_in = payload.get("expires_in")
    if not expires_in:
        return None
    return datetime.utcnow() + timedelta(seconds=int(expires_in))


def upsert_social_account(
    db: Session,
    *,
    user_id: int,
    channel_id: str,
    channel_title: str,
    access_token: str,
    refresh_token: str | None,
    expires_at: datetime | None,
) -> SocialAccount:
    account = (
        db.query(SocialAccount)
        .filter(
            SocialAccount.user_id == user_id,
            SocialAccount.platform == "youtube",
            SocialAccount.channel_id == channel_id,
        )
        .one_or_none()
    )
    if not account:
        account = SocialAccount(
            user_id=user_id,
            platform="youtube",
            account_type="owned_channel",
            channel_id=channel_id,
            channel_title=channel_title,
            capabilities_json=capability_for("youtube").default_capabilities,
        )
        db.add(account)

    account.channel_title = channel_title
    account.access_token_encrypted = encrypt_secret(access_token)
    if refresh_token:
        account.refresh_token_encrypted = encrypt_secret(refresh_token)
    account.token_expires_at = expires_at
    account.last_validated_at = datetime.utcnow()
    account.status = "linked"
    account.token_status = "healthy"
    db.flush()
    return account


def connect_account_from_code(db: Session, *, code: str, state: str) -> SocialAccount:
    user_id = parse_oauth_state(state)
    token_payload = exchange_code_for_tokens(code)
    access_token = token_payload["access_token"]
    channel = fetch_channel_identity(access_token)
    account = upsert_social_account(
        db,
        user_id=user_id,
        channel_id=channel["channel_id"],
        channel_title=channel["channel_title"],
        access_token=access_token,
        refresh_token=token_payload.get("refresh_token"),
        expires_at=_expires_at_from_payload(token_payload),
    )
    return account


def ensure_valid_access_token(db: Session, account: SocialAccount) -> str:
    access_token = decrypt_secret(account.access_token_encrypted)
    refresh_token = decrypt_secret(account.refresh_token_encrypted)
    now = datetime.utcnow()

    if access_token and (account.token_expires_at is None or account.token_expires_at > now + timedelta(minutes=2)):
        return access_token

    if not refresh_token:
        account.status = "reconnect_required"
        account.token_status = "refresh_missing"
        account.last_validated_at = now
        db.flush()
        raise YouTubeOAuthError("Reconnect required for this YouTube account.")

    try:
        payload = refresh_tokens(refresh_token)
    except httpx.HTTPError as exc:
        account.status = "reconnect_required"
        account.token_status = "expired"
        account.last_validated_at = now
        db.flush()
        raise YouTubeOAuthError("Could not refresh the YouTube access token.") from exc

    next_access_token = payload["access_token"]
    account.access_token_encrypted = encrypt_secret(next_access_token)
    if payload.get("refresh_token"):
        account.refresh_token_encrypted = encrypt_secret(payload["refresh_token"])
    account.token_expires_at = _expires_at_from_payload(payload)
    account.status = "linked"
    account.token_status = "healthy"
    account.last_validated_at = now
    db.flush()
    return next_access_token
