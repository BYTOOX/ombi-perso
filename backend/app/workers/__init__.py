"""
Celery workers for background task processing.

Workers:
- request_worker: Process media requests through pipeline
- plex_sync_worker: Synchronize Plex library
- download_monitor_worker: Monitor qBittorrent downloads
- cleanup_worker: Maintenance and cleanup tasks
"""

# Export all tasks for Celery discovery
from .request_worker import process_request_task
from .plex_sync_worker import sync_plex_library_task
from .download_monitor_worker import monitor_downloads_task
from .cleanup_worker import (
    cleanup_old_downloads_task,
    cleanup_expired_task_results,
)

__all__ = [
    "process_request_task",
    "sync_plex_library_task",
    "monitor_downloads_task",
    "cleanup_old_downloads_task",
    "cleanup_expired_task_results",
]
