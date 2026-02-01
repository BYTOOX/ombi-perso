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
from .ai_provider import get_ai_service
from .downloader import get_downloader_service
from .file_renamer import get_file_renamer_service
from .plex_manager import get_plex_manager_service
from .notifications import get_notification_service
from .workflow_service import WorkflowService
from ..models.workflow import WorkflowStepKey, ActionType

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
        self.ai = get_ai_service()
        self.downloader = get_downloader_service()
        self.renamer = get_file_renamer_service()
        self.plex = get_plex_manager_service()
        self.notifier = get_notification_service()
    
    async def process_request(
        self,
        request_id: int,
        override_query: Optional[str] = None,
        restart_from_step: Optional[str] = None
    ) -> bool:
        """
        Process a media request through the full pipeline.

        Args:
            request_id: ID of the request to process
            override_query: Optional search query to use instead of title
            restart_from_step: Optional step key to restart from (for retries)

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
                torrents = await self._search_torrents(db, request, override_query)
                
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
    
    async def _search_torrents(
        self,
        db: AsyncSession,
        request: MediaRequest,
        override_query: Optional[str] = None
    ) -> list[TorrentResult]:
        """Search for torrents matching the request with workflow tracking."""
        workflow = WorkflowService(db)

        # Start workflow step
        await workflow.start_step(request.id, WorkflowStepKey.TORRENT_SEARCH)

        # Build search query
        search_query = override_query or request.title
        if not override_query and request.year:
            search_query += f" {request.year}"

        # Map media type to YGG category
        media_type_map = {
            MediaType.MOVIE: "movie",
            MediaType.ANIMATED_MOVIE: "animated_movie",
            MediaType.SERIES: "series",
            MediaType.ANIMATED_SERIES: "animated_series",
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

            if not torrents:
                # Failed - no results, create action for admin
                await workflow.fail_step(
                    request_id=request.id,
                    step_key=WorkflowStepKey.TORRENT_SEARCH,
                    error_code="NO_RESULTS",
                    error_message=f"Aucun torrent trouvé pour: {search_query}",
                    artifacts={
                        "query": search_query,
                        "media_type": ygg_type,
                        "results_count": 0
                    },
                    create_action=ActionType.FIX_SEARCH_QUERY,
                    action_payload={
                        "original_query": search_query,
                        "title": request.title,
                        "original_title": request.original_title,
                        "year": request.year,
                        "media_type": ygg_type
                    },
                    action_priority=70
                )
                return []

            # Success - save artifacts with candidate list
            await workflow.complete_step(
                request_id=request.id,
                step_key=WorkflowStepKey.TORRENT_SEARCH,
                artifacts={
                    "query": search_query,
                    "media_type": ygg_type,
                    "results_count": len(torrents),
                    "candidates": [
                        {
                            "name": t.name,
                            "size_bytes": t.size_bytes,
                            "seeders": t.seeders,
                            "quality": t.quality
                        }
                        for t in torrents[:20]  # Store top 20 candidates
                    ]
                }
            )
            return torrents

        except Exception as e:
            logger.error(f"[Search] Error: {e}")
            await workflow.fail_step(
                request_id=request.id,
                step_key=WorkflowStepKey.TORRENT_SEARCH,
                error_code="SEARCH_ERROR",
                error_message=str(e),
                artifacts={"query": search_query, "media_type": ygg_type}
            )
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
            # Download the torrent file (qBittorrent can't download from YGG URLs without cookies)
            logger.info(f"Downloading torrent file for: {torrent.id}")
            torrent_file_bytes = await self.scraper.download_torrent_file(torrent.id)
            
            if not torrent_file_bytes:
                # Fallback: try URL method (might work with passkey)
                logger.warning("Could not download torrent file, trying URL method...")
                torrent_url = await self.scraper.get_torrent_url(torrent.id)
                torrent_hash = self.downloader.add_torrent(torrent_url=torrent_url)
            else:
                # Send torrent file bytes directly to qBittorrent
                torrent_url = f"file://{torrent.id}.torrent"  # Placeholder for logging
                torrent_hash = self.downloader.add_torrent(torrent_file=torrent_file_bytes)
            
            if not torrent_hash:
                logger.error("Failed to add torrent: add_torrent returned None")
                return None
            
            # Create download record
            download = Download(
                request_id=request.id,
                torrent_hash=torrent_hash,
                torrent_name=torrent.name,
                torrent_url=torrent_url,
                size_bytes=torrent.size_bytes or 0,
                status=DownloadStatus.DOWNLOADING
            )
            
            db.add(download)
            await db.commit()
            await db.refresh(download)
            
            logger.info(f"Started download: {torrent.name} (hash: {torrent_hash})")
            
            # Send notification
            size_gb = round(torrent.size_bytes / (1024**3), 2) if torrent.size_bytes else 0
            await self.notifier.notify_download_started(
                title=request.title,
                media_type=request.media_type.value,
                torrent_name=torrent.name,
                size=f"{size_gb} GB"
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
        """Process a completed download: rename, move, scan with workflow tracking."""
        workflow = WorkflowService(db)

        try:
            await self._update_status(db, request, RequestStatus.PROCESSING, "Renommage et déplacement...")

            download_path = torrent_info.get("content_path") or torrent_info.get("save_path")

            if not download_path:
                raise ValueError("Download path not found")

            # Start RENAME workflow step
            await workflow.start_step(request.id, WorkflowStepKey.RENAME)

            # Rename and move to library
            # Pass the external_id so renamer doesn't need to do async API lookup
            tmdb_id = int(request.external_id) if request.external_id and request.external_id.isdigit() else None

            result = self.renamer.process_download(
                download_path=download_path,
                media_type=request.media_type,
                media_title=request.title,
                year=request.year,
                tmdb_id=tmdb_id
            )

            if not result.get("success"):
                # Rename failed - create action for admin
                error_msg = result.get("error", "Rename failed")
                await workflow.fail_step(
                    request_id=request.id,
                    step_key=WorkflowStepKey.RENAME,
                    error_code="RENAME_FAILED",
                    error_message=error_msg,
                    artifacts={
                        "download_path": str(download_path),
                        "media_title": request.title,
                        "suggested_name": result.get("suggested_name"),
                        "files_found": result.get("files_found", [])
                    },
                    create_action=ActionType.CONFIRM_RENAME,
                    action_payload={
                        "original_path": str(download_path),
                        "original_name": result.get("original_name") or str(download_path).split("/")[-1],
                        "suggested_name": result.get("suggested_name"),
                        "alternatives": result.get("alternatives", []),
                        "error": error_msg
                    },
                    action_priority=60
                )
                raise ValueError(error_msg)

            final_path = result.get("final_path")

            # Complete RENAME step with artifacts
            await workflow.complete_step(
                request_id=request.id,
                step_key=WorkflowStepKey.RENAME,
                artifacts={
                    "original_path": str(download_path),
                    "final_path": final_path,
                    "files_processed": result.get("files_processed", [])
                }
            )

            download.final_path = final_path
            download.status = DownloadStatus.COMPLETED
            await db.commit()

            logger.info(f"Moved to library: {final_path}")

            # Start PLEX_SCAN workflow step
            await workflow.start_step(request.id, WorkflowStepKey.PLEX_SCAN)

            # Scan Plex library
            await self._update_status(db, request, RequestStatus.PROCESSING, "Scan Plex...")
            self.plex.scan_library()

            # Complete PLEX_SCAN step
            await workflow.complete_step(
                request_id=request.id,
                step_key=WorkflowStepKey.PLEX_SCAN,
                artifacts={"library_scanned": True}
            )

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
            # If it's not already tracked as a failed step, track it now
            await workflow.fail_step(
                request_id=request.id,
                step_key=WorkflowStepKey.RENAME,
                error_code="PROCESSING_ERROR",
                error_message=str(e)
            )
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


async def process_request_async(
    request_id: int,
    override_query: Optional[str] = None,
    restart_from_step: Optional[str] = None
):
    """Process a request asynchronously (for background task)."""
    pipeline = get_pipeline_service()
    await pipeline.process_request(request_id, override_query, restart_from_step)
