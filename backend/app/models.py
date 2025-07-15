from pydantic import BaseModel, Field, HttpUrl, constr, validator
from typing import Optional, Dict

##########################
#Data models
###########################
class UploadResponse(BaseModel):
    project_id: str = Field(..., description="The ID of the created project") 

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"[a-zA-Z0-9_]+$")
    #email : emailStr
    password: str = Field(..., min_length=8)

    @validator('password')
    def validate_password_complexity(cls, v):
        if (not any(c.islower() for c in v) or
            not any(c.isupper() for c in v) or
            not any(c.isdigit() for c in v) or
            len(v) < 8):
            raise ValueError('Password must be at least 8 characters long and include uppercase, lowercase, and numeric characters.')
        return v

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)

class MeRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MeResponse(BaseModel):
    id: int
    username: str
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    username: str

class AccountCreate(BaseModel):
    platform: constr(pattern="^(youtube|tiktok|instagram)$")
    # OAuth callback would supply a code; here we simplify:
    oauth_code: str  

class AccountOut(BaseModel):
    id: int
    platform: str
    name: str
    profile_picture: HttpUrl
    stats: Dict[str, int]            # e.g. {"followers": 1234, "views": 5678}
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
