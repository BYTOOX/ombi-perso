"""
Service configuration model for storing external service credentials in database.
Replaces .env for service configuration (Plex, qBittorrent, AI, YGG, TMDB, Discord).
All sensitive data is encrypted using Fernet symmetric encryption.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from sqlalchemy import String, Text, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ServiceName(str, Enum):
    """Available external services."""
    PLEX = "plex"
    QBITTORRENT = "qbittorrent"
    AI = "ai"  # llama.cpp / Ollama
    YGG = "ygg"  # YGGtorrent
    TMDB = "tmdb"
    DISCORD = "discord"
    FLARESOLVERR = "flaresolverr"
    YGGAPI = "yggapi"


class HealthStatus(str, Enum):
    """Service health status."""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    NOT_CONFIGURED = "not_configured"
    DISABLED = "disabled"


class ServiceConfiguration(Base):
    """
    Configuration for external services.
    Stores connection details with encrypted sensitive data.
    """

    __tablename__ = "service_configurations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Service identifier
    service_name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True
    )

    # Display name for UI
    display_name: Mapped[str] = mapped_column(String(100), default="")

    # Connection settings
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Encrypted sensitive fields (Fernet encrypted, base64 encoded)
    password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Service-specific configuration (JSON)
    # Examples:
    # - AI: {"model": "qwen3-vl-30b", "timeout": 120}
    # - YGG: {"passkey": "...", "base_url": "..."}
    # - Plex: {"library_ids": [1, 2, 3]}
    extra_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Status
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Health check tracking
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_health_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_health_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_health_latency_ms: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<ServiceConfiguration {self.service_name} enabled={self.is_enabled}>"

    def to_dict(self, include_secrets: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            "id": self.id,
            "service_name": self.service_name,
            "display_name": self.display_name,
            "url": self.url,
            "username": self.username,
            "extra_config": self.extra_config or {},
            "is_enabled": self.is_enabled,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "last_health_status": self.last_health_status,
            "last_health_message": self.last_health_message,
            "last_health_latency_ms": self.last_health_latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        # Indicate if secrets are set (but don't return actual values)
        result["has_password"] = bool(self.password_encrypted)
        result["has_api_key"] = bool(self.api_key_encrypted)
        result["has_token"] = bool(self.token_encrypted)

        return result
