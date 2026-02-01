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
def process_request_task(
    self,
    request_id: int,
    override_query: str = None,
    restart_from_step: str = None
) -> Dict[str, Any]:
    """
    Process a media request through the complete pipeline.

    Args:
        request_id: ID of the MediaRequest to process
        override_query: Optional search query override (for action resolution)
        restart_from_step: Optional step key to restart from (for retries)

    Returns:
        Dict with processing results and status

    Raises:
        Retry on temporary failures
        Exception on permanent failures
    """
    from ..services.pipeline import get_pipeline_service

    async def run_pipeline():
        """Run async pipeline operations using the pipeline service."""
        try:
            pipeline = get_pipeline_service()
            success = await pipeline.process_request(
                request_id=request_id,
                override_query=override_query,
                restart_from_step=restart_from_step
            )

            if success:
                logger.info(f"Request {request_id} pipeline completed successfully")
                return {
                    "status": "success",
                    "request_id": request_id,
                }
            else:
                logger.warning(f"Request {request_id} pipeline returned False")
                return {
                    "status": "failed",
                    "request_id": request_id,
                }

        except Exception as e:
            logger.error(f"Error processing request {request_id}: {e}")

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
                from ..services.settings_service import SettingsService
                from ..services.file_renamer import FileRenamerService
                from ..services.plex_manager import PlexManagerService
                from ..services.notifications import NotificationService

                settings_service = SettingsService(db)
                renamer = FileRenamerService(settings_service, None)
                _plex_manager = PlexManagerService(settings_service)
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
