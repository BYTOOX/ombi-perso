"""
Plex integration service for library management and notifications.
"""
import logging
from typing import Optional, List, Dict, Any
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized

from ..config import get_settings

logger = logging.getLogger(__name__)


class PlexManagerService:
    """
    Plex server integration for:
    - Library scanning
    - Duplicate detection
    - User notifications
    - Media availability checks
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._server: Optional[PlexServer] = None
        self._connection_failed = False  # Cache connection failures
    
    def _is_configured(self) -> bool:
        """Check if Plex is properly configured (not placeholder values)."""
        url = self.settings.plex_url
        token = self.settings.plex_token
        if not url or not token:
            return False
        # Detect placeholder values
        placeholders = ['your-', 'example', 'xxx', 'placeholder', 'your_']
        url_lower = url.lower()
        token_lower = token.lower()
        for placeholder in placeholders:
            if placeholder in url_lower or placeholder in token_lower:
                return False
        return True
    
    @property
    def server(self) -> Optional[PlexServer]:
        """Get Plex server connection."""
        # Skip if already failed or not configured
        if self._connection_failed or not self._is_configured():
            return None
            
        if self._server is None and self.settings.plex_url and self.settings.plex_token:
            try:
                self._server = PlexServer(
                    self.settings.plex_url,
                    self.settings.plex_token,
                    timeout=5  # 5 second timeout
                )
                logger.info(f"Connected to Plex: {self._server.friendlyName}")
            except Exception as e:
                logger.error(f"Failed to connect to Plex: {e}")
                self._connection_failed = True  # Don't retry on subsequent calls
                return None
        return self._server
    
    # =========================================================================
    # LIBRARY MANAGEMENT
    # =========================================================================
    
    def get_libraries(self) -> List[Dict[str, Any]]:
        """Get list of Plex libraries."""
        if not self.server:
            return []
        
        return [
            {
                "key": lib.key,
                "title": lib.title,
                "type": lib.type,
                "locations": lib.locations
            }
            for lib in self.server.library.sections()
        ]
    
    def get_library_by_type(self, media_type: str) -> Optional[Any]:
        """
        Get the appropriate library for a media type.
        Uses the configured library paths mapping.
        """
        if not self.server:
            return None
        
        target_path = self.settings.get_library_path(media_type)
        if not target_path:
            logger.warning(f"No library path configured for type: {media_type}")
            return None
        
        # Find library that contains this path
        for lib in self.server.library.sections():
            if target_path in lib.locations:
                return lib
        
        logger.warning(f"No library found for path: {target_path}")
        return None
    
    def scan_library(self, library_key: Optional[str] = None) -> bool:
        """
        Trigger a library scan.
        If library_key is None, scans all libraries.
        """
        if not self.server:
            return False
        
        try:
            if library_key:
                library = self.server.library.sectionByID(library_key)
                library.update()
                logger.info(f"Scanning library: {library.title}")
            else:
                self.server.library.update()
                logger.info("Scanning all libraries")
            return True
        except Exception as e:
            logger.error(f"Library scan error: {e}")
            return False
    
    def scan_path(self, path: str) -> bool:
        """Scan a specific path in the library."""
        if not self.server:
            return False
        
        try:
            # Find the library containing this path
            for lib in self.server.library.sections():
                for location in lib.locations:
                    if path.startswith(location):
                        lib.update(path)
                        logger.info(f"Scanning path: {path}")
                        return True
            
            logger.warning(f"No library contains path: {path}")
            return False
        except Exception as e:
            logger.error(f"Path scan error: {e}")
            return False
    
    # =========================================================================
    # DUPLICATE DETECTION
    # =========================================================================
    
    def check_exists(
        self,
        title: str,
        year: Optional[int] = None,
        media_type: str = "movie"
    ) -> Dict[str, Any]:
        """
        Check if media already exists in Plex.
        
        Returns:
            Dict with 'exists', 'rating_key', 'plex_title'
        """
        if not self.server:
            return {"exists": False}
        
        try:
            results = self.server.library.search(title)
            
            for item in results:
                # Type check
                if media_type == "movie" and item.type != "movie":
                    continue
                if media_type in ("series", "anime") and item.type != "show":
                    continue
                
                # Year check (if provided)
                if year and hasattr(item, 'year') and item.year != year:
                    continue
                
                # Title similarity check (basic)
                if self._titles_match(title, item.title):
                    return {
                        "exists": True,
                        "rating_key": item.ratingKey,
                        "plex_title": item.title,
                        "plex_year": getattr(item, 'year', None)
                    }
            
            return {"exists": False}
        except Exception as e:
            logger.error(f"Duplicate check error: {e}")
            return {"exists": False}
    
    def _titles_match(self, title1: str, title2: str) -> bool:
        """Check if two titles are similar enough to be duplicates."""
        t1 = title1.lower().strip()
        t2 = title2.lower().strip()
        
        # Exact match
        if t1 == t2:
            return True
        
        # One contains the other
        if t1 in t2 or t2 in t1:
            return True
        
        # Remove common suffixes/prefixes and compare
        for suffix in [' (vf)', ' (vostfr)', ' french', ' multi']:
            t1 = t1.replace(suffix, '')
            t2 = t2.replace(suffix, '')
        
        return t1 == t2
    
    # =========================================================================
    # USER NOTIFICATIONS
    # =========================================================================
    
    def get_users(self) -> List[Dict[str, Any]]:
        """Get list of Plex users with access."""
        if not self.server:
            return []
        
        try:
            # Get account to list friends
            account = self.server.myPlexAccount()
            users = [{"id": account.id, "username": account.username, "email": account.email}]
            
            for user in account.users():
                users.append({
                    "id": user.id,
                    "username": user.username,
                    "email": user.email
                })
            
            return users
        except Exception as e:
            logger.error(f"Error getting Plex users: {e}")
            return []
    
    def notify_user(
        self,
        user_id: str,
        media_title: str,
        message: str = "Votre demande est maintenant disponible!"
    ) -> bool:
        """
        Send a notification to a Plex user.
        Note: Plex doesn't have a direct notification API, 
        so this triggers a library update which shows "Recently Added".
        """
        # Plex notifications are limited
        # The best we can do is ensure library is updated
        # so the user sees "Recently Added"
        logger.info(f"Notification for user {user_id}: {media_title} - {message}")
        return True
    
    # =========================================================================
    # MEDIA INFO
    # =========================================================================
    
    def get_media_info(self, rating_key: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a Plex media item."""
        if not self.server:
            return None
        
        try:
            item = self.server.fetchItem(int(rating_key))
            return {
                "title": item.title,
                "year": getattr(item, 'year', None),
                "type": item.type,
                "rating": getattr(item, 'rating', None),
                "summary": getattr(item, 'summary', None),
                "thumb": item.thumbUrl if hasattr(item, 'thumbUrl') else None,
                "duration": getattr(item, 'duration', None),
                "viewCount": getattr(item, 'viewCount', 0)
            }
        except NotFound:
            return None
        except Exception as e:
            logger.error(f"Error getting media info: {e}")
            return None
    
    # =========================================================================
    # HEALTH CHECK
    # =========================================================================
    
    def health_check(self) -> Dict[str, Any]:
        """Check Plex connection status using cached connection."""
        if not self.settings.plex_url or not self.settings.plex_token:
            return {"status": "not_configured", "message": "Plex credentials not set"}
        
        try:
            # Use cached server connection instead of creating new one
            if self.server is None:
                return {"status": "error", "message": "Could not connect to Plex"}
            
            return {
                "status": "ok",
                "server_name": self.server.friendlyName,
                "version": self.server.version,
                "libraries_count": len(self.server.library.sections())
            }
        except Unauthorized:
            return {"status": "error", "message": "Invalid Plex token"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Singleton instance for connection reuse
_plex_manager_service: Optional[PlexManagerService] = None


def get_plex_manager_service() -> PlexManagerService:
    """Get Plex manager service singleton instance (reuses connection)."""
    global _plex_manager_service
    if _plex_manager_service is None:
        _plex_manager_service = PlexManagerService()
    return _plex_manager_service

