"""
Celery application configuration for Plex Kiosk.

This module configures Celery for background task processing:
- Request processing pipeline
- Plex library synchronization
- Download monitoring
- Cleanup tasks

Architecture:
- Broker: Redis (task queue)
- Backend: Redis (result storage)
- Workers: Async support via asyncio
- Beat: Scheduled periodic tasks
"""
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from .config import get_settings

settings = get_settings()

# =============================================================================
# CELERY APP
# =============================================================================

celery_app = Celery(
    "plex_kiosk",
    broker=settings.redis_url,
    backend=settings.redis_url.replace("/0", "/1"),  # Use DB 1 for results
    include=[
        "app.workers.request_worker",
        "app.workers.plex_sync_worker",
        "app.workers.download_monitor_worker",
        "app.workers.cleanup_worker",
    ]
)

# =============================================================================
# CELERY CONFIGURATION
# =============================================================================

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Paris",
    enable_utc=True,

    # Task execution
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (prevent memory leaks)

    # Results
    result_expires=86400,  # Keep results for 24 hours
    result_backend_transport_options={
        "master_name": "mymaster",
        "visibility_timeout": 3600,
    },

    # Task routing
    task_default_queue="default",
    task_queues=(
        Queue("default", routing_key="task.#"),
        Queue("priority", routing_key="priority.#"),
        Queue("plex_sync", routing_key="plex.#"),
        Queue("downloads", routing_key="downloads.#"),
    ),

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,

    # Worker
    worker_prefetch_multiplier=4,  # Fetch 4 tasks per worker
    worker_max_memory_per_child=400000,  # 400MB per worker (restart after)

    # Beat schedule (periodic tasks)
    beat_schedule={
        # Plex library sync - every hour
        "plex-sync-hourly": {
            "task": "app.workers.plex_sync_worker.sync_plex_library_task",
            "schedule": crontab(minute=0),  # Top of every hour
            "kwargs": {"full_sync": False},
            "options": {"queue": "plex_sync"},
        },

        # Full Plex sync - daily at 3 AM
        "plex-sync-daily-full": {
            "task": "app.workers.plex_sync_worker.sync_plex_library_task",
            "schedule": crontab(hour=3, minute=0),
            "kwargs": {"full_sync": True},
            "options": {"queue": "plex_sync"},
        },

        # Monitor active downloads - every 5 minutes
        "download-monitor": {
            "task": "app.workers.download_monitor_worker.monitor_downloads_task",
            "schedule": 300.0,  # 5 minutes
            "options": {"queue": "downloads"},
        },

        # Cleanup old completed downloads - daily at 4 AM
        "cleanup-downloads": {
            "task": "app.workers.cleanup_worker.cleanup_old_downloads_task",
            "schedule": crontab(hour=4, minute=0),
            "options": {"queue": "default"},
        },

        # Cleanup expired results - daily at 5 AM
        "cleanup-expired-results": {
            "task": "app.workers.cleanup_worker.cleanup_expired_task_results",
            "schedule": crontab(hour=5, minute=0),
            "options": {"queue": "default"},
        },
    },
)

# =============================================================================
# CELERY SIGNALS (for monitoring)
# =============================================================================

from celery.signals import task_prerun, task_postrun, task_failure  # noqa: E402
import logging  # noqa: E402

logger = logging.getLogger(__name__)


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    """Log task start."""
    logger.info(f"Task {task.name} [{task_id}] starting with args={args}, kwargs={kwargs}")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, **extra):
    """Log task completion."""
    logger.info(f"Task {task.name} [{task_id}] completed successfully")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extra):
    """Log task failure."""
    logger.error(f"Task {sender.name} [{task_id}] failed: {exception}")
    logger.error(f"Traceback: {traceback}")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_celery_app() -> Celery:
    """Get Celery app instance (for imports)."""
    return celery_app
