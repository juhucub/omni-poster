from pydantic import BaseModel, Field, HttpUrl, constr, validator
from typing import Optional, Dict
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint, BigInteger, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

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

# ─── Video Generation Models ────────────────────────────

class GenerateVideoRequest(BaseModel):
    """Request model for video generation."""
    project_id: str
    output_format: Optional[str] = "mp4"
    quality: Optional[str] = "high"  # low, medium, high
    aspect_ratio: Optional[str] = "16:9"  # 16:9, 9:16, 1:1

class GenerateVideoResponse(BaseModel):
    """Response model for video generation."""
    project_id: str
    status: str  # processing, completed, failed
    video_url: Optional[str] = None
    progress: Optional[int] = None
    message: str
    processing_time_seconds: Optional[float] = None
    output_file_size: Optional[int] = None

# ─── Enhanced Upload Response ────────────────────────────

class UploadResponse(BaseModel):
    project_id: str
    urls: Dict[str, str]

class Creator(Base):
    __tablename__ = "creators"
    id = Column(Integer, primary_key=True)
    platform = Column(String, index=True)
    external_id = Column(String, index=True)
    handle = Column(String)
    display_name = Column(String)
    etag = Column(String)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uix_creator"),)

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"))
    external_id = Column(String, index=True)
    title = Column(String)
    description = Column(Text)
    published_at = Column(DateTime, index=True)
    content_type = Column(String)  # e.g., "SHORT", "REEL", "VIDEO"
    duration_s = Column(Integer)
    __table_args__ = (UniqueConstraint("creator_id", "external_id", name="uix_video"),)
    creator = relationship("Creator")

class StatsSnapshot(Base):
    __tablename__ = "stats_snapshots"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    views = Column(BigInteger, default=0)
    likes = Column(BigInteger, default=0)
    comments = Column(BigInteger, default=0)
    shares = Column(BigInteger, default=0)