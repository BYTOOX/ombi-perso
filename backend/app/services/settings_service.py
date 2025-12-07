"""
Settings service for managing system configuration stored in database.
Handles path settings (download_path, library_paths) that can be modified from admin panel.
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache

from ..models.database import SessionLocal
from ..models.system_settings import SystemSettings

logger = logging.getLogger(__name__)


# Default paths configuration
DEFAULT_DOWNLOAD_PATH = "/downloads"
DEFAULT_LIBRARY_PATHS = {
    "movie": "/media/Films",
    "animated_movie": "/media/Films d'animation",
    "series": "/media/Série TV",
    "animated_series": "/media/Série Animée",
    "anime": "/media/Animé (JAP)"
}


class SettingsService:
    """
    Service for managing system settings stored in database.
    Provides methods to get/set path configurations.
    """
    
    # Cache for settings to avoid DB queries on every call
    _cache: Dict[str, Any] = {}
    _cache_valid: bool = False
    
    def __init__(self):
        pass
    
    def _get_setting(self, key: str) -> Optional[str]:
        """Get a setting value from database."""
        with SessionLocal() as db:
            setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
            return setting.value if setting else None
    
    def _set_setting(self, key: str, value: str):
        """Set a setting value in database."""
        with SessionLocal() as db:
            setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
            if setting:
                setting.value = value
            else:
                setting = SystemSettings(key=key, value=value)
                db.add(setting)
            db.commit()
        
        # Invalidate cache
        self._cache_valid = False
    
    def get_download_path(self) -> str:
        """Get the download path for temporary torrent downloads."""
        value = self._get_setting("download_path")
        return value if value else DEFAULT_DOWNLOAD_PATH
    
    def set_download_path(self, path: str) -> bool:
        """Set the download path."""
        self._set_setting("download_path", path)
        logger.info(f"Download path updated to: {path}")
        return True
    
    def get_library_paths(self) -> Dict[str, str]:
        """Get library paths mapping (media_type -> path)."""
        value = self._get_setting("library_paths")
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.error("Failed to parse library_paths from DB")
        return DEFAULT_LIBRARY_PATHS.copy()
    
    def set_library_paths(self, paths: Dict[str, str]) -> bool:
        """Set library paths mapping."""
        self._set_setting("library_paths", json.dumps(paths, ensure_ascii=False))
        logger.info(f"Library paths updated: {paths}")
        return True
    
    def get_library_path(self, media_type: str) -> Optional[str]:
        """Get library path for a specific media type."""
        paths = self.get_library_paths()
        return paths.get(media_type)
    
    def get_all_path_settings(self) -> Dict[str, Any]:
        """
        Get all path settings with validation info.
        Returns structure suitable for admin panel display.
        """
        download_path = self.get_download_path()
        library_paths = self.get_library_paths()
        
        # Validate download path
        download_info = self._validate_path(download_path)
        
        # Validate each library path
        library_info = {}
        for media_type, path in library_paths.items():
            library_info[media_type] = {
                "path": path,
                **self._validate_path(path)
            }
        
        return {
            "download_path": {
                "path": download_path,
                **download_info
            },
            "library_paths": library_info
        }
    
    def update_all_path_settings(
        self, 
        download_path: str, 
        library_paths: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Update all path settings at once.
        Returns validation results.
        """
        errors = []
        
        # Validate download path
        if not download_path:
            errors.append("Download path is required")
        else:
            self.set_download_path(download_path)
        
        # Validate library paths
        if not library_paths:
            errors.append("Library paths are required")
        else:
            # Ensure all required types are present
            required_types = ["movie", "animated_movie", "series", "animated_series", "anime"]
            for media_type in required_types:
                if media_type not in library_paths:
                    errors.append(f"Missing path for media type: {media_type}")
            
            if not errors:
                self.set_library_paths(library_paths)
        
        if errors:
            return {"success": False, "errors": errors}
        
        return {"success": True, "settings": self.get_all_path_settings()}
    
    def _validate_path(self, path: str) -> Dict[str, Any]:
        """Validate a path and return status info."""
        p = Path(path)
        exists = p.exists()
        writable = exists and os.access(p, os.W_OK)
        
        return {
            "exists": exists,
            "writable": writable,
            "is_directory": p.is_dir() if exists else False
        }
    
    def browse_directory(self, path: str = "/") -> Dict[str, Any]:
        """
        List contents of a directory for file browser.
        Returns directories only (not files).
        """
        try:
            p = Path(path)
            
            if not p.exists():
                return {"error": f"Path does not exist: {path}", "items": []}
            
            if not p.is_dir():
                return {"error": f"Path is not a directory: {path}", "items": []}
            
            items = []
            
            # Add parent directory link if not at root
            if str(p) != "/" and p.parent != p:
                items.append({
                    "name": "..",
                    "path": str(p.parent),
                    "is_directory": True,
                    "is_parent": True
                })
            
            # List directories only
            try:
                for item in sorted(p.iterdir()):
                    if item.is_dir():
                        # Skip hidden directories
                        if item.name.startswith('.'):
                            continue
                        
                        items.append({
                            "name": item.name,
                            "path": str(item),
                            "is_directory": True,
                            "writable": os.access(item, os.W_OK)
                        })
            except PermissionError:
                return {"error": f"Permission denied: {path}", "items": []}
            
            return {
                "current_path": str(p),
                "items": items
            }
        
        except Exception as e:
            logger.error(f"Error browsing directory {path}: {e}")
            return {"error": str(e), "items": []}
    
    @property
    def media_types(self) -> List[str]:
        """Get all configured media types."""
        return list(self.get_library_paths().keys())
    
    # =========================================================================
    # RENAME SETTINGS
    # =========================================================================
    
    def get_rename_settings(self) -> Dict[str, Any]:
        """
        Get all rename settings.
        Returns settings with default values for any missing keys.
        """
        from ..models.rename_settings import RenameSettings
        
        with SessionLocal() as db:
            settings = db.query(RenameSettings).first()
            
            if not settings:
                return self._get_default_rename_settings()
            
            return {
                "id": settings.id,
                "preferred_language": settings.preferred_language,
                "title_language": settings.title_language,
                "movie_format": settings.movie_format,
                "series_format": settings.series_format,
                "anime_format": settings.anime_format,
                "include_tmdb_id": settings.include_tmdb_id,
                "include_tvdb_id": settings.include_tvdb_id,
                "replace_special_chars": settings.replace_special_chars,
                "special_char_map": settings.special_char_map,
                "anime_title_preference": settings.anime_title_preference,
                "use_ai_fallback": settings.use_ai_fallback,
                "updated_at": settings.updated_at.isoformat() if settings.updated_at else None
            }
    
    def _get_default_rename_settings(self) -> Dict[str, Any]:
        """Get default rename settings."""
        return {
            "id": None,
            "preferred_language": "french",
            "title_language": "english",
            "movie_format": "{title} ({year})",
            "series_format": "{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}",
            "anime_format": "{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}",
            "include_tmdb_id": False,
            "include_tvdb_id": False,
            "replace_special_chars": False,
            "special_char_map": None,
            "anime_title_preference": "english",
            "use_ai_fallback": True,
            "updated_at": None
        }
    
    def update_rename_settings(self, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update rename settings.
        Creates settings if they don't exist.
        """
        from ..models.rename_settings import RenameSettings
        
        with SessionLocal() as db:
            settings = db.query(RenameSettings).first()
            
            if not settings:
                # Create new settings
                settings = RenameSettings()
                db.add(settings)
            
            # Update fields
            for key, value in settings_data.items():
                if hasattr(settings, key) and key not in ["id", "updated_at"]:
                    setattr(settings, key, value)
            
            db.commit()
            db.refresh(settings)
            
            logger.info(f"Rename settings updated")
            return self.get_rename_settings()
    
    def get_movie_format(self) -> str:
        """Get movie naming format template."""
        settings = self.get_rename_settings()
        return settings.get("movie_format", "{title} ({year})")
    
    def get_series_format(self) -> str:
        """Get series naming format template."""
        settings = self.get_rename_settings()
        return settings.get("series_format", "{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}")
    
    def get_anime_format(self) -> str:
        """Get anime naming format template."""
        settings = self.get_rename_settings()
        return settings.get("anime_format", "{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}")
    
    # =========================================================================
    # TITLE MAPPINGS
    # =========================================================================
    
    def get_title_mappings(self, media_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all title mappings, optionally filtered by media type.
        """
        from ..models.rename_settings import TitleMapping
        
        with SessionLocal() as db:
            query = db.query(TitleMapping)
            
            if media_type:
                query = query.filter(TitleMapping.media_type == media_type)
            
            mappings = query.order_by(TitleMapping.created_at.desc()).all()
            
            return [
                {
                    "id": m.id,
                    "pattern": m.pattern,
                    "plex_title": m.plex_title,
                    "media_type": m.media_type,
                    "tmdb_id": m.tmdb_id,
                    "tvdb_id": m.tvdb_id,
                    "year": m.year,
                    "created_at": m.created_at.isoformat() if m.created_at else None
                }
                for m in mappings
            ]
    
    def add_title_mapping(
        self,
        pattern: str,
        plex_title: str,
        media_type: str,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Add a title mapping.
        """
        from ..models.rename_settings import TitleMapping
        
        with SessionLocal() as db:
            mapping = TitleMapping(
                pattern=pattern,
                plex_title=plex_title,
                media_type=media_type,
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                year=year
            )
            db.add(mapping)
            db.commit()
            db.refresh(mapping)
            
            logger.info(f"Title mapping added: {pattern} → {plex_title}")
            
            return {
                "id": mapping.id,
                "pattern": mapping.pattern,
                "plex_title": mapping.plex_title,
                "media_type": mapping.media_type,
                "tmdb_id": mapping.tmdb_id,
                "tvdb_id": mapping.tvdb_id,
                "year": mapping.year,
                "created_at": mapping.created_at.isoformat()
            }
    
    def remove_title_mapping(self, mapping_id: int) -> bool:
        """
        Remove a title mapping by ID.
        """
        from ..models.rename_settings import TitleMapping
        
        with SessionLocal() as db:
            mapping = db.query(TitleMapping).filter(TitleMapping.id == mapping_id).first()
            
            if not mapping:
                return False
            
            db.delete(mapping)
            db.commit()
            
            logger.info(f"Title mapping removed: ID {mapping_id}")
            return True
    
    def find_title_mapping(self, torrent_name: str, media_type: str) -> Optional[Dict[str, Any]]:
        """
        Find a matching title mapping for a torrent name.
        Uses glob pattern matching.
        """
        import fnmatch
        
        mappings = self.get_title_mappings(media_type)
        
        for mapping in mappings:
            # Use glob-style matching
            if fnmatch.fnmatch(torrent_name.lower(), mapping["pattern"].lower()):
                return mapping
        
        return None


# Singleton instance
_settings_service: Optional[SettingsService] = None


def get_settings_service() -> SettingsService:
    """Get settings service instance."""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service


def init_default_settings():
    """
    Initialize default settings in database if not present.
    Called during app startup.
    """
    service = get_settings_service()
    
    with SessionLocal() as db:
        # Check if settings exist
        existing = db.query(SystemSettings).first()
        
        if not existing:
            logger.info("Initializing default path settings in database...")
            
            # Set defaults
            service.set_download_path(DEFAULT_DOWNLOAD_PATH)
            service.set_library_paths(DEFAULT_LIBRARY_PATHS)
            
            logger.info("✓ Default path settings initialized")


def init_rename_settings():
    """
    Initialize default rename settings in database if not present.
    Called during app startup.
    """
    from ..models.rename_settings import RenameSettings
    
    service = get_settings_service()
    
    with SessionLocal() as db:
        existing = db.query(RenameSettings).first()
        
        if not existing:
            logger.info("Initializing default rename settings in database...")
            
            settings = RenameSettings()
            db.add(settings)
            db.commit()
            
            logger.info("✓ Default rename settings initialized")
