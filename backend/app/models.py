from pydantic import BaseModel, Field, HttpUrl, constr, validator
from typing import Optional, Dict

# ─── Shared responses ────────────────────────────────────

class UploadResponse(BaseModel):
    project_id: str
    urls: Dict[str, str]

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class User(BaseModel):
    username: str
    hashed_password: str
class UserResponse(BaseModel):
    username: str

# ─── Auth requests/responses ────────────────────────────

class RegisterRequest(BaseModel):
    username: constr(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: constr(min_length=8)

    @validator("password")
    def password_complexity(cls, v: str) -> str:
        if not (
            any(c.islower() for c in v)
            and any(c.isupper() for c in v)
            and any(c.isdigit() for c in v)
        ):
            raise ValueError(
                "Password must be at least 8 chars and include upper, lower, digit."
            )
        return v

class LoginRequest(BaseModel):
    username: constr(min_length=3)
    password: constr(min_length=8)

# Used internally by the client-side flow to re-auth on form-submit
class MeRequest(BaseModel):
    username: constr(min_length=3)
    password: constr(min_length=8)

class MeResponse(UserResponse):
    access_token: str
    token_type: str = "bearer"

# ─── Account endpoints (stubs) ──────────────────────────

class AccountCreate(BaseModel):
    platform: constr(pattern="^(youtube|tiktok|instagram)$")
    oauth_code: str

class AccountOut(BaseModel):
    id: int
    platform: str
    name: str
    profile_picture: HttpUrl
    stats: Dict[str, int]
    status: constr(pattern="^(authorized|token_expired|rate_warning)$")

class MetricsOut(BaseModel):
    followers: int
    views: int
    likes: int

class GoalIn(BaseModel):
    views: Optional[int]
    likes: Optional[int]
    followers: Optional[int]

class Message(BaseModel):
    detail: str
