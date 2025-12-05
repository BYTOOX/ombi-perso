"""User model with role-based access control."""
from datetime import datetime, date
from enum import Enum
from sqlalchemy import String, Boolean, DateTime, Date, Integer, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List, TYPE_CHECKING

from .database import Base

if TYPE_CHECKING:
    from .request import MediaRequest


class UserRole(str, Enum):
    """User roles."""
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """User model with Plex SSO support."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Plex SSO
    plex_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    plex_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    plex_thumb: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Role & status
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Request limits
    daily_requests_count: Mapped[int] = mapped_column(Integer, default=0)
    last_request_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    requests: Mapped[List["MediaRequest"]] = relationship("MediaRequest", back_populates="user")
    
    def can_make_request(self, max_requests: int) -> bool:
        """Check if user can make a new request today."""
        today = date.today()
        if self.last_request_date != today:
            return True
        return self.daily_requests_count < max_requests
    
    def increment_request_count(self):
        """Increment daily request count."""
        today = date.today()
        if self.last_request_date != today:
            self.daily_requests_count = 1
            self.last_request_date = today
        else:
            self.daily_requests_count += 1
    
    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == UserRole.ADMIN
    
    def __repr__(self):
        return f"<User {self.username}>"
