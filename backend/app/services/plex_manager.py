"""
Plex integration service for library management and notifications.
"""
import logging
from typing import Optional, List, Dict, Any
from plexapi.server import PlexServer
from plexapi.exceptions import Unauthorized

from ..config import Settings

logger = logging.getLogger(__name__)


class PlexManagerService:
    """
    Plex server integration for:
    - Library scanning
    - Duplicate detection
    - User notifications
    - Media availability checks
    """

    def __init__(self, settings: Settings, settings_service):
        self.settings = settings
        self._settings_service = settings_service
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

        # Return cached server if available
        if self._server:
            try:
                # Test connection
                _ = self._server.library
                return self._server
            except Exception as e:
                logger.debug(f"Cached Plex connection failed: {e}")
                self._server = None

        # Create new connection
        try:
            self._server = PlexServer(
                self.settings.plex_url,
                self.settings.plex_token,
                timeout=10
            )
            self._connection_failed = False
            return self._server
        except Unauthorized:
            logger.error("Plex: Unauthorized - check your token")
            self._connection_failed = True
            return None
        except Exception as e:
            logger.error(f"Plex: Failed to connect - {e}")
            self._connection_failed = True
            return None

    def get_libraries(self) -> List[Dict[str, Any]]:
        """Obtenir la liste de toutes les librairies Plex."""
        if not self.server:
            return []

        try:
            libs = []
            for section in self.server.library.sections():
                libs.append({
                    "key": section.key,
                    "title": section.title,
                    "type": section.type,  # movie, show, artist, photo
                    "uuid": section.uuid
                })
            return libs
        except Exception as e:
            logger.error(f"Failed to get libraries: {e}")
            return []

    def scan_library(self, library_key: Optional[str] = None) -> bool:
        """
        Déclencher un scan de librairie Plex.

        Args:
            library_key: Si spécifié, scan uniquement cette librairie
        """
        if not self.server:
            logger.warning("Plex: Not connected, cannot scan library")
            return False

        try:
            if library_key:
                # Scan specific library
                section = self.server.library.sectionByID(library_key)
                section.update()
                logger.info(f"Plex: Scanning library '{section.title}'")
            else:
                # Scan all libraries
                for section in self.server.library.sections():
                    section.update()
                logger.info("Plex: Scanning all libraries")
            return True
        except Exception as e:
            logger.error(f"Plex: Failed to trigger scan - {e}")
            return False

    def get_media_by_id(self, media_type: str, tmdb_id: Optional[int] = None,
                        tvdb_id: Optional[int] = None, imdb_id: Optional[str] = None):
        """
        Trouver un média dans Plex par son ID externe (TMDB/TVDB/IMDB).

        Returns:
            PlexAPI media object or None
        """
        if not self.server:
            return None

        # Build GUID search patterns
        guid_patterns = []
        if tmdb_id:
            guid_patterns.append(f"tmdb://{tmdb_id}")
        if tvdb_id:
            guid_patterns.append(f"tvdb://{tvdb_id}")
        if imdb_id:
            guid_patterns.append(f"imdb://{imdb_id}")

        if not guid_patterns:
            logger.warning("No IDs provided for media search")
            return None

        try:
            # Search in appropriate library type
            for section in self.server.library.sections():
                if media_type == "movie" and section.type == "movie":
                    for guid_pattern in guid_patterns:
                        results = section.search(guid=guid_pattern)
                        if results:
                            return results[0]
                elif media_type == "series" and section.type == "show":
                    for guid_pattern in guid_patterns:
                        results = section.search(guid=guid_pattern)
                        if results:
                            return results[0]

            return None
        except Exception as e:
            logger.error(f"Plex: Failed to search media - {e}")
            return None

    def check_availability(self, media_type: str, tmdb_id: Optional[int] = None,
                          tvdb_id: Optional[int] = None, imdb_id: Optional[str] = None) -> bool:
        """
        Vérifier si un média existe dans Plex.
        """
        return self.get_media_by_id(media_type, tmdb_id, tvdb_id, imdb_id) is not None

    def get_duplicates(self, title: str, year: Optional[int] = None,
                      media_type: str = "movie") -> List[Dict[str, Any]]:
        """
        Chercher les doublons potentiels dans Plex.

        Returns:
            Liste des médias potentiellement en doublon avec leurs infos
        """
        if not self.server:
            return []

        duplicates = []

        try:
            for section in self.server.library.sections():
                # Skip wrong type
                if media_type == "movie" and section.type != "movie":
                    continue
                if media_type == "series" and section.type != "show":
                    continue

                # Search by title
                results = section.search(title=title)

                for item in results:
                    # Check year match if provided
                    if year:
                        item_year = getattr(item, 'year', None)
                        if item_year and abs(item_year - year) > 1:  # Allow 1 year difference
                            continue

                    # Extract info
                    duplicates.append({
                        "title": item.title,
                        "year": getattr(item, 'year', None),
                        "rating_key": item.ratingKey,
                        "library": section.title,
                        "guid": item.guid,
                        "summary": getattr(item, 'summary', ''),
                        "url": f"{self.settings.plex_url}/web/index.html#!/server/{self.server.machineIdentifier}/details?key=/library/metadata/{item.ratingKey}"
                    })

            return duplicates
        except Exception as e:
            logger.error(f"Plex: Failed to check duplicates - {e}")
            return []

    def notify_user_available(self, username: str, media_title: str, media_type: str):
        """
        Notifier un utilisateur Plex qu'un média est disponible.

        Note: Actuellement, cette fonctionnalité n'est pas implémentée via l'API Plex.
        On utilise Discord pour les notifications.
        """
        # Plex doesn't have a direct notification API
        # This would require Plex Pass + Home users setup
        logger.info(f"Notification: {username} - {media_title} ({media_type}) available")

    def get_watch_status(self, username: str, media_type: str,
                        tmdb_id: Optional[int] = None, tvdb_id: Optional[int] = None):
        """
        Obtenir le statut de visionnage d'un média pour un utilisateur.

        Returns:
            Dict with watched, progress, etc. or None
        """
        if not self.server:
            return None

        media = self.get_media_by_id(media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
        if not media:
            return None

        try:
            # Get user's watch history
            # Note: This requires Plex Pass for managed users
            user = self.server.myPlexAccount().user(username)
            history = user.history()

            # Find this media in history
            for item in history:
                if item.ratingKey == media.ratingKey:
                    return {
                        "watched": item.isWatched,
                        "progress": getattr(item, 'viewOffset', 0),
                        "last_viewed": getattr(item, 'lastViewedAt', None)
                    }

            return {"watched": False, "progress": 0}
        except Exception as e:
            logger.error(f"Plex: Failed to get watch status - {e}")
            return None

    def get_library_paths(self) -> Dict[str, List[str]]:
        """
        Obtenir les chemins de toutes les librairies Plex.

        Returns:
            Dict avec library_name: [paths]
        """
        if not self.server:
            return {}

        try:
            paths = {}
            for section in self.server.library.sections():
                section_paths = []
                for location in section.locations:
                    section_paths.append(location)
                paths[section.title] = section_paths
            return paths
        except Exception as e:
            logger.error(f"Plex: Failed to get library paths - {e}")
            return {}

    def find_media_file_path(self, media_type: str, tmdb_id: Optional[int] = None,
                            tvdb_id: Optional[int] = None) -> Optional[str]:
        """
        Trouver le chemin du fichier d'un média dans Plex.
        Utile pour vérifier où placer les nouveaux téléchargements.
        """
        media = self.get_media_by_id(media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
        if not media:
            return None

        try:
            # Get first media file
            if hasattr(media, 'media') and media.media:
                first_media = media.media[0]
                if hasattr(first_media, 'parts') and first_media.parts:
                    return first_media.parts[0].file
            return None
        except Exception as e:
            logger.error(f"Plex: Failed to get media file path - {e}")
            return None

    def get_media_quality_info(self, media_type: str, tmdb_id: Optional[int] = None,
                               tvdb_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Obtenir les infos de qualité d'un média (résolution, codec, etc.).
        """
        media = self.get_media_by_id(media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
        if not media:
            return {}

        try:
            info = {
                "title": media.title,
                "year": getattr(media, 'year', None),
                "files": []
            }

            # Extract quality info from all versions
            if hasattr(media, 'media'):
                for media_item in media.media:
                    file_info = {
                        "resolution": getattr(media_item, 'videoResolution', 'unknown'),
                        "codec": getattr(media_item, 'videoCodec', 'unknown'),
                        "bitrate": getattr(media_item, 'bitrate', 0),
                        "audio_codec": getattr(media_item, 'audioCodec', 'unknown'),
                        "container": getattr(media_item, 'container', 'unknown'),
                        "size_mb": getattr(media_item, 'file_size', 0) // 1024 // 1024 if hasattr(media_item, 'file_size') else 0
                    }

                    # Add file path if available
                    if hasattr(media_item, 'parts') and media_item.parts:
                        file_info["path"] = media_item.parts[0].file

                    info["files"].append(file_info)

            return info
        except Exception as e:
            logger.error(f"Plex: Failed to get quality info - {e}")
            return {}

    def refresh_metadata(self, media_type: str, tmdb_id: Optional[int] = None,
                        tvdb_id: Optional[int] = None):
        """
        Forcer un rafraîchissement des métadonnées d'un média.
        Utile après ajout manuel de fichiers.
        """
        media = self.get_media_by_id(media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
        if not media:
            logger.warning(f"Media not found for refresh: {media_type} tmdb={tmdb_id} tvdb={tvdb_id}")
            return False

        try:
            media.refresh()
            logger.info(f"Plex: Refreshed metadata for {media.title}")
            return True
        except Exception as e:
            logger.error(f"Plex: Failed to refresh metadata - {e}")
            return False

    def health_check(self) -> Dict[str, Any]:
        """
        Vérifier la connexion à Plex.

        Returns:
            Dict with status and info
        """
        if not self._is_configured():
            return {
                "status": "not_configured",
                "message": "Plex URL or token not configured (or using placeholder values)"
            }

        if not self.server:
            return {"status": "error", "message": "Cannot connect to Plex server"}

        try:
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


# Singleton instance (legacy - used by plex_cache_service and pipeline)
_plex_manager_service: Optional[PlexManagerService] = None


def get_plex_manager_service() -> PlexManagerService:
    """
    Get Plex manager service singleton instance.
    NOTE: This is legacy code for backward compatibility with services that haven't been refactored yet.
    New code should use dependency injection via dependencies.py
    """
    global _plex_manager_service
    if _plex_manager_service is None:
        from ..config import get_settings
        from .settings_service import SettingsService
        from ..models.database import SessionLocal

        settings = get_settings()
        db = SessionLocal()
        try:
            settings_service = SettingsService(db)
            _plex_manager_service = PlexManagerService(settings, settings_service)
        finally:
            db.close()
    return _plex_manager_service
