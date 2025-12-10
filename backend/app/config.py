"""
Configuration management with full flexibility.
All settings can be overridden via environment variables.
"""
import json
from functools import lru_cache
from typing import Dict, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Application
    app_name: str = Field(default="plex-kiosk", description="Application name")
    app_port: int = Field(default=8765, description="Application port")
    secret_key: str = Field(default="change-me-in-production", description="JWT secret key")
    debug: bool = Field(default=False, description="Debug mode")
    
    # Database
    database_url: str = Field(default="sqlite:///./data/kiosk.db", description="Database URL")
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL")
    
    # FlareSolverr
    flaresolverr_url: str = Field(default="http://localhost:8191/v1", description="FlareSolverr URL")
    
    # YggAPI (unofficial API - bypasses Cloudflare)
    yggapi_url: str = Field(default="https://yggapi.eu", description="YggAPI URL (unofficial, no Cloudflare)")
    
    # Ollama (Local AI) - MUST be configured in .env
    ollama_url: Optional[str] = Field(default=None, description="Ollama API URL - REQUIRED")
    ollama_model: Optional[str] = Field(default=None, description="Ollama model name - REQUIRED")
    
    # TMDB
    tmdb_api_key: Optional[str] = Field(default=None, description="TMDB API key")
    
    # YGGtorrent
    ygg_base_url: str = Field(default="https://www.yggtorrent.top", description="YGGtorrent base URL (changes frequently)")
    ygg_username: Optional[str] = Field(default=None, description="YGG username")
    ygg_password: Optional[str] = Field(default=None, description="YGG password")
    ygg_passkey: Optional[str] = Field(default=None, description="YGG passkey for direct torrent links")
    
    # Plex
    plex_url: Optional[str] = Field(default=None, description="Plex server URL")
    plex_token: Optional[str] = Field(default=None, description="Plex token")
    
    # qBittorrent
    qbittorrent_url: Optional[str] = Field(default=None, description="qBittorrent WebUI URL")
    qbittorrent_username: str = Field(default="admin", description="qBittorrent username")
    qbittorrent_password: str = Field(default="adminadmin", description="qBittorrent password")
    
    # Paths
    download_path: str = Field(default="/downloads", description="Temporary download folder")
    library_paths: Dict[str, str] = Field(
        default={
            "movie": "/media/Films",
            "animated_movie": "/media/Films d'animation",
            "series": "/media/Série TV",
            "animated_series": "/media/Série Animée",
            "anime": "/media/Animé (JAP)"
        },
        description="Library paths mapping (type -> path)"
    )
    
    # Notifications
    discord_webhook_url: Optional[str] = Field(default=None, description="Discord webhook URL")
    
    # Limits
    max_requests_per_day: int = Field(default=10, description="Max requests per user per day")
    seed_duration_hours: int = Field(default=24, description="Hours to seed before deletion")
    max_download_size_gb: int = Field(default=1000, description="Max total download size in GB")
    
    @field_validator("library_paths", mode="before")
    @classmethod
    def parse_library_paths(cls, v):
        """Parse library_paths from JSON string if needed.
        
        Returns default paths if value is empty/None (paths managed via Admin Panel).
        """
        # Default paths - used when not configured via env
        default_paths = {
            "movie": "/media/Films",
            "animated_movie": "/media/Films d'animation",
            "series": "/media/Série TV",
            "animated_series": "/media/Série Animée",
            "anime": "/media/Animé (JAP)"
        }
        
        # Handle None or empty string
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return default_paths
        
        # Parse JSON string
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Invalid JSON, return defaults
                return default_paths
        
        return v
    
    def get_library_path(self, media_type: str) -> Optional[str]:
        """Get library path for a media type."""
        return self.library_paths.get(media_type)
    
    @property
    def media_types(self) -> list[str]:
        """Get all configured media types."""
        return list(self.library_paths.keys())


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
