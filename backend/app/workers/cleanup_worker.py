"""
Cleanup Worker - Maintenance and cleanup tasks.

Scheduled tasks:
- Daily 4 AM: Clean up old completed downloads
- Daily 5 AM: Clean up expired Celery task results
- Weekly: Database maintenance
"""
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from ..celery_app import celery_app
from ..models.database import AsyncSessionLocal
from ..models.download import Download, DownloadStatus
from ..models.request import MediaRequest, RequestStatus
from sqlalchemy import select, delete, func

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.cleanup_worker.cleanup_old_downloads_task")
def cleanup_old_downloads_task() -> Dict[str, Any]:
    """
    Clean up old completed/failed downloads from database.

    Keeps downloads for 30 days after completion.

    Returns:
        Dict with cleanup statistics
    """

    async def run_cleanup():
        """Run async cleanup operations."""
        async with AsyncSessionLocal() as db:
            try:
                logger.info("Starting old downloads cleanup")

                # Calculate cutoff date (30 days ago)
                cutoff_date = datetime.utcnow() - timedelta(days=30)

                # Delete old completed downloads
                result_completed = await db.execute(
                    delete(Download).where(
                        Download.status.in_([
                            DownloadStatus.COMPLETED,
                            DownloadStatus.SEEDED,
                        ]),
                        Download.completed_at < cutoff_date,
                    )
                )

                # Delete old failed downloads (keep for 7 days only)
                cutoff_failed = datetime.utcnow() - timedelta(days=7)
                result_failed = await db.execute(
                    delete(Download).where(
                        Download.status == DownloadStatus.FAILED,
                        Download.started_at < cutoff_failed,
                    )
                )

                await db.commit()

                completed_deleted = result_completed.rowcount
                failed_deleted = result_failed.rowcount
                total_deleted = completed_deleted + failed_deleted

                logger.info(
                    f"Cleaned up {total_deleted} old downloads "
                    f"({completed_deleted} completed, {failed_deleted} failed)"
                )

                return {
                    "status": "success",
                    "deleted": {
                        "completed": completed_deleted,
                        "failed": failed_deleted,
                        "total": total_deleted,
                    },
                }

            except Exception as e:
                logger.error(f"Error during downloads cleanup: {e}")
                await db.rollback()
                raise

    return asyncio.run(run_cleanup())


@celery_app.task(name="app.workers.cleanup_worker.cleanup_old_requests_task")
def cleanup_old_requests_task() -> Dict[str, Any]:
    """
    Clean up old completed/failed requests from database.

    Keeps requests for 90 days after completion.

    Returns:
        Dict with cleanup statistics
    """

    async def run_cleanup():
        """Run async cleanup operations."""
        async with AsyncSessionLocal() as db:
            try:
                logger.info("Starting old requests cleanup")

                # Calculate cutoff date (90 days ago)
                cutoff_date = datetime.utcnow() - timedelta(days=90)

                # Delete old completed requests
                result_completed = await db.execute(
                    delete(MediaRequest).where(
                        MediaRequest.status == RequestStatus.COMPLETED,
                        MediaRequest.completed_at < cutoff_date,
                    )
                )

                # Delete old failed requests (keep for 30 days)
                cutoff_failed = datetime.utcnow() - timedelta(days=30)
                result_failed = await db.execute(
                    delete(MediaRequest).where(
                        MediaRequest.status == RequestStatus.FAILED,
                        MediaRequest.requested_at < cutoff_failed,
                    )
                )

                await db.commit()

                completed_deleted = result_completed.rowcount
                failed_deleted = result_failed.rowcount
                total_deleted = completed_deleted + failed_deleted

                logger.info(
                    f"Cleaned up {total_deleted} old requests "
                    f"({completed_deleted} completed, {failed_deleted} failed)"
                )

                return {
                    "status": "success",
                    "deleted": {
                        "completed": completed_deleted,
                        "failed": failed_deleted,
                        "total": total_deleted,
                    },
                }

            except Exception as e:
                logger.error(f"Error during requests cleanup: {e}")
                await db.rollback()
                raise

    return asyncio.run(run_cleanup())


