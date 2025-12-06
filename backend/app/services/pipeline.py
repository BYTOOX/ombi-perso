"""
Request pipeline service - Orchestrates the full media request workflow.

Flow: PENDING → SEARCHING → DOWNLOADING → PROCESSING → COMPLETED
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.database import async_session_factory
from ..models.request import MediaRequest, RequestStatus, MediaType
from ..models.download import Download, DownloadStatus
from ..schemas.media import MediaSearchResult, TorrentResult
from .torrent_scraper import get_torrent_scraper_service
from .ai_agent import get_ai_agent_service
from .downloader import get_downloader_service
from .file_renamer import get_file_renamer_service
from .plex_manager import get_plex_manager_service
from .notifications import get_notification_service

logger = logging.getLogger(__name__)
settings = get_settings()


class RequestPipelineService:
    """
    Orchestrates the full media request workflow:
    1. Search torrents on YGGtorrent
    2. Score and select best torrent using AI
    3. Add to qBittorrent
    4. Monitor download progress
    5. Rename and move to library
    6. Scan Plex library
    7. Notify user
    """
    
    def __init__(self):
        self.scraper = get_torrent_scraper_service()
        self.ai = get_ai_agent_service()
        self.downloader = get_downloader_service()
        self.renamer = get_file_renamer_service()
        self.plex = get_plex_manager_service()
        self.notifier = get_notification_service()
    
    async def process_request(self, request_id: int) -> bool:
        """
        Process a media request through the full pipeline.
        
        Returns True if successful, False otherwise.
        """
        async with async_session_factory() as db:
            # Get request
            result = await db.execute(
                select(MediaRequest).where(MediaRequest.id == request_id)
            )
            request = result.scalar_one_or_none()
            
            if not request:
                logger.error(f"Request {request_id} not found")
                return False
            
            try:
                # Start processing
                logger.info("=" * 60)
                logger.info(f"PIPELINE START - Request #{request_id}")
                logger.info(f"Title: {request.title}")
                logger.info(f"Original Title: {request.original_title}")
                logger.info(f"Year: {request.year}")
                logger.info(f"Media Type: {request.media_type.value}")
                logger.info(f"Quality Preference: {request.quality_preference}")
                logger.info(f"External ID: {request.external_id} (source: {request.source})")
                logger.info("=" * 60)
                
                # Step 1: Search torrents
                await self._update_status(db, request, RequestStatus.SEARCHING, "Recherche de torrents...")
                torrents = await self._search_torrents(request)
                
                if not torrents:
                    logger.warning(f"[Request #{request_id}] No torrents found - search returned empty results")
                    await self._update_status(db, request, RequestStatus.ERROR, "Aucun torrent trouvé")
                    return False
                
                logger.info(f"[Request #{request_id}] Found {len(torrents)} torrents")
                
                # Log torrent details
                for i, t in enumerate(torrents[:10], 1):  # Log first 10
                    size_gb = round(t.size_bytes / (1024**3), 2) if t.size_bytes else 0
                    logger.info(f"  [{i}] {t.name[:80]}...")
                    logger.info(f"      Quality: {t.quality or 'unknown'} | Size: {size_gb}GB | Seeders: {t.seeders} | French: {t.has_french_audio}")
                
                if len(torrents) > 10:
                    logger.info(f"  ... and {len(torrents) - 10} more torrents")
                
                # Step 2: AI scoring and selection
                await self._update_status(db, request, RequestStatus.SEARCHING, f"Analyse de {len(torrents)} torrents...")
                logger.info(f"[Request #{request_id}] Starting AI torrent selection...")
                best_torrent = await self._select_best_torrent(request, torrents)
                
                if not best_torrent:
                    logger.warning(f"[Request #{request_id}] AI could not select a torrent")
                    await self._update_status(db, request, RequestStatus.ERROR, "Impossible de sélectionner un torrent")
                    return False
                
                logger.info(f"[Request #{request_id}] AI Selected: {best_torrent.name}")
                logger.info(f"[Request #{request_id}] - Quality: {best_torrent.quality}")
                logger.info(f"[Request #{request_id}] - Size: {round(best_torrent.size_bytes / (1024**3), 2) if best_torrent.size_bytes else 0}GB")
                logger.info(f"[Request #{request_id}] - Seeders: {best_torrent.seeders}")
                logger.info(f"[Request #{request_id}] - AI Score: {getattr(best_torrent, 'ai_score', 'N/A')}")
                
                # Step 3: Add to qBittorrent
                await self._update_status(db, request, RequestStatus.DOWNLOADING, f"Téléchargement: {best_torrent.name}")
                logger.info(f"[Request #{request_id}] Starting download...")
                download = await self._start_download(db, request, best_torrent)
                
                if not download:
                    logger.error(f"[Request #{request_id}] Failed to add torrent to qBittorrent")
                    await self._update_status(db, request, RequestStatus.ERROR, "Échec de l'ajout du torrent")
                    return False
                
                logger.info(f"[Request #{request_id}] Download started successfully")
                
                # Store AI analysis
                request.ai_analysis = {
                    "selected_torrent": best_torrent.name,
                    "ai_score": getattr(best_torrent, 'ai_score', 0),
                    "quality": best_torrent.quality,
                    "size_gb": round(best_torrent.size_bytes / (1024**3), 2) if best_torrent.size_bytes else 0
                }
                await db.commit()
                
                # Step 4: Monitor download (in background)
                await self._monitor_download(db, request, download)
                
                return True
                
            except Exception as e:
                logger.exception(f"[Request #{request_id}] Pipeline error: {e}")
                await self._update_status(db, request, RequestStatus.ERROR, f"Erreur: {str(e)}")
                return False
    
    async def _search_torrents(self, request: MediaRequest) -> list[TorrentResult]:
        """Search for torrents matching the request."""
        # Build search query
        search_query = request.title
        if request.year:
            search_query += f" {request.year}"
        
        # Map media type to YGG category
        media_type_map = {
            MediaType.MOVIE: "movie",
            MediaType.ANIMATED_MOVIE: "animated_movie",
            MediaType.SERIES: "series",
            MediaType.ANIMATED_SERIES_US: "animated_series_us",
            MediaType.ANIME: "anime"
        }
        
        ygg_type = media_type_map.get(request.media_type, None)
        
        logger.info(f"[Search] Query: '{search_query}'")
        logger.info(f"[Search] Media Type: {request.media_type.value} -> YGG Category: {ygg_type}")
        
        try:
            torrents = await self.scraper.search(
                query=search_query,
                media_type=ygg_type
            )
            logger.info(f"[Search] Scraper returned {len(torrents)} results")
            return torrents
        except Exception as e:
            logger.error(f"[Search] Error: {e}")
            return []
    
    async def _select_best_torrent(
        self,
        request: MediaRequest,
        torrents: list[TorrentResult]
    ) -> Optional[TorrentResult]:
        """Use AI to select the best torrent."""
        if not torrents:
            return None
        
        # Create media search result for AI
        media = MediaSearchResult(
            id=request.external_id,
            source=request.source,
            media_type=request.media_type.value,
            title=request.title,
            original_title=request.original_title,
            year=request.year,
            poster_url=request.poster_url,
            overview=request.overview
        )
        
        try:
            best = await self.ai.select_best_torrent(
                media=media,
                torrents=torrents,
                quality_preference=request.quality_preference
            )
            return best
        except Exception as e:
            logger.warning(f"AI selection failed, using first result: {e}")
            # Fallback: use first torrent sorted by seeders
            return sorted(torrents, key=lambda t: t.seeders or 0, reverse=True)[0]
    
    async def _start_download(
        self,
        db: AsyncSession,
        request: MediaRequest,
        torrent: TorrentResult
    ) -> Optional[Download]:
        """Add torrent to qBittorrent and create download record."""
        try:
            # Get download URL
            torrent_url = self.scraper.get_torrent_url(torrent.id)
            
            # Add to qBittorrent
            result = self.downloader.add_torrent(torrent_url=torrent_url)
            
            if not result.get("success"):
                logger.error(f"Failed to add torrent: {result.get('error')}")
                return None
            
            torrent_hash = result.get("hash")
            
            # Create download record
            download = Download(
                request_id=request.id,
                torrent_hash=torrent_hash,
                torrent_name=torrent.name,
                torrent_url=torrent_url,
                size_bytes=torrent.size or 0,
                status=DownloadStatus.DOWNLOADING
            )
            
            db.add(download)
            await db.commit()
            await db.refresh(download)
            
            logger.info(f"Started download: {torrent.name} (hash: {torrent_hash})")
            
            # Send notification
            await self.notifier.notify_download_started(
                title=request.title,
                torrent_name=torrent.name
            )
            
            return download
            
        except Exception as e:
            logger.exception(f"Failed to start download: {e}")
            return None
    
    async def _monitor_download(
        self,
        db: AsyncSession,
        request: MediaRequest,
        download: Download
    ):
        """Monitor download progress and complete processing when done."""
        max_wait_hours = 24
        check_interval = 30  # seconds
        max_checks = (max_wait_hours * 3600) // check_interval
        
        for check in range(max_checks):
            await asyncio.sleep(check_interval)
            
            try:
                # Get torrent info from qBittorrent
                info = self.downloader.get_torrent_info(download.torrent_hash)
                
                if not info:
                    logger.warning(f"Torrent {download.torrent_hash} not found in qBittorrent")
                    continue
                
                progress = info.get("progress", 0)
                status = info.get("status")
                
                # Update download record
                download.progress = int(progress * 100)
                download.download_path = info.get("save_path")
                
                if status == DownloadStatus.COMPLETED or progress >= 1.0:
                    logger.info(f"Download complete: {download.torrent_name}")
                    download.status = DownloadStatus.SEEDING
                    download.completed_at = datetime.utcnow()
                    await db.commit()
                    
                    # Process completed download
                    await self._process_completed_download(db, request, download, info)
                    return
                
                elif status == DownloadStatus.ERROR:
                    logger.error(f"Download failed: {download.torrent_name}")
                    download.status = DownloadStatus.ERROR
                    await db.commit()
                    await self._update_status(db, request, RequestStatus.ERROR, "Téléchargement échoué")
                    return
                
                await db.commit()
                
            except Exception as e:
                logger.warning(f"Error checking download status: {e}")
                continue
        
        # Timeout
        logger.warning(f"Download timeout for: {download.torrent_name}")
        await self._update_status(db, request, RequestStatus.ERROR, "Téléchargement timeout")
    
    async def _process_completed_download(
        self,
        db: AsyncSession,
        request: MediaRequest,
        download: Download,
        torrent_info: Dict[str, Any]
    ):
        """Process a completed download: rename, move, scan."""
        try:
            await self._update_status(db, request, RequestStatus.PROCESSING, "Renommage et déplacement...")
            
            download_path = torrent_info.get("content_path") or torrent_info.get("save_path")
            
            if not download_path:
                raise ValueError("Download path not found")
            
            # Rename and move to library
            result = self.renamer.process_download(
                download_path=download_path,
                media_type=request.media_type,
                media_title=request.title,
                year=request.year
            )
            
            if not result.get("success"):
                raise ValueError(result.get("error", "Rename failed"))
            
            final_path = result.get("final_path")
            download.final_path = final_path
            download.status = DownloadStatus.COMPLETED
            await db.commit()
            
            logger.info(f"Moved to library: {final_path}")
            
            # Scan Plex library
            await self._update_status(db, request, RequestStatus.PROCESSING, "Scan Plex...")
            self.plex.scan_library()
            
            # Mark request as completed
            request.status = RequestStatus.COMPLETED
            request.status_message = "Disponible sur Plex"
            request.completed_at = datetime.utcnow()
            await db.commit()
            
            logger.info(f"Request completed: {request.title}")
            
            # Send completion notification
            await self.notifier.notify_request_completed(
                title=request.title,
                media_type=request.media_type.value,
                username=None  # TODO: get username from request.user
            )
            
        except Exception as e:
            logger.exception(f"Failed to process completed download: {e}")
            await self._update_status(db, request, RequestStatus.ERROR, f"Erreur de traitement: {str(e)}")
    
    async def _update_status(
        self,
        db: AsyncSession,
        request: MediaRequest,
        status: RequestStatus,
        message: str
    ):
        """Update request status and message."""
        request.status = status
        request.status_message = message
        await db.commit()
        logger.info(f"Request {request.id} status: {status.value} - {message}")


# Singleton instance
_pipeline_service: Optional[RequestPipelineService] = None


def get_pipeline_service() -> RequestPipelineService:
    """Get pipeline service singleton."""
    global _pipeline_service
    if _pipeline_service is None:
        _pipeline_service = RequestPipelineService()
    return _pipeline_service


async def process_request_async(request_id: int):
    """Process a request asynchronously (for background task)."""
    pipeline = get_pipeline_service()
    await pipeline.process_request(request_id)
