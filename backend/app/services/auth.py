from __future__ import annotations

from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuditLog, User, UserPreference

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(user: User) -> tuple[str, datetime]:
    expires_at = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user.id), "username": user.username, "exp": expires_at}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM), expires_at


def create_user(db: Session, username: str, password: str) -> User:
    existing = db.query(User).filter(User.username == username).one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.flush()

    preferences = UserPreference(user_id=user.id, allowed_platforms_json=["youtube"])
    db.add(preferences)
    db.add(
        AuditLog(
            user_id=user.id,
            action="user.registered",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"username": username},
        )
    )
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.query(User).filter(User.username == username).one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    user.last_login_at = datetime.utcnow()
    db.add(
        AuditLog(
            user_id=user.id,
            action="user.logged_in",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"username": username},
        )
    )
    db.commit()
    db.refresh(user)
    return user
