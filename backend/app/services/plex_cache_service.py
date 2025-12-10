"""
Plex Library Cache Service.
Manages local cache of Plex library for fast availability checks.
"""
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models.database import SessionLocal
from ..models.plex_library import PlexLibraryItem, PlexSyncStatus
from ..config import get_settings
from .plex_manager import get_plex_manager_service

logger = logging.getLogger(__name__)


@dataclass
class AvailabilityInfo:
    """Basic availability info for search results."""
    available: bool = False
    quality: Optional[str] = None  # e.g., "1080p", "4K"
    audio_languages: List[str] = None
    seasons_available: List[int] = None
    
    def __post_init__(self):
        if self.audio_languages is None:
            self.audio_languages = []
        if self.seasons_available is None:
            self.seasons_available = []


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    items_synced: int
    items_skipped: int
    items_without_guid: int
    duration_seconds: float
    message: str


class PlexCacheService:
    """
    Manages the local cache of Plex library for fast availability checks.
    
    Features:
    - Syncs Plex library to local SQLite cache
    - Extracts TMDB/TVDB/IMDB IDs from Plex GUIDs
    - Batch availability checks for search results
    - Detailed availability info for modals
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._plex = get_plex_manager_service()
    
    # =========================================================================
    # SYNC OPERATIONS
    # =========================================================================
    
    def sync_library(self, full_sync: bool = False) -> SyncResult:
        """
        Sync Plex library to local cache.
        
        Args:
            full_sync: If True, clear cache and resync everything.
                      If False, only sync new items since last sync.
        
        Returns:
            SyncResult with stats about the sync operation.
        """
        start_time = datetime.utcnow()
        
        if not self._plex.server:
            return SyncResult(
                success=False,
                items_synced=0,
                items_skipped=0,
                items_without_guid=0,
                duration_seconds=0,
                message="Plex server not connected"
            )
        
        with SessionLocal() as db:
            # Mark sync as in progress
            sync_status = self._get_or_create_sync_status(db)
            sync_status.sync_in_progress = True
            db.commit()
            
            try:
                if full_sync:
                    # Clear existing cache
                    db.execute(delete(PlexLibraryItem))
                    db.commit()
                    logger.info("Full sync: cleared existing cache")
                
                # Get last sync time for incremental sync
                last_sync = None if full_sync else sync_status.last_sync_at
                
                items_synced = 0
                items_skipped = 0
                items_without_guid = 0
                
                # Sync each library section
                for library in self._plex.server.library.sections():
                    if library.type not in ('movie', 'show'):
                        continue
                    
                    logger.info(f"Syncing library: {library.title} ({library.type})")
                    
                    # Get items to sync
                    if last_sync:
                        # Incremental: only items added after last sync
                        items = library.search(addedAt__gt=last_sync)
                    else:
                        # Full: all items
                        items = library.all()
                    
                    for item in items:
                        try:
                            result = self._sync_item(db, item, library.title)
                            if result == "synced":
                                items_synced += 1
                            elif result == "no_guid":
                                items_without_guid += 1
                                items_synced += 1  # Still synced, just flagged
                            else:
                                items_skipped += 1
                        except Exception as e:
                            logger.error(f"Error syncing item {item.title}: {e}")
                            items_skipped += 1
                        
                        # Small delay to avoid overwhelming Plex
                        if items_synced % 50 == 0:
                            db.commit()
                
                db.commit()
                
                # Update sync status
                duration = (datetime.utcnow() - start_time).total_seconds()
                sync_status.last_sync_at = datetime.utcnow()
                sync_status.last_sync_count = items_synced
                sync_status.total_items = db.query(PlexLibraryItem).count()
                sync_status.items_without_guid = items_without_guid
                sync_status.last_sync_message = f"Synced {items_synced} items in {duration:.1f}s"
                sync_status.sync_in_progress = False
                db.commit()
                
                logger.info(f"Sync complete: {items_synced} items synced, {items_skipped} skipped, {items_without_guid} without GUID")
                
                return SyncResult(
                    success=True,
                    items_synced=items_synced,
                    items_skipped=items_skipped,
                    items_without_guid=items_without_guid,
                    duration_seconds=duration,
                    message=f"Synced {items_synced} items from Plex"
                )
                
            except Exception as e:
                sync_status.sync_in_progress = False
                sync_status.last_sync_message = f"Error: {str(e)}"
                db.commit()
                logger.error(f"Sync failed: {e}")
                return SyncResult(
                    success=False,
                    items_synced=0,
                    items_skipped=0,
                    items_without_guid=0,
                    duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
                    message=str(e)
                )
    
    def _sync_item(self, db: Session, plex_item, library_title: str) -> str:
        """
        Sync a single Plex item to cache.
        
        Returns: "synced", "no_guid", or "skipped"
        """
        rating_key = str(plex_item.ratingKey)
        
        # Check if already exists
        existing = db.query(PlexLibraryItem).filter(
            PlexLibraryItem.plex_rating_key == rating_key
        ).first()
        
        if existing:
            # Update existing item
            item = existing
        else:
            item = PlexLibraryItem(plex_rating_key=rating_key)
            db.add(item)
        
        # Basic info
        item.plex_library_title = library_title
        item.title = plex_item.title
        item.original_title = getattr(plex_item, 'originalTitle', None)
        item.year = getattr(plex_item, 'year', None)
        item.media_type = plex_item.type  # movie or show
        item.plex_added_at = getattr(plex_item, 'addedAt', None)
        item.synced_at = datetime.utcnow()
        
        # Extract GUIDs
        guids = self._extract_guids(plex_item)
        item.tmdb_id = guids.get('tmdb')
        item.tvdb_id = guids.get('tvdb')
        item.imdb_id = guids.get('imdb')
        
        # Extract quality info
        quality_info = self._extract_quality_info(plex_item)
        item.quality_info = quality_info.get('quality_info')
        item.audio_languages = quality_info.get('audio_languages', [])
        item.subtitle_languages = quality_info.get('subtitle_languages', [])
        item.file_size_gb = quality_info.get('file_size_gb')
        
        # For series: get seasons info
        if plex_item.type == 'show':
            seasons_info = self._extract_seasons_info(plex_item)
            item.seasons_available = seasons_info.get('seasons', [])
            item.total_episodes = seasons_info.get('total_episodes', 0)
        
        # Poster URL
        if hasattr(plex_item, 'thumbUrl'):
            item.poster_url = plex_item.thumbUrl
        
        return "synced" if item.has_external_id else "no_guid"
    
    def _extract_guids(self, plex_item) -> Dict[str, Optional[str]]:
        """
        Extract TMDB, TVDB, and IMDB IDs from Plex GUIDs.
        
        Plex stores GUIDs in format like:
        - plex://movie/5d776823...
        - tmdb://12345
        - tvdb://67890
        - imdb://tt1234567
        """
        result = {'tmdb': None, 'tvdb': None, 'imdb': None}
        
        try:
            # Plex API: guids is a list of Guid objects
            guids = getattr(plex_item, 'guids', [])
            
            for guid in guids:
                guid_str = str(guid.id) if hasattr(guid, 'id') else str(guid)
                
                # Parse TMDB ID
                if 'tmdb://' in guid_str:
                    match = re.search(r'tmdb://(\d+)', guid_str)
                    if match:
                        result['tmdb'] = match.group(1)
                
                # Parse TVDB ID
                elif 'tvdb://' in guid_str:
                    match = re.search(r'tvdb://(\d+)', guid_str)
                    if match:
                        result['tvdb'] = match.group(1)
                
                # Parse IMDB ID
                elif 'imdb://' in guid_str:
                    match = re.search(r'imdb://(tt\d+)', guid_str)
                    if match:
                        result['imdb'] = match.group(1)
        
        except Exception as e:
            logger.debug(f"Error extracting GUIDs from {plex_item.title}: {e}")
        
        return result
    
    def _extract_quality_info(self, plex_item) -> Dict[str, Any]:
        """Extract quality information from Plex media item."""
        result = {
            'quality_info': {},
            'audio_languages': [],
            'subtitle_languages': [],
            'file_size_gb': None
        }
        
        try:
            media_list = getattr(plex_item, 'media', [])
            if not media_list:
                return result
            
            # Use first media file (best quality usually)
            media = media_list[0]
            
            # Resolution
            resolution = None
            height = getattr(media, 'height', 0)
            if height >= 2160:
                resolution = "4K"
            elif height >= 1080:
                resolution = "1080p"
            elif height >= 720:
                resolution = "720p"
            elif height >= 480:
                resolution = "480p"
            else:
                resolution = f"{height}p" if height else None
            
            result['quality_info'] = {
                'resolution': resolution,
                'video_codec': getattr(media, 'videoCodec', None),
                'video_profile': getattr(media, 'videoProfile', None),
                'bitrate': getattr(media, 'bitrate', None),
                'container': getattr(media, 'container', None),
            }
            
            # File size
            total_size = 0
            audio_langs = set()
            subtitle_langs = set()
            
            for part in getattr(media, 'parts', []):
                # Size
                if hasattr(part, 'size'):
                    total_size += part.size
                
                # Audio streams
                for stream in getattr(part, 'audioStreams', []):
                    lang = getattr(stream, 'languageCode', None) or getattr(stream, 'language', None)
                    if lang:
                        audio_langs.add(lang[:3].lower())
                
                # Subtitle streams
                for stream in getattr(part, 'subtitleStreams', []):
                    lang = getattr(stream, 'languageCode', None) or getattr(stream, 'language', None)
                    if lang:
                        subtitle_langs.add(lang[:3].lower())
            
            if total_size > 0:
                result['file_size_gb'] = round(total_size / (1024 ** 3), 2)
            
            result['audio_languages'] = list(audio_langs)
            result['subtitle_languages'] = list(subtitle_langs)
            
        except Exception as e:
            logger.debug(f"Error extracting quality info from {plex_item.title}: {e}")
        
        return result
    
    def _extract_seasons_info(self, show_item) -> Dict[str, Any]:
        """Extract available seasons and episode count from a TV show."""
        result = {'seasons': [], 'total_episodes': 0}
        
        try:
            seasons = show_item.seasons()
            for season in seasons:
                # Skip specials (season 0)
                if season.seasonNumber and season.seasonNumber > 0:
                    result['seasons'].append(season.seasonNumber)
                    result['total_episodes'] += len(season.episodes())
            
            result['seasons'].sort()
        except Exception as e:
            logger.debug(f"Error extracting seasons from {show_item.title}: {e}")
        
        return result
    
    def _get_or_create_sync_status(self, db: Session) -> PlexSyncStatus:
        """Get or create the sync status record."""
        status = db.query(PlexSyncStatus).first()
        if not status:
            status = PlexSyncStatus(id=1)
            db.add(status)
            db.commit()
        return status
    
    # =========================================================================
    # AVAILABILITY CHECKS
    # =========================================================================
    
    def check_availability_batch(
        self,
        items: List[Dict[str, Any]]
    ) -> Dict[str, AvailabilityInfo]:
        """
        Check availability for multiple items at once.
        
        Args:
            items: List of dicts with 'id' (TMDB ID) and 'media_type'
        
        Returns:
            Dict mapping TMDB ID to AvailabilityInfo
        """
        if not items:
            return {}
        
        result = {}
        
        with SessionLocal() as db:
            # Collect all TMDB IDs to check
            tmdb_ids = [str(item.get('id')) for item in items if item.get('id')]
            
            if not tmdb_ids:
                return {}
            
            # Single query for all items
            cached_items = db.query(PlexLibraryItem).filter(
                PlexLibraryItem.tmdb_id.in_(tmdb_ids)
            ).all()
            
            # Build result dict
            for cached in cached_items:
                if cached.tmdb_id:
                    # Determine quality string
                    quality = None
                    if cached.quality_info:
                        quality = cached.quality_info.get('resolution')
                    
                    result[cached.tmdb_id] = AvailabilityInfo(
                        available=True,
                        quality=quality,
                        audio_languages=cached.audio_languages or [],
                        seasons_available=cached.seasons_available or []
                    )
        
        return result
    
    def get_detailed_availability(
        self,
        tmdb_id: str,
        media_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed availability info for modal display.
        
        Returns full quality info, languages, seasons, etc.
        """
        with SessionLocal() as db:
            item = db.query(PlexLibraryItem).filter(
                PlexLibraryItem.tmdb_id == str(tmdb_id)
            ).first()
            
            if not item:
                return None
            
            return item.to_availability_dict()
    
    def check_seasons_availability(
        self,
        tmdb_id: str
    ) -> Dict[str, Any]:
        """
        Check which seasons are available for a series.
        
        Returns:
            Dict with 'available_seasons', 'total_episodes', etc.
        """
        with SessionLocal() as db:
            item = db.query(PlexLibraryItem).filter(
                PlexLibraryItem.tmdb_id == str(tmdb_id),
                PlexLibraryItem.media_type == 'show'
            ).first()
            
            if not item:
                return {
                    'available': False,
                    'seasons': [],
                    'total_episodes': 0
                }
            
            return {
                'available': True,
                'seasons': item.seasons_available or [],
                'total_episodes': item.total_episodes or 0,
                'quality_info': item.quality_info,
                'audio_languages': item.audio_languages or []
            }
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status."""
        with SessionLocal() as db:
            status = self._get_or_create_sync_status(db)
            return {
                'last_sync_at': status.last_sync_at.isoformat() if status.last_sync_at else None,
                'last_sync_count': status.last_sync_count,
                'total_items': status.total_items,
                'items_without_guid': status.items_without_guid,
                'last_sync_message': status.last_sync_message,
                'sync_in_progress': status.sync_in_progress
            }


# Singleton instance
_plex_cache_service: Optional[PlexCacheService] = None


def get_plex_cache_service() -> PlexCacheService:
    """Get Plex cache service singleton instance."""
    global _plex_cache_service
    if _plex_cache_service is None:
        _plex_cache_service = PlexCacheService()
    return _plex_cache_service
