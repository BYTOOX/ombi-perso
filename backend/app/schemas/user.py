"""User schemas for API validation."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

from ..models.user import UserRole, UserStatus


class UserBase(BaseModel):
    """Base user schema."""
    username: str = Field(..., min_length=3, max_length=100)
    email: Optional[EmailStr] = None


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str = Field(..., min_length=8)


class AdminUserCreate(UserBase):
    """Schema for admin creating a user (with optional password and status)."""
    password: Optional[str] = Field(None, min_length=8)
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.ACTIVE  # Admin-created users are active


class UserLogin(BaseModel):
    """Schema for user login."""
    username: str
    password: str


class PlexAuth(BaseModel):
    """Schema for Plex SSO authentication."""
    plex_token: str


class PlexLink(BaseModel):
    """Schema for linking Plex account to existing user."""
    plex_token: str


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None


class UserResponse(BaseModel):
    """Schema for user response."""
    id: int
    username: str
    email: Optional[str] = None
    plex_id: Optional[str] = None
    plex_username: Optional[str] = None
    plex_thumb: Optional[str] = None
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    is_active: bool
    daily_requests_count: int
    created_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    """Token payload data."""
    user_id: int
    username: str
    role: UserRole


class RegistrationResponse(BaseModel):
    """Response for registration (may not include token if pending)."""
    message: str
    pending: bool = True
    user: Optional[UserResponse] = None
    access_token: Optional[str] = None

