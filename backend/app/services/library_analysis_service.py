"""
Library Analysis Service for AI-powered quality analysis of Plex library.

Analyzes the library for:
- Missing films in collections/franchises
- Low quality content (480p, SD)
- Bad codecs (MPEG4, Xvid, non-HEVC)
- VOSTFR content with MULTI available
- Missing episodes/seasons in series
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import select, and_

from ..models.database import AsyncSessionLocal
from ..models.library_analysis import (
    AnalysisRun,
    LibraryAnalysisResult,
    AnalysisType,
    Severity,
    AnalysisRunStatus
)
from .service_config_service import get_service_config_service
from .notifications import NotificationService

logger = logging.getLogger(__name__)


class LibraryAnalysisService:
    """
    Service for comprehensive library quality analysis.

    Analysis types:
    1. Missing Collections: Checks TMDB for missing films in franchises
    2. Low Quality: Detects 480p, SD content
    3. Bad Codec: Finds MPEG4, Xvid, non-HEVC content
    4. VOSTFR Upgradable: Finds VOSTFR with MULTI available
    5. Missing Episodes: Detects incomplete series
    """

    # Quality thresholds
    LOW_QUALITY_RESOLUTIONS = ["480p", "360p", "sd", "dvdrip", "dvdscr"]
    BAD_CODECS = ["mpeg4", "xvid", "divx", "mpeg2", "wmv"]
    RECOMMENDED_CODECS = ["hevc", "x265", "h265", "av1"]

    def __init__(self):
        self._config_service = get_service_config_service()
        self._notification_service = NotificationService()

    async def _get_tmdb_api_key(self) -> Optional[str]:
        """Get TMDB API key from database config."""
        config = await self._config_service.get_service_config("tmdb")
        if config and config.api_key_encrypted:
            return await self._config_service.get_decrypted_value("tmdb", "api_key")
        return None

    # =========================================================================
    # ANALYSIS RUN MANAGEMENT
    # =========================================================================

    async def start_analysis(
        self,
        analysis_types: Optional[List[str]] = None,
        media_types: Optional[List[str]] = None,
        user_id: Optional[int] = None
    ) -> AnalysisRun:
        """
        Start a new library analysis run.

        Args:
            analysis_types: Types of analysis to perform (None = all)
            media_types: Media types to analyze (movie, series, anime)
            user_id: ID of user who triggered the analysis

        Returns:
            Created AnalysisRun object
        """
        async with AsyncSessionLocal() as session:
            run = AnalysisRun(
                id=str(uuid.uuid4()),
                status=AnalysisRunStatus.PENDING.value,
                analysis_types=analysis_types,
                media_types=media_types,
                triggered_by_user_id=user_id
            )

            session.add(run)
            await session.commit()
            await session.refresh(run)

            logger.info(f"Created analysis run: {run.id}")

            # Start analysis in background (non-blocking)
            asyncio.create_task(self._run_analysis(run.id))

            return run

    async def _run_analysis(self, run_id: str):
        """Execute the library analysis."""
        logger.info(f"Starting analysis run: {run_id}")

        try:
            async with AsyncSessionLocal() as session:
                run = await session.get(AnalysisRun, run_id)
                if not run:
                    return

                run.status = AnalysisRunStatus.RUNNING.value
                run.started_at = datetime.utcnow()
                await session.commit()

            # Determine which analyses to run
            analyses_to_run = run.analysis_types or [t.value for t in AnalysisType]
            media_types = run.media_types or ["movie", "series", "anime"]

            issues_found = 0
            issues_by_type = {}
            issues_by_severity = {}

            # Run each analysis type
            for analysis_type in analyses_to_run:
                try:
                    async with AsyncSessionLocal() as session:
                        r = await session.get(AnalysisRun, run_id)
                        if r:
                            r.current_phase = analysis_type
                            await session.commit()

                    count = await self._run_analysis_type(run_id, analysis_type, media_types)
                    issues_found += count
                    issues_by_type[analysis_type] = count

                except Exception as e:
                    logger.error(f"Error in analysis type {analysis_type}: {e}")

            # Calculate severity distribution
            async with AsyncSessionLocal() as session:
                results = await session.execute(
                    select(LibraryAnalysisResult)
                    .where(LibraryAnalysisResult.analysis_run_id == run_id)
                )
                all_results = list(results.scalars().all())

                for result in all_results:
                    issues_by_severity[result.severity] = issues_by_severity.get(result.severity, 0) + 1

                # Update run with final results
                run = await session.get(AnalysisRun, run_id)
                if run:
                    run.status = AnalysisRunStatus.COMPLETED.value
                    run.completed_at = datetime.utcnow()
                    run.issues_found = issues_found
                    run.issues_by_type = issues_by_type
                    run.issues_by_severity = issues_by_severity
                    run.current_phase = None
                    await session.commit()

            logger.info(f"Analysis run {run_id} completed: {issues_found} issues found")

            # Send notification
            await self._send_analysis_complete_notification(run_id, issues_found, issues_by_severity)

        except Exception as e:
            logger.error(f"Analysis run {run_id} failed: {e}")

            async with AsyncSessionLocal() as session:
                run = await session.get(AnalysisRun, run_id)
                if run:
                    run.status = AnalysisRunStatus.FAILED.value
                    run.error_message = str(e)
                    run.completed_at = datetime.utcnow()
                    await session.commit()

    async def _run_analysis_type(
        self,
        run_id: str,
        analysis_type: str,
        media_types: List[str]
    ) -> int:
        """Run a specific type of analysis."""
        logger.info(f"Running analysis type: {analysis_type}")

        if analysis_type == AnalysisType.MISSING_COLLECTION.value:
            return await self._analyze_missing_collections(run_id, media_types)
        elif analysis_type == AnalysisType.LOW_QUALITY.value:
            return await self._analyze_low_quality(run_id, media_types)
        elif analysis_type == AnalysisType.BAD_CODEC.value:
            return await self._analyze_bad_codecs(run_id, media_types)
        elif analysis_type == AnalysisType.VOSTFR_UPGRADABLE.value:
            return await self._analyze_vostfr_upgradable(run_id, media_types)
        elif analysis_type == AnalysisType.MISSING_EPISODES.value:
            return await self._analyze_missing_episodes(run_id, media_types)

        return 0

    # =========================================================================
    # SPECIFIC ANALYSIS TYPES
    # =========================================================================

    async def _analyze_missing_collections(
        self,
        run_id: str,
        media_types: List[str]
    ) -> int:
        """
        Analyze for missing films in collections/franchises.
        Uses TMDB to get collection info.
        """
        logger.info("Analyzing missing collections...")
        count = 0

        # TODO: Integrate with Plex to get current movies with TMDB IDs
        # For each movie, check if it belongs to a collection
        # If so, check what other movies are in that collection
        # Report missing ones

        # Placeholder implementation
        # plex_movies = await self._get_plex_movies()
        # for movie in plex_movies:
        #     if movie.tmdb_id:
        #         collection_info = await self._get_tmdb_collection(movie.tmdb_id)
        #         if collection_info:
        #             missing = self._find_missing_in_collection(collection_info, plex_movies)
        #             if missing:
        #                 await self._create_result(run_id, AnalysisType.MISSING_COLLECTION, ...)
        #                 count += 1

        return count

    async def _analyze_low_quality(
        self,
        run_id: str,
        media_types: List[str]
    ) -> int:
        """Analyze for low quality content (480p, SD)."""
        logger.info("Analyzing low quality content...")
        count = 0

        # TODO: Integrate with Plex to get media info
        # Check video resolution and flag low quality

        # Example of what would be created:
        # async with AsyncSessionLocal() as session:
        #     result = LibraryAnalysisResult(
        #         analysis_run_id=run_id,
        #         analysis_type=AnalysisType.LOW_QUALITY.value,
        #         severity=Severity.MEDIUM.value,
        #         title="Movie Title",
        #         media_type="movie",
        #         issue_description="Résolution basse (480p) détectée",
        #         recommended_action="Rechercher une version 1080p ou 4K",
        #         current_quality="480p",
        #         recommended_quality="1080p"
        #     )
        #     session.add(result)
        #     await session.commit()
        #     count += 1

        return count

    async def _analyze_bad_codecs(
        self,
        run_id: str,
        media_types: List[str]
    ) -> int:
        """Analyze for bad/outdated codecs (MPEG4, Xvid)."""
        logger.info("Analyzing bad codecs...")
        count = 0

        # TODO: Check video codec and flag outdated ones
        # Flag: MPEG4, Xvid, DivX, MPEG2
        # Recommend: HEVC/x265 for better compression

        return count

    async def _analyze_vostfr_upgradable(
        self,
        run_id: str,
        media_types: List[str]
    ) -> int:
        """Analyze for VOSTFR content that could be upgraded to MULTI."""
        logger.info("Analyzing VOSTFR upgradable content...")
        count = 0

        # TODO: Cross-reference with VOSTFRUpgradeService
        # Check if MULTI versions are available for VOSTFR content

        return count

    async def _analyze_missing_episodes(
        self,
        run_id: str,
        media_types: List[str]
    ) -> int:
        """Analyze series for missing episodes or seasons."""
        logger.info("Analyzing missing episodes...")
        count = 0

        # TODO: For each series in Plex:
        # 1. Get total seasons/episodes from TMDB
        # 2. Compare with what's in Plex
        # 3. Report missing episodes/seasons

        return count

    # =========================================================================
    # RESULT MANAGEMENT
    # =========================================================================

    async def get_run(self, run_id: str) -> Optional[AnalysisRun]:
        """Get an analysis run by ID."""
        async with AsyncSessionLocal() as session:
            return await session.get(AnalysisRun, run_id)

    async def get_all_runs(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> List[AnalysisRun]:
        """Get all analysis runs, most recent first."""
        async with AsyncSessionLocal() as session:
            query = (
                select(AnalysisRun)
                .order_by(AnalysisRun.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_run_results(
        self,
        run_id: str,
        analysis_type: Optional[str] = None,
        severity: Optional[str] = None,
        include_dismissed: bool = False
    ) -> List[LibraryAnalysisResult]:
        """Get results for an analysis run."""
        async with AsyncSessionLocal() as session:
            query = select(LibraryAnalysisResult).where(
                LibraryAnalysisResult.analysis_run_id == run_id
            )

            if analysis_type:
                query = query.where(LibraryAnalysisResult.analysis_type == analysis_type)
            if severity:
                query = query.where(LibraryAnalysisResult.severity == severity)
            if not include_dismissed:
                query = query.where(LibraryAnalysisResult.is_dismissed.is_(False))

            query = query.order_by(
                LibraryAnalysisResult.severity.desc(),
                LibraryAnalysisResult.created_at.desc()
            )

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_latest_results(
        self,
        analysis_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50
    ) -> List[LibraryAnalysisResult]:
        """Get latest analysis results across all runs."""
        async with AsyncSessionLocal() as session:
            query = select(LibraryAnalysisResult).where(
                LibraryAnalysisResult.is_dismissed.is_(False)
            )

            if analysis_type:
                query = query.where(LibraryAnalysisResult.analysis_type == analysis_type)
            if severity:
                query = query.where(LibraryAnalysisResult.severity == severity)

            query = query.order_by(
                LibraryAnalysisResult.created_at.desc()
            ).limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def dismiss_result(
        self,
        result_id: int,
        user_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """Dismiss an analysis result."""
        async with AsyncSessionLocal() as session:
            result = await session.get(LibraryAnalysisResult, result_id)
            if not result:
                return False

            result.is_dismissed = True
            result.dismissed_by_user_id = user_id
            result.dismissed_at = datetime.utcnow()
            result.dismiss_reason = reason

            await session.commit()

            logger.info(f"Dismissed analysis result: {result_id}")
            return True

    async def action_result(
        self,
        result_id: int,
        request_id: int
    ) -> bool:
        """Mark a result as actioned (media request created)."""
        async with AsyncSessionLocal() as session:
            result = await session.get(LibraryAnalysisResult, result_id)
            if not result:
                return False

            result.is_actioned = True
            result.actioned_request_id = request_id
            result.actioned_at = datetime.utcnow()

            await session.commit()

            logger.info(f"Actioned analysis result: {result_id} -> request {request_id}")
            return True

    # =========================================================================
    # STATISTICS
    # =========================================================================

    async def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics across all analyses."""
        async with AsyncSessionLocal() as session:
            # Get latest completed run
            latest_run_query = (
                select(AnalysisRun)
                .where(AnalysisRun.status == AnalysisRunStatus.COMPLETED.value)
                .order_by(AnalysisRun.completed_at.desc())
                .limit(1)
            )
            result = await session.execute(latest_run_query)
            latest_run = result.scalar_one_or_none()

            # Get open issues (not dismissed, not actioned)
            open_issues_query = (
                select(LibraryAnalysisResult)
                .where(
                    and_(
                        LibraryAnalysisResult.is_dismissed.is_(False),
                        LibraryAnalysisResult.is_actioned.is_(False)
                    )
                )
            )
            result = await session.execute(open_issues_query)
            open_issues = list(result.scalars().all())

            # Count by type
            by_type = {}
            by_severity = {}
            for issue in open_issues:
                by_type[issue.analysis_type] = by_type.get(issue.analysis_type, 0) + 1
                by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1

            return {
                "total_open_issues": len(open_issues),
                "by_type": by_type,
                "by_severity": by_severity,
                "high_severity_count": by_severity.get(Severity.HIGH.value, 0),
                "last_analysis": {
                    "id": latest_run.id if latest_run else None,
                    "completed_at": latest_run.completed_at.isoformat() if latest_run else None,
                    "issues_found": latest_run.issues_found if latest_run else 0
                } if latest_run else None
            }

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    async def _send_analysis_complete_notification(
        self,
        run_id: str,
        issues_found: int,
        issues_by_severity: Dict[str, int]
    ) -> bool:
        """Send notification when analysis is complete."""
        discord_config = await self._config_service.get_service_config("discord")

        if not discord_config or not discord_config.url or not discord_config.is_enabled:
            return False

        high = issues_by_severity.get(Severity.HIGH.value, 0)
        medium = issues_by_severity.get(Severity.MEDIUM.value, 0)
        low = issues_by_severity.get(Severity.LOW.value, 0)

        color = 0x2ecc71  # Green
        if high > 0:
            color = 0xe74c3c  # Red
        elif medium > 0:
            color = 0xf39c12  # Orange

        description = f"""Analyse de la bibliothèque terminée.

**{issues_found}** problèmes détectés:
- 🔴 Haute priorité: {high}
- 🟠 Priorité moyenne: {medium}
- 🟢 Basse priorité: {low}

[Voir les résultats](/admin?tab=analysis&run={run_id[:8]})"""

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                payload = {
                    "embeds": [{
                        "title": "📊 Analyse de bibliothèque terminée",
                        "description": description,
                        "color": color,
                        "timestamp": datetime.utcnow().isoformat(),
                        "footer": {"text": "Plex Kiosk - Library Analysis"}
                    }],
                    "username": "Plex Kiosk"
                }

                response = await client.post(discord_config.url, json=payload)
                response.raise_for_status()
                return True

        except Exception as e:
            logger.error(f"Failed to send analysis notification: {e}")
            return False


# Singleton instance
_library_analysis_service: Optional[LibraryAnalysisService] = None


def get_library_analysis_service() -> LibraryAnalysisService:
    """Get library analysis service instance (singleton)."""
    global _library_analysis_service
    if _library_analysis_service is None:
        _library_analysis_service = LibraryAnalysisService()
    return _library_analysis_service
