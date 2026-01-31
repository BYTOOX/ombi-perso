"""
Scheduler Service for background tasks.
Uses APScheduler to run periodic tasks:
- Health checks every 5 minutes
- Episode monitoring every 6 hours
- VOSTFR scan every 6 hours
- Library analysis every Sunday at 3 AM
"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing scheduled background tasks."""

    _instance: Optional["SchedulerService"] = None
    _scheduler: Optional[AsyncIOScheduler] = None
    _is_running: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler(
                timezone="Europe/Paris",
                job_defaults={
                    "coalesce": True,  # Combine missed runs into one
                    "max_instances": 1,  # Only one instance of each job
                    "misfire_grace_time": 300,  # 5 minutes grace time
                }
            )
            self._setup_jobs()

    def _setup_jobs(self):
        """Configure all scheduled jobs."""
        # Health checks - every 5 minutes
        self._scheduler.add_job(
            self._run_health_checks,
            trigger=IntervalTrigger(minutes=5),
            id="health_checks",
            name="Health Checks",
            replace_existing=True
        )

        # Episode monitoring - every 6 hours
        self._scheduler.add_job(
            self._run_episode_check,
            trigger=IntervalTrigger(hours=6),
            id="episode_check",
            name="Episode Check",
            replace_existing=True
        )

        # VOSTFR upgrade scan - every 6 hours (offset by 1 hour from episode check)
        self._scheduler.add_job(
            self._run_vostfr_scan,
            trigger=CronTrigger(hour="1,7,13,19", minute=0),
            id="vostfr_scan",
            name="VOSTFR Upgrade Scan",
            replace_existing=True
        )

        # Library analysis - Sunday at 3 AM
        self._scheduler.add_job(
            self._run_library_analysis,
            trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
            id="library_analysis",
            name="Weekly Library Analysis",
            replace_existing=True
        )

        # Update aired episodes - every 2 hours
        self._scheduler.add_job(
            self._run_aired_update,
            trigger=IntervalTrigger(hours=2),
            id="aired_update",
            name="Update Aired Episodes",
            replace_existing=True
        )

        logger.info("Scheduled jobs configured")

    async def start(self):
        """Start the scheduler."""
        if not self._is_running:
            self._scheduler.start()
            self._is_running = True
            logger.info("Scheduler started")

    async def stop(self):
        """Stop the scheduler."""
        if self._is_running:
            self._scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Scheduler stopped")

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._is_running

    def get_jobs_status(self) -> list:
        """Get status of all scheduled jobs."""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        return jobs

    async def run_job_now(self, job_id: str) -> bool:
        """Manually trigger a job to run immediately."""
        job = self._scheduler.get_job(job_id)
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return False

        # Run the job function directly
        job_funcs = {
            "health_checks": self._run_health_checks,
            "episode_check": self._run_episode_check,
            "vostfr_scan": self._run_vostfr_scan,
            "library_analysis": self._run_library_analysis,
            "aired_update": self._run_aired_update,
        }

        func = job_funcs.get(job_id)
        if func:
            logger.info(f"Manually triggering job: {job_id}")
            await func()
            return True
        return False

    # =========================================================================
    # JOB FUNCTIONS
    # =========================================================================

    async def _run_health_checks(self):
        """Run health checks on all configured services."""
        logger.info("Running scheduled health checks...")
        try:
            from .healthcheck_service import get_healthcheck_service
            healthcheck = get_healthcheck_service()
            results = await healthcheck.check_all_services()

            # Log summary
            ok_count = sum(1 for r in results.values() if r.status == "ok")
            error_count = sum(1 for r in results.values() if r.status == "error")
            logger.info(f"Health check complete: {ok_count} OK, {error_count} errors")

            # Send Discord notification if there are errors
            if error_count > 0:
                await self._notify_health_errors(results)

        except Exception as e:
            logger.error(f"Health check job failed: {e}")

    async def _run_episode_check(self):
        """Check for new episodes to download."""
        logger.info("Running scheduled episode check...")
        try:
            from .release_monitor_service import get_release_monitor_service
            monitor = get_release_monitor_service()
            result = await monitor.check_for_new_episodes()
            logger.info(f"Episode check complete: {result}")
        except Exception as e:
            logger.error(f"Episode check job failed: {e}")

    async def _run_vostfr_scan(self):
        """Scan library for VOSTFR content that can be upgraded."""
        logger.info("Running scheduled VOSTFR scan...")
        try:
            from .vostfr_upgrade_service import get_vostfr_upgrade_service
            vostfr = get_vostfr_upgrade_service()
            result = await vostfr.scan_library_for_vostfr()
            logger.info(f"VOSTFR scan complete: {result}")
        except Exception as e:
            logger.error(f"VOSTFR scan job failed: {e}")

    async def _run_library_analysis(self):
        """Run weekly library quality analysis."""
        logger.info("Running scheduled library analysis...")
        try:
            from .library_analysis_service import get_library_analysis_service
            analysis = get_library_analysis_service()

            # Run full analysis
            run = await analysis.start_analysis(
                analysis_types=None,  # All types
                media_types=None,  # All media
                user_id=None  # System-triggered
            )

            logger.info(f"Library analysis started: {run.id}")

            # Notify admin of completion
            await self._notify_analysis_complete(run.id)

        except Exception as e:
            logger.error(f"Library analysis job failed: {e}")

    async def _run_aired_update(self):
        """Update status of aired episodes."""
        logger.info("Running scheduled aired update...")
        try:
            from .release_monitor_service import get_release_monitor_service
            monitor = get_release_monitor_service()
            result = await monitor.update_aired_status()
            logger.info(f"Aired update complete: {result}")
        except Exception as e:
            logger.error(f"Aired update job failed: {e}")

    # =========================================================================
    # NOTIFICATION HELPERS
    # =========================================================================

    async def _notify_health_errors(self, results: dict):
        """Send Discord notification for health check errors."""
        try:
            from .notifications import get_notification_service
            notif = get_notification_service()

            errors = []
            for service_name, result in results.items():
                if result.status == "error":
                    errors.append(f"- **{service_name}**: {result.message}")

            if errors:
                message = "**⚠️ Alertes Santé Services**\n\n" + "\n".join(errors)
                await notif.send_notification(
                    title="Problèmes de santé détectés",
                    message=message,
                    notification_type="error"
                )
        except Exception as e:
            logger.error(f"Failed to send health error notification: {e}")

    async def _notify_analysis_complete(self, run_id: str):
        """Send Discord notification when analysis completes."""
        try:
            from .library_analysis_service import get_library_analysis_service
            from .notifications import get_notification_service

            analysis = get_library_analysis_service()
            notif = get_notification_service()

            # Wait for analysis to complete (max 30 minutes)
            import asyncio
            for _ in range(180):  # 180 x 10s = 30 minutes
                run = await analysis.get_run(run_id)
                if run and run.status in ["completed", "failed", "cancelled"]:
                    break
                await asyncio.sleep(10)

            run = await analysis.get_run(run_id)
            if run and run.status == "completed":
                summary = await analysis.get_summary()
                message = (
                    f"**📊 Analyse Bibliothèque Terminée**\n\n"
                    f"- Items analysés: {run.items_analyzed}\n"
                    f"- Problèmes détectés: {run.issues_found}\n"
                    f"  - 🔴 Haute: {summary.get('by_severity', {}).get('high', 0)}\n"
                    f"  - 🟠 Moyenne: {summary.get('by_severity', {}).get('medium', 0)}\n"
                    f"  - 🟢 Basse: {summary.get('by_severity', {}).get('low', 0)}\n"
                    f"- Durée: {run.duration_seconds}s"
                )
                await notif.send_notification(
                    title="Analyse hebdomadaire terminée",
                    message=message,
                    notification_type="info"
                )
        except Exception as e:
            logger.error(f"Failed to send analysis notification: {e}")


# Singleton accessor
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """Get or create the scheduler service singleton."""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
