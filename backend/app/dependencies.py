# app/dependencies.py
from typing import Optional
from fastapi import Depends, HTTPException, status, Cookie, Header
from jose import JWTError, jwt

from app.services.auth import SECRET_KEY, ALGORITHM, USERS
from app.models import UserResponse

def get_current_user(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> UserResponse:
    token = (
        access_token
        or (authorization.split(" ")[1] if authorization and authorization.startswith("Bearer ") else None)
    )
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")  # type: ignore
        if not username:
            raise JWTError()
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user = USERS.get(username)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    return UserResponse(id=user["id"], username=username)
