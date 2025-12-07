"""
qBittorrent download manager service.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import qbittorrentapi

from ..config import get_settings
from ..models.download import DownloadStatus

logger = logging.getLogger(__name__)


class DownloaderService:
    """
    qBittorrent integration for:
    - Adding/managing torrents
    - Progress monitoring
    - Auto-seeding management
    - Disk space monitoring
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[qbittorrentapi.Client] = None
        self._connection_failed = False  # Cache connection failures
    
    def _is_configured(self) -> bool:
        """Check if qBittorrent is properly configured (not placeholder values)."""
        url = self.settings.qbittorrent_url
        if not url:
            return False
        # Detect placeholder values
        placeholders = ['your-', 'example', 'localhost', '127.0.0.1', 'xxx', 'placeholder']
        url_lower = url.lower()
        for placeholder in placeholders:
            if placeholder in url_lower and placeholder not in ['localhost', '127.0.0.1']:
                # Only localhost/127.0.0.1 are valid, others are placeholders
                if 'your-' in url_lower or 'example' in url_lower or 'xxx' in url_lower or 'placeholder' in url_lower:
                    return False
        return True
    
    @property
    def client(self) -> Optional[qbittorrentapi.Client]:
        """Get qBittorrent client connection with timeout."""
        # Skip if already failed or not configured
        if self._connection_failed:
            logger.warning("qBittorrent connection previously failed, not retrying (restart container to retry)")
            return None
        
        if not self._is_configured():
            logger.warning(f"qBittorrent not configured. URL: {self.settings.qbittorrent_url}")
            return None
            
        if self._client is None and self.settings.qbittorrent_url:
            try:
                # Parse URL
                url = self.settings.qbittorrent_url
                host = url.replace("http://", "").replace("https://", "")
                # Remove trailing slash and path if present
                if "/" in host:
                    host = host.split("/")[0]
                if ":" in host:
                    host, port_str = host.split(":")
                    port = int(port_str)
                else:
                    port = 8080
                
                logger.info(f"Connecting to qBittorrent at {host}:{port}...")
                
                self._client = qbittorrentapi.Client(
                    host=host,
                    port=port,
                    username=self.settings.qbittorrent_username,
                    password=self.settings.qbittorrent_password,
                    VERIFY_WEBUI_CERTIFICATE=False,
                )
                self._client.auth_log_in()
                logger.info(f"Connected to qBittorrent: {self._client.app.version}")
            except Exception as e:
                logger.error(f"Failed to connect to qBittorrent at {self.settings.qbittorrent_url}: {e}")
                self._connection_failed = True  # Don't retry on subsequent calls
                return None
        return self._client
    
    # =========================================================================
    # TORRENT MANAGEMENT
    # =========================================================================
    
    def add_torrent(
        self,
        torrent_url: Optional[str] = None,
        magnet_link: Optional[str] = None,
        torrent_file: Optional[bytes] = None,
        category: str = "plex-kiosk",
        save_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Add a torrent to qBittorrent.
        
        Args:
            torrent_url: URL to .torrent file
            magnet_link: Magnet link
            torrent_file: Raw torrent file bytes
            category: qBittorrent category
            save_path: Custom save path
            
        Returns:
            Torrent hash if successful, None otherwise
        """
        if not self.client:
            logger.error("Cannot add torrent: qBittorrent client is not connected. Check QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD in .env")
            return None
        
        try:
            # Prepare parameters
            params = {
                "category": category,
                "savepath": save_path or self.settings.download_path,
                "paused": False
            }
            
            if magnet_link:
                params["urls"] = magnet_link
            elif torrent_url:
                params["urls"] = torrent_url
            elif torrent_file:
                params["torrent_files"] = torrent_file
            else:
                raise ValueError("Must provide torrent_url, magnet_link, or torrent_file")
            
            # Add torrent - log what we're adding
            if torrent_file:
                logger.info(f"Adding torrent from file bytes ({len(torrent_file)} bytes)")
            elif torrent_url:
                logger.info(f"Adding torrent URL: {torrent_url[:100]}...")
            elif magnet_link:
                logger.info(f"Adding magnet link: {magnet_link[:60]}...")
            
            result = self.client.torrents_add(**params)
            
            if result == "Ok.":
                # Get the hash of the added torrent
                # qBittorrent doesn't return the hash directly, so we need to find it
                import time
                import hashlib
                
                time.sleep(2)  # Wait for torrent to be added
                
                # Try multiple methods to get the hash
                torrent_hash = None
                
                # Method 1: Get by category
                try:
                    torrents = self.client.torrents_info(category=category, sort="added_on", reverse=True)
                    if torrents:
                        torrent_hash = torrents[0].hash
                        logger.info(f"Torrent added, hash (by category): {torrent_hash}")
                except Exception as e:
                    logger.warning(f"Could not get torrents by category: {e}")
                
                # Method 2: Get all recent torrents
                if not torrent_hash:
                    try:
                        torrents = self.client.torrents_info(sort="added_on", reverse=True, limit=5)
                        if torrents:
                            torrent_hash = torrents[0].hash
                            logger.info(f"Torrent added, hash (all recent): {torrent_hash}")
                    except Exception as e:
                        logger.warning(f"Could not get recent torrents: {e}")
                
                # Method 3: Generate a pseudo-hash from URL (last resort)
                if not torrent_hash and torrent_url:
                    torrent_hash = hashlib.md5(torrent_url.encode()).hexdigest()[:40]
                    logger.warning(f"Using generated hash from URL: {torrent_hash}")
                
                if torrent_hash:
                    return torrent_hash
                else:
                    logger.warning("Torrent added but could not retrieve or generate hash")
                    return None
            
            logger.warning(f"Torrent add result: {result}. URL: {torrent_url[:100] if torrent_url else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Error adding torrent: {e}")
            return None
    
    def get_torrent_info(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a torrent."""
        if not self.client:
            return None
        
        try:
            torrents = self.client.torrents_info(torrent_hashes=torrent_hash)
            if not torrents:
                return None
            
            t = torrents[0]
            return {
                "hash": t.hash,
                "name": t.name,
                "size": t.size,
                "progress": t.progress * 100,
                "status": self._map_status(t.state),
                "download_speed": t.dlspeed,
                "upload_speed": t.upspeed,
                "seeders": t.num_seeds,
                "leechers": t.num_leechs,
                "eta": t.eta,
                "save_path": t.save_path,
                "content_path": t.content_path,
                "added_on": datetime.fromtimestamp(t.added_on),
                "completion_on": datetime.fromtimestamp(t.completion_on) if t.completion_on > 0 else None,
                "ratio": t.ratio
            }
        except Exception as e:
            logger.error(f"Error getting torrent info: {e}")
            return None
    
    def get_all_torrents(self, category: str = "plex-kiosk") -> List[Dict[str, Any]]:
        """Get all torrents in a category."""
        if not self.client:
            return []
        
        try:
            torrents = self.client.torrents_info(category=category)
            return [
                {
                    "hash": t.hash,
                    "name": t.name,
                    "size": t.size,
                    "progress": t.progress * 100,
                    "status": self._map_status(t.state),
                    "download_speed": t.dlspeed,
                    "upload_speed": t.upspeed,
                    "added_on": datetime.fromtimestamp(t.added_on)
                }
                for t in torrents
            ]
        except Exception as e:
            logger.error(f"Error getting torrents: {e}")
            return []
    
    def pause_torrent(self, torrent_hash: str) -> bool:
        """Pause a torrent."""
        if not self.client:
            return False
        
        try:
            self.client.torrents_pause(torrent_hashes=torrent_hash)
            return True
        except Exception as e:
            logger.error(f"Error pausing torrent: {e}")
            return False
    
    def resume_torrent(self, torrent_hash: str) -> bool:
        """Resume a torrent."""
        if not self.client:
            return False
        
        try:
            self.client.torrents_resume(torrent_hashes=torrent_hash)
            return True
        except Exception as e:
            logger.error(f"Error resuming torrent: {e}")
            return False
    
    def delete_torrent(self, torrent_hash: str, delete_files: bool = True) -> bool:
        """Delete a torrent and optionally its files."""
        if not self.client:
            return False
        
        try:
            self.client.torrents_delete(torrent_hashes=torrent_hash, delete_files=delete_files)
            logger.info(f"Deleted torrent {torrent_hash}, files={'yes' if delete_files else 'no'}")
            return True
        except Exception as e:
            logger.error(f"Error deleting torrent: {e}")
            return False
    
    # =========================================================================
    # SEEDING MANAGEMENT
    # =========================================================================
    
    def get_torrents_to_cleanup(self) -> List[Dict[str, Any]]:
        """
        Get torrents that have been seeding for longer than the configured duration.
        """
        if not self.client:
            return []
        
        seed_duration = timedelta(hours=self.settings.seed_duration_hours)
        cutoff_time = datetime.now() - seed_duration
        
        try:
            torrents = self.client.torrents_info(filter="seeding", category="plex-kiosk")
            return [
                {
                    "hash": t.hash,
                    "name": t.name,
                    "completion_time": datetime.fromtimestamp(t.completion_on),
                    "ratio": t.ratio
                }
                for t in torrents
                if t.completion_on > 0 and datetime.fromtimestamp(t.completion_on) < cutoff_time
            ]
        except Exception as e:
            logger.error(f"Error checking seed cleanup: {e}")
            return []
    
    def cleanup_finished_seeds(self) -> int:
        """Remove torrents that have seeded for the required duration."""
        torrents = self.get_torrents_to_cleanup()
        count = 0
        
        for t in torrents:
            if self.delete_torrent(t["hash"], delete_files=True):
                count += 1
                logger.info(f"Cleaned up: {t['name']} (ratio: {t['ratio']:.2f})")
        
        return count
    
    # =========================================================================
    # DISK MANAGEMENT
    # =========================================================================
    
    def get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage information."""
        if not self.client:
            return {}
        
        try:
            # Get transfer info for current download size
            transfer = self.client.transfer_info()
            
            # Get all torrents to calculate total size
            torrents = self.client.torrents_info(category="plex-kiosk")
            total_size = sum(t.size for t in torrents)
            
            limit_gb = self.settings.max_download_size_gb
            
            return {
                "total_size_bytes": total_size,
                "total_size_gb": total_size / (1024 ** 3),
                "limit_gb": limit_gb,
                "usage_percent": (total_size / (1024 ** 3) / limit_gb) * 100 if limit_gb > 0 else 0,
                "download_speed": transfer.get("dl_info_speed", 0),
                "upload_speed": transfer.get("up_info_speed", 0)
            }
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return {}
    
    def has_space_for(self, size_bytes: int) -> bool:
        """Check if there's enough space for a new download."""
        usage = self.get_disk_usage()
        if not usage:
            return True  # Assume yes if we can't check
        
        current_gb = usage.get("total_size_gb", 0)
        new_gb = size_bytes / (1024 ** 3)
        limit_gb = self.settings.max_download_size_gb
        
        return (current_gb + new_gb) <= limit_gb
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _map_status(self, qbt_state: str) -> DownloadStatus:
        """Map qBittorrent state to our status."""
        state_map = {
            "allocating": DownloadStatus.QUEUED,
            "downloading": DownloadStatus.DOWNLOADING,
            "metaDL": DownloadStatus.DOWNLOADING,
            "pausedDL": DownloadStatus.QUEUED,
            "queuedDL": DownloadStatus.QUEUED,
            "stalledDL": DownloadStatus.DOWNLOADING,
            "checkingDL": DownloadStatus.DOWNLOADING,
            "forcedDL": DownloadStatus.DOWNLOADING,
            "uploading": DownloadStatus.SEEDING,
            "stalledUP": DownloadStatus.SEEDING,
            "pausedUP": DownloadStatus.SEEDING,
            "queuedUP": DownloadStatus.SEEDING,
            "checkingUP": DownloadStatus.SEEDING,
            "forcedUP": DownloadStatus.SEEDING,
            "error": DownloadStatus.ERROR,
            "missingFiles": DownloadStatus.ERROR,
            "moving": DownloadStatus.PROCESSING,
        }
        return state_map.get(qbt_state, DownloadStatus.QUEUED)
    
    def health_check(self) -> Dict[str, Any]:
        """Check qBittorrent connection."""
        if not self.settings.qbittorrent_url:
            return {"status": "not_configured"}
        
        try:
            if self.client:
                return {
                    "status": "ok",
                    "version": self.client.app.version,
                    "api_version": self.client.app.web_api_version
                }
            return {"status": "error", "message": "Could not connect"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Singleton instance for connection reuse
_downloader_service: Optional[DownloaderService] = None


def get_downloader_service() -> DownloaderService:
    """Get downloader service singleton instance (reuses connection)."""
    global _downloader_service
    if _downloader_service is None:
        _downloader_service = DownloaderService()
    return _downloader_service

