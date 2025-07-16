import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import jwt
from passlib.context import CryptContext

logger = logging.getLogger("uvicorn.error")

# secrets & config
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# password hashing context
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# simple in-memory user store (replace w/ real DB in prod)
USERS: Dict[str, Dict] = {}
USER_ID_COUNTER = 1

def get_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def register_user(username: str, password: str) -> int:
    global USER_ID_COUNTER
    if username in USERS:
        raise ValueError("Username already exists")
    hashed = get_hash(password)
    uid = USER_ID_COUNTER
    USER_ID_COUNTER += 1
    USERS[username] = {"id": uid, "hashed_password": hashed}
    logger.info(f"User registered: {username} (id={uid})")
    return uid

def authenticate_user(username: str, password: str) -> bool:
    user = USERS.get(username)
    return bool(user and verify_password(password, user["hashed_password"]))

def create_access_token(
    subject: str, expires_delta: Optional[timedelta] = None
) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": subject, "exp": expire}
    logger.debug(f"Issuing token for {subject}, expires {expire.isoformat()}")
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
