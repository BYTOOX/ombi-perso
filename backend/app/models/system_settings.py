"""
System settings model for storing configuration in database.
Replaces .env for paths configuration (download_path, library_paths).
"""
from datetime import datetime

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SystemSettings(Base):
    """
    Key-value store for system settings.
    Used for paths configuration that can be modified from admin panel.
    """
    
    __tablename__ = "system_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Setting key (e.g., "download_path", "library_paths")
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    
    # Setting value (JSON string for complex values)
    value: Mapped[str] = mapped_column(Text)
    
    # Metadata
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    def __repr__(self):
        return f"<SystemSettings {self.key}={self.value[:50]}...>"
