"""
Download Monitor Worker - Monitor qBittorrent downloads.

This worker:
1. Checks active downloads every 5 minutes
2. Updates progress in database
3. Triggers completion workflow when download finishes
4. Handles errors and retries
"""
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from ..celery_app import celery_app
from ..models.database import AsyncSessionLocal
from ..models.download import Download, DownloadStatus
from ..models.request import MediaRequest, RequestStatus
from sqlalchemy import select

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.download_monitor_worker.monitor_downloads_task",
    bind=True,
)
def monitor_downloads_task(self) -> Dict[str, Any]:
    """
    Monitor all active downloads and update their status.

    Runs every 5 minutes via Celery Beat.

    Returns:
        Dict with monitoring statistics
    """

    async def run_monitor():
        """Run async monitoring operations."""
        async with AsyncSessionLocal() as db:
            try:
                logger.info("Starting download monitoring")

                # Initialize downloader service
                from ..services.downloader import DownloaderService
                downloader = DownloaderService()

                # Get all active downloads from DB
                result = await db.execute(
                    select(Download).where(
                        Download.status.in_([
                            DownloadStatus.QUEUED,
                            DownloadStatus.DOWNLOADING,
                            DownloadStatus.PAUSED,
                        ])
                    )
                )
                active_downloads = result.scalars().all()

                if not active_downloads:
                    logger.info("No active downloads to monitor")
                    return {"status": "success", "monitored": 0}

                logger.info(f"Monitoring {len(active_downloads)} active downloads")

                stats = {
                    "monitored": len(active_downloads),
                    "completed": 0,
                    "failed": 0,
                    "active": 0,
                }

                # Check each download
                for download in active_downloads:
                    try:
                        # Get torrent info from qBittorrent
                        torrent_info = await downloader.get_torrent_info(
                            download.torrent_hash
                        )

                        if not torrent_info:
                            logger.warning(
                                f"Torrent {download.torrent_hash} not found in qBittorrent"
                            )
                            continue

                        # Update download info
                        download.progress = torrent_info.get("progress", 0.0) * 100
                        download.download_speed = torrent_info.get("dlspeed", 0)
                        download.upload_speed = torrent_info.get("upspeed", 0)
                        download.eta = torrent_info.get("eta")
                        download.size_total = torrent_info.get("total_size")
                        download.size_downloaded = torrent_info.get("downloaded")

                        # Check status
                        qb_state = torrent_info.get("state", "").lower()

                        if qb_state in ["downloading", "stalledDL", "metaDL"]:
                            download.status = DownloadStatus.DOWNLOADING
                            stats["active"] += 1

                        elif qb_state in ["pausedDL", "pausedUP"]:
                            download.status = DownloadStatus.PAUSED
                            stats["active"] += 1

                        elif qb_state in ["uploading", "stalledUP", "queuedUP"]:
                            # Download completed, now seeding
                            if download.status != DownloadStatus.COMPLETED:
                                logger.info(
                                    f"Download completed: {download.torrent_name}"
                                )
                                download.status = DownloadStatus.COMPLETED
                                download.completed_at = datetime.utcnow()
                                download.progress = 100.0
                                stats["completed"] += 1

                                # Trigger completion workflow
                                await self._trigger_completion(
                                    download, torrent_info, db
                                )

                        elif qb_state in ["error", "missingFiles"]:
                            download.status = DownloadStatus.FAILED
                            download.error_message = torrent_info.get("error", "Unknown error")
                            stats["failed"] += 1

                            # Update request status
                            await self._mark_request_failed(download, db)

                        await db.commit()

                    except Exception as e:
                        logger.error(
                            f"Error monitoring download {download.id}: {e}"
                        )
                        continue

                logger.info(
                    f"Monitoring complete: {stats['completed']} completed, "
                    f"{stats['failed']} failed, {stats['active']} active"
                )

                return {"status": "success", "stats": stats}

            except Exception as e:
                logger.error(f"Error during download monitoring: {e}")
                await db.rollback()
                raise

    async def _trigger_completion(download: Download, torrent_info: dict, db):
        """Trigger request completion workflow."""
        try:
            # Get save path
            save_path = torrent_info.get("save_path") or download.save_path

            if not save_path:
                logger.error(f"No save path for download {download.id}")
                return

            # Queue completion task
            from .request_worker import complete_request_task
            complete_request_task.delay(
                request_id=download.request_id,
                download_path=save_path,
            )

            logger.info(
                f"Queued completion task for request {download.request_id}"
            )

        except Exception as e:
            logger.error(f"Error triggering completion: {e}")

    async def _mark_request_failed(download: Download, db):
        """Mark associated request as failed."""
        try:
            result = await db.execute(
                select(MediaRequest).where(
                    MediaRequest.id == download.request_id
                )
            )
            request = result.scalar_one_or_none()

            if request:
                request.status = RequestStatus.FAILED
                request.error_message = download.error_message or "Download failed"
                await db.commit()

        except Exception as e:
            logger.error(f"Error marking request failed: {e}")

    # Bind helper methods to task
    self._trigger_completion = _trigger_completion
    self._mark_request_failed = _mark_request_failed

    return asyncio.run(run_monitor())


@celery_app.task(name="app.workers.download_monitor_worker.cleanup_finished_torrents")
def cleanup_finished_torrents() -> Dict[str, Any]:
    """
    Clean up finished torrents after seeding period.

    Removes torrents that have been seeding for SEED_DURATION_HOURS.

    Returns:
        Dict with cleanup statistics
    """

    async def run_cleanup():
        """Run async cleanup operations."""
        async with AsyncSessionLocal() as db:
            try:
                from ..config import get_settings
                from datetime import timedelta

                settings = get_settings()

                # Calculate cutoff time
                cutoff_time = datetime.utcnow() - timedelta(
                    hours=settings.seed_duration_hours
                )

                # Get completed downloads past seeding period
                result = await db.execute(
                    select(Download).where(
                        Download.status == DownloadStatus.COMPLETED,
                        Download.completed_at < cutoff_time,
                    )
                )
                old_downloads = result.scalars().all()

                if not old_downloads:
                    logger.info("No torrents to clean up")
                    return {"status": "success", "removed": 0}

                logger.info(f"Cleaning up {len(old_downloads)} old torrents")

                # Initialize downloader
                from ..services.downloader import DownloaderService
                downloader = DownloaderService()

                removed_count = 0

                for download in old_downloads:
                    try:
                        # Remove from qBittorrent
                        await downloader.remove_torrent(
                            download.torrent_hash,
                            delete_files=False,  # Keep files
                        )

                        # Update status
                        download.status = DownloadStatus.SEEDED
                        removed_count += 1

                        logger.info(
                            f"Removed torrent: {download.torrent_name}"
                        )

                    except Exception as e:
                        logger.error(
                            f"Error removing torrent {download.torrent_hash}: {e}"
                        )
                        continue

                await db.commit()

                logger.info(f"Cleaned up {removed_count} torrents")

                return {
                    "status": "success",
                    "removed": removed_count,
                }

            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                await db.rollback()
                raise

    return asyncio.run(run_cleanup())
