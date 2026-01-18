"""
Plex Sync Worker - Synchronize Plex library with database.

Scheduled tasks:
- Hourly: Incremental sync (new items only)
- Daily 3 AM: Full sync (all items)
"""
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from ..celery_app import celery_app
from ..models.database import AsyncSessionLocal
from ..models.plex_library import PlexLibraryItem, PlexSyncStatus
from sqlalchemy import select, delete

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.plex_sync_worker.sync_plex_library_task",
    bind=True,
)
def sync_plex_library_task(self, full_sync: bool = False) -> Dict[str, Any]:
    """
    Synchronize Plex library with local database.

    Args:
        full_sync: If True, sync all items. If False, only new items.

    Returns:
        Dict with sync statistics
    """

    async def run_sync():
        """Run async sync operations."""
        async with AsyncSessionLocal() as db:
            try:
                logger.info(f"Starting Plex sync (full_sync={full_sync})")

                # Initialize services
                from ..services.settings_service import SettingsService
                from ..services.plex_manager import PlexManagerService

                settings_service = SettingsService(db)
                plex_manager = PlexManagerService(settings_service)

                # Check if Plex is configured
                if not plex_manager.is_configured:
                    logger.warning("Plex is not configured, skipping sync")
                    return {"status": "skipped", "reason": "not_configured"}

                stats = {
                    "added": 0,
                    "updated": 0,
                    "removed": 0,
                    "total": 0,
                }

                # Get all items from Plex
                logger.info("Fetching items from Plex")
                plex_items = plex_manager.get_all_library_items()
                stats["total"] = len(plex_items)

                logger.info(f"Found {len(plex_items)} items in Plex library")

                # Track Plex keys we've seen
                seen_keys = set()

                # Process each item
                for plex_item in plex_items:
                    plex_key = plex_item["plex_key"]
                    seen_keys.add(plex_key)

                    # Check if item exists in DB
                    result = await db.execute(
                        select(PlexLibraryItem).where(
                            PlexLibraryItem.plex_key == plex_key
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        # Update existing item
                        existing.title = plex_item["title"]
                        existing.media_type = plex_item["media_type"]
                        existing.year = plex_item.get("year")
                        existing.tmdb_id = plex_item.get("tmdb_id")
                        existing.imdb_id = plex_item.get("imdb_id")
                        existing.library_section = plex_item.get("library_section")
                        existing.file_path = plex_item.get("file_path")
                        existing.added_at = plex_item.get("added_at")
                        existing.updated_at = datetime.utcnow()
                        existing.last_synced = datetime.utcnow()
                        existing.sync_status = PlexSyncStatus.SYNCED
                        stats["updated"] += 1
                    else:
                        # Add new item
                        new_item = PlexLibraryItem(
                            plex_key=plex_key,
                            title=plex_item["title"],
                            media_type=plex_item["media_type"],
                            year=plex_item.get("year"),
                            tmdb_id=plex_item.get("tmdb_id"),
                            imdb_id=plex_item.get("imdb_id"),
                            library_section=plex_item.get("library_section"),
                            file_path=plex_item.get("file_path"),
                            added_at=plex_item.get("added_at"),
                            last_synced=datetime.utcnow(),
                            sync_status=PlexSyncStatus.SYNCED,
                        )
                        db.add(new_item)
                        stats["added"] += 1

                # Remove items no longer in Plex (if full sync)
                if full_sync:
                    # Get all DB items
                    result = await db.execute(select(PlexLibraryItem))
                    db_items = result.scalars().all()

                    for db_item in db_items:
                        if db_item.plex_key not in seen_keys:
                            await db.delete(db_item)
                            stats["removed"] += 1

                await db.commit()

                logger.info(
                    f"Plex sync completed: {stats['added']} added, "
                    f"{stats['updated']} updated, {stats['removed']} removed"
                )

                return {
                    "status": "success",
                    "full_sync": full_sync,
                    "stats": stats,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                logger.error(f"Error during Plex sync: {e}")
                await db.rollback()
                raise

    return asyncio.run(run_sync())


@celery_app.task(name="app.workers.plex_sync_worker.cleanup_old_sync_data")
def cleanup_old_sync_data() -> Dict[str, Any]:
    """
    Clean up old sync data (items not synced in 30 days).

    Returns:
        Dict with cleanup statistics
    """

    async def run_cleanup():
        """Run async cleanup operations."""
        async with AsyncSessionLocal() as db:
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=30)

                # Delete items not synced in 30 days
                result = await db.execute(
                    delete(PlexLibraryItem).where(
                        PlexLibraryItem.last_synced < cutoff_date
                    )
                )

                deleted_count = result.rowcount
                await db.commit()

                logger.info(f"Cleaned up {deleted_count} old Plex library items")

                return {
                    "status": "success",
                    "deleted": deleted_count,
                }

            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                await db.rollback()
                raise

    return asyncio.run(run_cleanup())
