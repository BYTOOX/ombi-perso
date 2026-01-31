"""
Configuration management with full flexibility.
All settings can be overridden via environment variables.
"""
import json
from functools import lru_cache
from typing import Optional
from pydantic import Field
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
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/plex_kiosk_dev",
        description="Database URL (PostgreSQL recommended, SQLite for dev: sqlite+aiosqlite:///./data/kiosk.db)"
    )
    
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
    plex_machine_identifier: Optional[str] = Field(
        default=None,
        description="Machine identifier of the authorized Plex server (restricts SSO login)"
    )

    # qBittorrent
    qbittorrent_url: Optional[str] = Field(default=None, description="qBittorrent WebUI URL")
    qbittorrent_username: str = Field(default="admin", description="qBittorrent username")
    qbittorrent_password: str = Field(default="adminadmin", description="qBittorrent password")
    
    # Paths
    download_path: str = Field(default="/downloads", description="Temporary download folder")
    # NOTE: library_paths is stored as Optional[str] to prevent pydantic-settings 
    # from auto-parsing it as JSON (which fails on empty strings)
    # Use the library_paths_dict property to get the actual dict
    library_paths: Optional[str] = Field(
        default=None,
        description="Library paths as JSON string (managed via Admin Panel)"
    )
    
    # Notifications
    discord_webhook_url: Optional[str] = Field(default=None, description="Discord webhook URL")

    # CORS (Security)
    frontend_url: Optional[str] = Field(
        default=None,
        description="Frontend URL for production CORS (e.g., https://plex-kiosk.yourdomain.com)"
    )
    cors_origins: Optional[str] = Field(
        default=None,
        description="Comma-separated additional CORS origins (e.g., https://app.yourdomain.com,https://admin.yourdomain.com)"
    )

    # Limits
    max_requests_per_day: int = Field(default=10, description="Max requests per user per day")
    seed_duration_hours: int = Field(default=24, description="Hours to seed before deletion")
    max_download_size_gb: int = Field(default=1000, description="Max total download size in GB")
    
    @property
    def _default_library_paths(self) -> dict[str, str]:
        """Default library paths."""
        return {
            "movie": "/media/Films",
            "animated_movie": "/media/Films d'animation",
            "series": "/media/Série TV",
            "animated_series": "/media/Série Animée",
            "anime": "/media/Animé (JAP)"
        }
    
    @property
    def library_paths_dict(self) -> dict[str, str]:
        """Get library paths as a dictionary.
        
        Returns default paths if not configured or invalid JSON.
        """
        if not self.library_paths or self.library_paths.strip() == "":
            return self._default_library_paths
        
        try:
            parsed = json.loads(self.library_paths)
            if isinstance(parsed, dict):
                return parsed
            return self._default_library_paths
        except (json.JSONDecodeError, TypeError):
            return self._default_library_paths
    
    def get_library_path(self, media_type: str) -> Optional[str]:
        """Get library path for a media type."""
        return self.library_paths_dict.get(media_type)
    
    @property
    def media_types(self) -> list[str]:
        """Get all configured media types."""
        return list(self.library_paths_dict.keys())


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
