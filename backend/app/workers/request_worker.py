"""
Request Worker - Process media requests through the pipeline.

This worker handles the main workflow:
1. Search for torrents
2. Select best torrent (AI-powered)
3. Download via qBittorrent
4. Rename and organize files
5. Transfer to Plex library
6. Trigger Plex scan
7. Send notifications
"""
import asyncio
import logging
from typing import Dict, Any

from ..celery_app import celery_app
from ..models.database import AsyncSessionLocal
from ..models.request import MediaRequest, RequestStatus
from sqlalchemy import select

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.request_worker.process_request_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def process_request_task(self, request_id: int) -> Dict[str, Any]:
    """
    Process a media request through the complete pipeline.

    Args:
        request_id: ID of the MediaRequest to process

    Returns:
        Dict with processing results and status

    Raises:
        Retry on temporary failures
        Exception on permanent failures
    """

    async def run_pipeline():
        """Run async pipeline operations."""
        async with AsyncSessionLocal() as db:
            try:
                # 1. Load request
                result = await db.execute(
                    select(MediaRequest).where(MediaRequest.id == request_id)
                )
                request = result.scalar_one_or_none()

                if not request:
                    raise ValueError(f"Request {request_id} not found")

                logger.info(f"Processing request {request_id}: {request.title}")

                # Update status to processing
                request.status = RequestStatus.PROCESSING
                await db.commit()

                # 2. Initialize services with DI
                # Import here to avoid circular imports
                from ..dependencies import (
                    get_torrent_scraper_service,
                    get_ai_agent_service,
                    get_downloader_service,
                    get_file_renamer_service,
                    get_plex_manager_service,
                    get_notification_service,
                    get_settings_service,
                )
                from ..services.settings_service import SettingsService
                from ..services.torrent_scraper import TorrentScraperService
                from ..services.ai_agent import AIAgentService
                from ..services.downloader import DownloaderService
                from ..services.file_renamer import FileRenamerService
                from ..services.plex_manager import PlexManagerService
                from ..services.notifications import NotificationService

                # Create service instances
                settings_service = SettingsService(db)
                scraper = TorrentScraperService(settings_service)
                ai_agent = AIAgentService()
                downloader = DownloaderService()
                renamer = FileRenamerService(settings_service, None)  # TODO: title resolver
                plex_manager = PlexManagerService(settings_service)
                notifier = NotificationService()

                # 3. Search for torrents
                logger.info(f"Searching torrents for: {request.title}")
                torrents = await scraper.search(
                    title=request.title,
                    media_type=request.media_type,
                    year=request.year,
                    season=request.season_number,
                    episode=request.episode_number,
                )

                if not torrents:
                    raise Exception("No torrents found")

                logger.info(f"Found {len(torrents)} torrents")

                # 4. Select best torrent using AI
                logger.info("Using AI to select best torrent")
                best_torrent = await ai_agent.select_best_torrent(
                    torrents=torrents,
                    request_info={
                        "title": request.title,
                        "media_type": request.media_type,
                        "year": request.year,
                    }
                )

                if not best_torrent:
                    raise Exception("AI failed to select torrent")

                logger.info(f"Selected torrent: {best_torrent.get('title')}")

                # 5. Download torrent
                logger.info("Starting download")
                download = await downloader.add_torrent(
                    torrent_url=best_torrent["download_url"],
                    save_path=None,  # Use default from settings
                )

                # Update request with download info
                request.status = RequestStatus.DOWNLOADING
                await db.commit()

                # 6. Wait for download completion (async polling)
                logger.info("Waiting for download to complete")
                # This will be handled by download_monitor_worker
                # For now, just return success

                result = {
                    "status": "downloading",
                    "request_id": request_id,
                    "torrent": best_torrent["title"],
                    "download_hash": download.get("hash"),
                }

                logger.info(f"Request {request_id} pipeline initiated successfully")
                return result

            except Exception as e:
                logger.error(f"Error processing request {request_id}: {e}")

                # Update request status
                try:
                    request.status = RequestStatus.FAILED
                    request.error_message = str(e)
                    await db.commit()
                except:
                    pass

                # Retry on temporary failures
                if "connection" in str(e).lower() or "timeout" in str(e).lower():
                    raise self.retry(exc=e)

                raise

    # Run async pipeline
    return asyncio.run(run_pipeline())


@celery_app.task(name="app.workers.request_worker.complete_request_task")
def complete_request_task(request_id: int, download_path: str) -> Dict[str, Any]:
    """
    Complete request processing after download finishes.

    Called by download_monitor_worker when download completes.

    Args:
        request_id: ID of the MediaRequest
        download_path: Path to downloaded files

    Returns:
        Dict with completion status
    """

    async def complete_processing():
        """Complete async processing."""
        async with AsyncSessionLocal() as db:
            try:
                # Load request
                result = await db.execute(
                    select(MediaRequest).where(MediaRequest.id == request_id)
                )
                request = result.scalar_one_or_none()

                if not request:
                    raise ValueError(f"Request {request_id} not found")

                logger.info(f"Completing request {request_id}: {request.title}")

                # Initialize services
                from ..dependencies import (
                    get_file_renamer_service,
                    get_plex_manager_service,
                    get_notification_service,
                    get_settings_service,
                )
                from ..services.settings_service import SettingsService
                from ..services.file_renamer import FileRenamerService
                from ..services.plex_manager import PlexManagerService
                from ..services.notifications import NotificationService

                settings_service = SettingsService(db)
                renamer = FileRenamerService(settings_service, None)
                plex_manager = PlexManagerService(settings_service)
                notifier = NotificationService()

                # 1. Rename and organize files
                logger.info("Renaming and organizing files")
                organized_path = await renamer.process_download(
                    download_path=download_path,
                    media_type=request.media_type,
                    title=request.title,
                    year=request.year,
                    season=request.season_number,
                    episode=request.episode_number,
                )

                # 2. Update Plex library
                logger.info("Triggering Plex library scan")
                # plex_manager.scan_library()  # Sync method

                # 3. Update request status
                request.status = RequestStatus.COMPLETED
                await db.commit()

                # 4. Send notification
                await notifier.send_request_completed(request)

                logger.info(f"Request {request_id} completed successfully")

                return {
                    "status": "completed",
                    "request_id": request_id,
                    "path": organized_path,
                }

            except Exception as e:
                logger.error(f"Error completing request {request_id}: {e}")
                request.status = RequestStatus.FAILED
                request.error_message = str(e)
                await db.commit()
                raise

    return asyncio.run(complete_processing())