@celery_app.task(name="app.workers.cleanup_worker.cleanup_expired_task_results")
def cleanup_expired_task_results() -> Dict[str, Any]:
    """
    Clean up expired Celery task results from Redis.

    Celery keeps results for result_expires (24h by default).
    This task forces cleanup of very old results.

    Returns:
        Dict with cleanup statistics
    """
    try:
        logger.info("Starting expired task results cleanup")

        # Get Celery app
        from ..celery_app import celery_app

        # Get result backend
        backend = celery_app.backend

        # Clean up expired results
        # This uses Redis SCAN to find and delete expired keys
        cleaned = 0

        # Get Redis client
        if hasattr(backend, 'client'):
            redis_client = backend.client

            # Scan for old result keys
            cursor = 0
            pattern = "celery-task-meta-*"

            while True:
                cursor, keys = redis_client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )

                for key in keys:
                    # Get TTL
                    ttl = redis_client.ttl(key)

                    # If no TTL set or expired, delete
                    if ttl == -1 or ttl == -2:
                        redis_client.delete(key)
                        cleaned += 1

                if cursor == 0:
                    break

        logger.info(f"Cleaned up {cleaned} expired task results")

        return {
            "status": "success",
            "cleaned": cleaned,
        }

    except Exception as e:
        logger.error(f"Error during task results cleanup: {e}")
        raise


@celery_app.task(name="app.workers.cleanup_worker.database_maintenance_task")
def database_maintenance_task() -> Dict[str, Any]:
    """
    Perform database maintenance operations.

    - VACUUM (PostgreSQL only)
    - ANALYZE to update statistics
    - Rebuild indexes if needed

    Returns:
        Dict with maintenance statistics
    """

    async def run_maintenance():
        """Run async maintenance operations."""
        async with AsyncSessionLocal() as db:
            try:
                logger.info("Starting database maintenance")

                # Check if PostgreSQL
                from ..models.database import is_postgres

                if is_postgres:
                    # Run VACUUM ANALYZE (must be outside transaction)
                    await db.execute("VACUUM ANALYZE")
                    logger.info("Ran VACUUM ANALYZE")

                # Get table statistics
                stats = {}

                # Count records in main tables
                from ..models.user import User
                from ..models.request import MediaRequest
                from ..models.download import Download
                from ..models.plex_library import PlexLibraryItem

                for model_name, model in [
                    ("users", User),
                    ("requests", MediaRequest),
                    ("downloads", Download),
                    ("plex_library", PlexLibraryItem),
                ]:
                    result = await db.execute(select(func.count()).select_from(model))
                    count = result.scalar()
                    stats[model_name] = count

                logger.info(f"Database statistics: {stats}")

                return {
                    "status": "success",
                    "stats": stats,
                }

            except Exception as e:
                logger.error(f"Error during database maintenance: {e}")
                raise

    return asyncio.run(run_maintenance())


@celery_app.task(name="app.workers.cleanup_worker.cleanup_temp_files_task")
def cleanup_temp_files_task() -> Dict[str, Any]:
    """
    Clean up temporary files from download directory.

    Removes:
    - Old .torrent files
    - Incomplete downloads
    - Temporary extraction files

    Returns:
        Dict with cleanup statistics
    """
    try:
        import shutil
        from pathlib import Path

        logger.info("Starting temp files cleanup")

        from ..config import get_settings
        settings = get_settings()

        download_path = Path(settings.download_path)

        if not download_path.exists():
            logger.warning(f"Download path does not exist: {download_path}")
            return {"status": "skipped", "reason": "path_not_found"}

        stats = {
            "torrents_removed": 0,
            "temp_removed": 0,
            "space_freed_mb": 0,
        }

        # Remove old .torrent files (older than 7 days)
        cutoff_time = datetime.utcnow().timestamp() - (7 * 24 * 3600)

        for torrent_file in download_path.glob("*.torrent"):
            if torrent_file.stat().st_mtime < cutoff_time:
                size_mb = torrent_file.stat().st_size / (1024 * 1024)
                torrent_file.unlink()
                stats["torrents_removed"] += 1
                stats["space_freed_mb"] += size_mb

        # Remove temp directories (older than 7 days)
        for item in download_path.iterdir():
            if item.is_dir() and item.name.startswith("temp_"):
                if item.stat().st_mtime < cutoff_time:
                    size_mb = sum(
                        f.stat().st_size for f in item.rglob("*") if f.is_file()
                    ) / (1024 * 1024)
                    shutil.rmtree(item)
                    stats["temp_removed"] += 1
                    stats["space_freed_mb"] += size_mb

        logger.info(
            f"Temp files cleanup complete: removed {stats['torrents_removed']} torrents, "
            f"{stats['temp_removed']} temp dirs, freed {stats['space_freed_mb']:.2f} MB"
        )

        return {
            "status": "success",
            "stats": stats,
        }

    except Exception as e:
        logger.error(f"Error during temp files cleanup: {e}")
        raise
