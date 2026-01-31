"""
Release Monitor Service for automatic series tracking.
Similar to Sonarr, monitors series for new episode releases and triggers downloads.

Key features:
- Add series to monitoring from TMDB/AniList
- Fetch episode release schedules
- Search for torrents when episodes air
- Send Discord notifications with approval links
- Track download status
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import httpx
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from ..models.database import AsyncSessionLocal
from ..models.monitored_series import (
    MonitoredSeries,
    MonitorType,
    AudioPreference,
    QualityPreference,
    MonitoringStatus
)
from ..models.episode_schedule import EpisodeReleaseSchedule, EpisodeStatus
from .service_config_service import get_service_config_service
from .notifications import NotificationService

logger = logging.getLogger(__name__)


class ReleaseMonitorService:
    """
    Service for monitoring series releases and triggering automatic downloads.

    Workflow:
    1. User adds a series to monitoring (from TMDB/AniList)
    2. Service fetches episode schedule from TMDB
    3. When an episode airs, service searches for torrents
    4. When torrent found, sends Discord notification with approval link
    5. Admin approves → download starts
    6. Download completes → notification sent
    """

    TMDB_BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._config_service = get_service_config_service()
        self._notification_service = NotificationService()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get_tmdb_api_key(self) -> Optional[str]:
        """Get TMDB API key from database config."""
        config = await self._config_service.get_service_config("tmdb")
        if config and config.api_key_encrypted:
            return await self._config_service.get_decrypted_value("tmdb", "api_key")
        return None

    async def _get_discord_config(self) -> Dict[str, Any]:
        """Get Discord configuration from database."""
        config = await self._config_service.get_service_config("discord")
        if config and config.url:
            return {
                "webhook_url": config.url,
                "is_enabled": config.is_enabled
            }
        return {"webhook_url": None, "is_enabled": False}

    # =========================================================================
    # SERIES MANAGEMENT
    # =========================================================================

    async def add_series(
        self,
        tmdb_id: Optional[str] = None,
        anilist_id: Optional[str] = None,
        title: str = "",
        original_title: Optional[str] = None,
        year: Optional[int] = None,
        media_type: str = "series",
        poster_url: Optional[str] = None,
        backdrop_url: Optional[str] = None,
        monitor_type: str = MonitorType.NEW_EPISODES.value,
        quality_preference: str = QualityPreference.FHD_1080P.value,
        audio_preference: str = AudioPreference.MULTI.value,
        user_id: Optional[int] = None
    ) -> MonitoredSeries:
        """
        Add a series to monitoring.

        Args:
            tmdb_id: TMDB series ID
            anilist_id: AniList anime ID
            title: Series title
            original_title: Original title
            year: First air year
            media_type: "series" or "anime"
            poster_url: Poster image URL
            backdrop_url: Backdrop image URL
            monitor_type: Type of monitoring (new_episodes, vostfr_upgrade, both)
            quality_preference: Quality preference (4k, 1080p, 720p, any)
            audio_preference: Audio preference (multi, vf, vostfr, any)
            user_id: ID of user who added the series

        Returns:
            Created MonitoredSeries object
        """
        async with AsyncSessionLocal() as session:
            # Check if already monitoring
            existing = await session.execute(
                select(MonitoredSeries).where(
                    or_(
                        and_(MonitoredSeries.tmdb_id == tmdb_id, tmdb_id is not None),
                        and_(MonitoredSeries.anilist_id == anilist_id, anilist_id is not None)
                    )
                )
            )
            existing_series = existing.scalar_one_or_none()

            if existing_series:
                logger.info(f"Series already monitored: {title}")
                return existing_series

            # Fetch additional info from TMDB if available
            total_seasons = None
            if tmdb_id:
                series_info = await self._fetch_tmdb_series_info(tmdb_id)
                if series_info:
                    total_seasons = series_info.get("number_of_seasons")
                    if not title:
                        title = series_info.get("name", title)
                    if not poster_url and series_info.get("poster_path"):
                        poster_url = f"https://image.tmdb.org/t/p/w500{series_info['poster_path']}"
                    if not backdrop_url and series_info.get("backdrop_path"):
                        backdrop_url = f"https://image.tmdb.org/t/p/original{series_info['backdrop_path']}"

            # Create monitored series
            series = MonitoredSeries(
                tmdb_id=tmdb_id,
                anilist_id=anilist_id,
                title=title,
                original_title=original_title,
                year=year,
                media_type=media_type,
                poster_url=poster_url,
                backdrop_url=backdrop_url,
                monitor_type=monitor_type,
                quality_preference=quality_preference,
                audio_preference=audio_preference,
                status=MonitoringStatus.ACTIVE.value,
                total_seasons=total_seasons,
                added_by_user_id=user_id
            )

            session.add(series)
            await session.commit()
            await session.refresh(series)

            logger.info(f"Added series to monitoring: {title} (ID: {series.id})")

            # Fetch episode schedule
            if tmdb_id:
                await self.refresh_episode_schedule(series.id)

            # Send notification
            await self._send_discord_notification(
                title="📺 Nouvelle série suivie",
                description=f"**{title}**\n\nType de monitoring: {monitor_type}",
                color=0x3498db,  # Blue
                thumbnail=poster_url
            )

            return series

    async def remove_series(self, series_id: int) -> bool:
        """Remove a series from monitoring."""
        async with AsyncSessionLocal() as session:
            series = await session.get(MonitoredSeries, series_id)
            if not series:
                return False

            title = series.title
            await session.delete(series)
            await session.commit()

            logger.info(f"Removed series from monitoring: {title}")
            return True

    async def update_series(
        self,
        series_id: int,
        **kwargs
    ) -> Optional[MonitoredSeries]:
        """Update series monitoring settings."""
        async with AsyncSessionLocal() as session:
            series = await session.get(MonitoredSeries, series_id)
            if not series:
                return None

            # Update allowed fields
            allowed_fields = [
                "monitor_type", "quality_preference", "audio_preference",
                "status", "current_season", "current_episode"
            ]

            for field, value in kwargs.items():
                if field in allowed_fields and value is not None:
                    setattr(series, field, value)

            await session.commit()
            await session.refresh(series)

            logger.info(f"Updated series: {series.title}")
            return series

    async def pause_series(self, series_id: int) -> bool:
        """Pause monitoring for a series."""
        series = await self.update_series(series_id, status=MonitoringStatus.PAUSED.value)
        return series is not None

    async def resume_series(self, series_id: int) -> bool:
        """Resume monitoring for a series."""
        series = await self.update_series(series_id, status=MonitoringStatus.ACTIVE.value)
        return series is not None

    async def get_all_series(
        self,
        status: Optional[str] = None,
        include_episodes: bool = False
    ) -> List[MonitoredSeries]:
        """Get all monitored series."""
        async with AsyncSessionLocal() as session:
            query = select(MonitoredSeries)

            if status:
                query = query.where(MonitoredSeries.status == status)

            if include_episodes:
                query = query.options(selectinload(MonitoredSeries.episode_schedules))

            query = query.order_by(MonitoredSeries.title)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_series(self, series_id: int) -> Optional[MonitoredSeries]:
        """Get a single monitored series."""
        async with AsyncSessionLocal() as session:
            return await session.get(MonitoredSeries, series_id)

    # =========================================================================
    # EPISODE SCHEDULE
    # =========================================================================

    async def refresh_episode_schedule(self, series_id: int) -> int:
        """
        Fetch and update episode schedule from TMDB.

        Returns:
            Number of episodes added/updated
        """
        async with AsyncSessionLocal() as session:
            series = await session.get(MonitoredSeries, series_id)
            if not series or not series.tmdb_id:
                return 0

            api_key = await self._get_tmdb_api_key()
            if not api_key:
                logger.warning("TMDB API key not configured")
                return 0

            count = 0
            total_seasons = series.total_seasons or 1

            # Fetch all seasons
            for season_num in range(1, total_seasons + 1):
                try:
                    response = await self.client.get(
                        f"{self.TMDB_BASE_URL}/tv/{series.tmdb_id}/season/{season_num}",
                        params={
                            "api_key": api_key,
                            "language": "fr-FR"
                        }
                    )

                    if response.status_code != 200:
                        continue

                    season_data = response.json()
                    episodes = season_data.get("episodes", [])

                    for ep in episodes:
                        air_date_str = ep.get("air_date")
                        if not air_date_str:
                            continue

                        air_date = datetime.strptime(air_date_str, "%Y-%m-%d")
                        episode_num = ep.get("episode_number", 0)

                        # Check if episode already exists
                        existing = await session.execute(
                            select(EpisodeReleaseSchedule).where(
                                and_(
                                    EpisodeReleaseSchedule.monitored_series_id == series_id,
                                    EpisodeReleaseSchedule.season == season_num,
                                    EpisodeReleaseSchedule.episode == episode_num
                                )
                            )
                        )
                        existing_ep = existing.scalar_one_or_none()

                        if existing_ep:
                            # Update air date if changed
                            if existing_ep.air_date != air_date:
                                existing_ep.air_date = air_date
                                existing_ep.episode_title = ep.get("name")
                                existing_ep.episode_overview = ep.get("overview")
                        else:
                            # Create new episode entry
                            status = EpisodeStatus.UPCOMING.value
                            if air_date <= datetime.utcnow():
                                status = EpisodeStatus.AIRED.value

                            new_episode = EpisodeReleaseSchedule(
                                monitored_series_id=series_id,
                                season=season_num,
                                episode=episode_num,
                                episode_title=ep.get("name"),
                                episode_overview=ep.get("overview"),
                                tmdb_episode_id=str(ep.get("id")),
                                air_date=air_date,
                                air_date_source="tmdb",
                                status=status
                            )
                            session.add(new_episode)
                            count += 1

                except Exception as e:
                    logger.error(f"Error fetching season {season_num} for {series.title}: {e}")

            # Update series last check
            series.last_checked_at = datetime.utcnow()

            await session.commit()

            logger.info(f"Updated episode schedule for {series.title}: {count} new episodes")
            return count

    async def get_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days_ahead: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Get calendar of upcoming and recent episodes.

        Args:
            start_date: Start of date range (default: today - 7 days)
            end_date: End of date range (default: today + days_ahead)
            days_ahead: Number of days to look ahead (default: 14)

        Returns:
            List of episodes with series info
        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=7)
        if not end_date:
            end_date = datetime.utcnow() + timedelta(days=days_ahead)

        async with AsyncSessionLocal() as session:
            query = (
                select(EpisodeReleaseSchedule)
                .options(selectinload(EpisodeReleaseSchedule.monitored_series))
                .where(
                    and_(
                        EpisodeReleaseSchedule.air_date >= start_date,
                        EpisodeReleaseSchedule.air_date <= end_date
                    )
                )
                .order_by(EpisodeReleaseSchedule.air_date)
            )

            result = await session.execute(query)
            episodes = result.scalars().all()

            calendar = []
            for ep in episodes:
                series = ep.monitored_series
                calendar.append({
                    "id": ep.id,
                    "series_id": series.id,
                    "series_title": series.title,
                    "series_poster": series.poster_url,
                    "season": ep.season,
                    "episode": ep.episode,
                    "episode_code": ep.episode_code,
                    "episode_title": ep.episode_title,
                    "air_date": ep.air_date.isoformat(),
                    "is_aired": ep.is_aired,
                    "status": ep.status,
                    "found_torrent_name": ep.found_torrent_name
                })

            return calendar

    async def get_pending_episodes(self) -> List[EpisodeReleaseSchedule]:
        """Get episodes waiting for approval."""
        async with AsyncSessionLocal() as session:
            query = (
                select(EpisodeReleaseSchedule)
                .options(selectinload(EpisodeReleaseSchedule.monitored_series))
                .where(
                    EpisodeReleaseSchedule.status == EpisodeStatus.PENDING_APPROVAL.value
                )
                .order_by(EpisodeReleaseSchedule.air_date)
            )

            result = await session.execute(query)
            return list(result.scalars().all())

    # =========================================================================
    # EPISODE ACTIONS
    # =========================================================================

    async def approve_episode(
        self,
        episode_id: int,
        user_id: int
    ) -> bool:
        """
        Approve an episode for download.

        Args:
            episode_id: Episode schedule ID
            user_id: ID of user approving

        Returns:
            True if approved successfully
        """
        async with AsyncSessionLocal() as session:
            episode = await session.get(EpisodeReleaseSchedule, episode_id)
            if not episode:
                return False

            if episode.status != EpisodeStatus.PENDING_APPROVAL.value:
                logger.warning(f"Episode {episode_id} not pending approval (status: {episode.status})")
                return False

            episode.status = EpisodeStatus.APPROVED.value
            episode.approved_by_user_id = user_id
            episode.approved_at = datetime.utcnow()

            await session.commit()

            logger.info(f"Episode approved: {episode.episode_code}")

            # TODO: Trigger download here
            # This would integrate with the download service

            return True

    async def skip_episode(self, episode_id: int) -> bool:
        """Skip an episode (won't be downloaded)."""
        async with AsyncSessionLocal() as session:
            episode = await session.get(EpisodeReleaseSchedule, episode_id)
            if not episode:
                return False

            episode.status = EpisodeStatus.SKIPPED.value
            await session.commit()

            logger.info(f"Episode skipped: {episode.episode_code}")
            return True

    async def retry_episode_search(self, episode_id: int) -> bool:
        """Retry searching for an episode's torrent."""
        async with AsyncSessionLocal() as session:
            episode = await session.get(EpisodeReleaseSchedule, episode_id)
            if not episode:
                return False

            episode.status = EpisodeStatus.AIRED.value
            episode.next_search_at = datetime.utcnow()
            await session.commit()

            logger.info(f"Episode search retry scheduled: {episode.episode_code}")
            return True

    # =========================================================================
    # MONITORING TASKS (called by scheduler)
    # =========================================================================

    async def check_for_new_episodes(self) -> Dict[str, Any]:
        """
        Check all monitored series for new episodes.
        Called periodically by the scheduler.

        Returns:
            Summary of actions taken
        """
        logger.info("Starting new episode check...")

        results = {
            "series_checked": 0,
            "episodes_found": 0,
            "torrents_found": 0,
            "notifications_sent": 0,
            "errors": []
        }

        # Get all active series
        series_list = await self.get_all_series(status=MonitoringStatus.ACTIVE.value)
        results["series_checked"] = len(series_list)

        for series in series_list:
            try:
                # Refresh episode schedule if needed (not checked in last 24h)
                if not series.last_checked_at or \
                   series.last_checked_at < datetime.utcnow() - timedelta(hours=24):
                    await self.refresh_episode_schedule(series.id)

                # Check for aired episodes that need searching
                async with AsyncSessionLocal() as session:
                    query = (
                        select(EpisodeReleaseSchedule)
                        .where(
                            and_(
                                EpisodeReleaseSchedule.monitored_series_id == series.id,
                                EpisodeReleaseSchedule.status.in_([
                                    EpisodeStatus.AIRED.value,
                                    EpisodeStatus.NOT_FOUND.value
                                ]),
                                EpisodeReleaseSchedule.air_date <= datetime.utcnow()
                            )
                        )
                    )

                    result = await session.execute(query)
                    episodes = list(result.scalars().all())

                    for episode in episodes:
                        results["episodes_found"] += 1

                        # Search for torrent (placeholder - would integrate with torrent search)
                        torrent_found = await self._search_episode_torrent(series, episode)

                        if torrent_found:
                            results["torrents_found"] += 1
                            results["notifications_sent"] += 1

            except Exception as e:
                error_msg = f"Error checking {series.title}: {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

        logger.info(f"Episode check complete: {results}")
        return results

    async def update_aired_episodes(self) -> int:
        """
        Update status of episodes that have aired.
        Called periodically by the scheduler.

        Returns:
            Number of episodes updated
        """
        async with AsyncSessionLocal() as session:
            # Find episodes that were upcoming but have now aired
            query = (
                select(EpisodeReleaseSchedule)
                .where(
                    and_(
                        EpisodeReleaseSchedule.status == EpisodeStatus.UPCOMING.value,
                        EpisodeReleaseSchedule.air_date <= datetime.utcnow()
                    )
                )
            )

            result = await session.execute(query)
            episodes = list(result.scalars().all())

            for episode in episodes:
                episode.status = EpisodeStatus.AIRED.value

            await session.commit()

            if episodes:
                logger.info(f"Updated {len(episodes)} episodes to AIRED status")

            return len(episodes)

    # =========================================================================
    # TORRENT SEARCH
    # =========================================================================

    async def _search_episode_torrent(
        self,
        series: MonitoredSeries,
        episode: EpisodeReleaseSchedule
    ) -> bool:
        """
        Search for a torrent for an episode.

        Args:
            series: The monitored series
            episode: The episode to search for

        Returns:
            True if torrent found and notification sent
        """
        # Update search tracking
        async with AsyncSessionLocal() as session:
            ep = await session.get(EpisodeReleaseSchedule, episode.id)
            if not ep:
                return False

            ep.status = EpisodeStatus.SEARCHING.value
            ep.search_attempts += 1
            ep.last_search_at = datetime.utcnow()
            await session.commit()

        # Build search query
        search_terms = [
            f"{series.title} {episode.episode_code}",
            f"{series.title} S{episode.season:02d}E{episode.episode:02d}",
        ]

        if series.original_title:
            search_terms.append(f"{series.original_title} {episode.episode_code}")

        # TODO: Integrate with actual torrent search service
        # This is a placeholder - would use YGG/torrent search service
        logger.info(f"Searching for: {search_terms[0]}")

        # Simulate search (replace with actual implementation)
        # torrent = await self._ygg_search(search_terms, series.quality_preference, series.audio_preference)

        torrent = None  # Placeholder

        if torrent:
            async with AsyncSessionLocal() as session:
                ep = await session.get(EpisodeReleaseSchedule, episode.id)
                if ep:
                    ep.status = EpisodeStatus.PENDING_APPROVAL.value
                    ep.found_torrent_name = torrent.get("name")
                    ep.found_torrent_url = torrent.get("url")
                    ep.found_torrent_size = torrent.get("size")
                    ep.found_torrent_seeders = torrent.get("seeders")
                    ep.found_torrent_quality = torrent.get("quality")
                    ep.found_torrent_audio = torrent.get("audio")
                    ep.torrent_found_at = datetime.utcnow()
                    await session.commit()

            # Send notification
            await self._send_episode_found_notification(series, episode, torrent)
            return True

        else:
            async with AsyncSessionLocal() as session:
                ep = await session.get(EpisodeReleaseSchedule, episode.id)
                if ep:
                    ep.status = EpisodeStatus.NOT_FOUND.value
                    ep.status_message = f"Torrent non trouvé (tentative {ep.search_attempts})"
                    # Schedule next search in 6 hours
                    ep.next_search_at = datetime.utcnow() + timedelta(hours=6)
                    await session.commit()

            return False

    # =========================================================================
    # TMDB API
    # =========================================================================

    async def _fetch_tmdb_series_info(self, tmdb_id: str) -> Optional[Dict[str, Any]]:
        """Fetch series info from TMDB."""
        api_key = await self._get_tmdb_api_key()
        if not api_key:
            return None

        try:
            response = await self.client.get(
                f"{self.TMDB_BASE_URL}/tv/{tmdb_id}",
                params={
                    "api_key": api_key,
                    "language": "fr-FR"
                }
            )

            if response.status_code == 200:
                return response.json()

        except Exception as e:
            logger.error(f"Error fetching TMDB series info: {e}")

        return None

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    async def _send_discord_notification(
        self,
        title: str,
        description: str,
        color: int = 0x3498db,
        thumbnail: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Send a Discord notification."""
        discord_config = await self._get_discord_config()

        if not discord_config.get("webhook_url") or not discord_config.get("is_enabled"):
            logger.debug("Discord notifications not configured or disabled")
            return False

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat()
        }

        if thumbnail:
            embed["thumbnail"] = {"url": thumbnail}

        if fields:
            embed["fields"] = fields

        embed["footer"] = {"text": "Plex Kiosk Monitoring"}

        payload = {
            "embeds": [embed],
            "username": "Plex Kiosk"
        }

        try:
            response = await self.client.post(
                discord_config["webhook_url"],
                json=payload
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False

    async def _send_episode_found_notification(
        self,
        series: MonitoredSeries,
        episode: EpisodeReleaseSchedule,
        torrent: Dict[str, Any]
    ) -> bool:
        """Send notification when a torrent is found for an episode."""
        # Build approval URL (would be actual admin panel URL)
        approval_url = f"/admin/monitoring/approve/{episode.id}"

        description = f"""**{series.title}** - {episode.episode_code}
{episode.episode_title or ''}

**Torrent trouvé:**
{torrent.get('name', 'N/A')[:100]}

Qualité: {torrent.get('quality', 'N/A')} | Audio: {torrent.get('audio', 'N/A')}
Taille: {torrent.get('size', 'N/A')} | Seeders: {torrent.get('seeders', 0)}

[Approuver le téléchargement]({approval_url})"""

        return await self._send_discord_notification(
            title="🎬 Nouvel épisode disponible",
            description=description,
            color=0x2ecc71,  # Green
            thumbnail=series.poster_url,
            fields=[
                {"name": "Série", "value": series.title, "inline": True},
                {"name": "Épisode", "value": episode.episode_code, "inline": True}
            ]
        )


# Singleton instance
_release_monitor_service: Optional[ReleaseMonitorService] = None


def get_release_monitor_service() -> ReleaseMonitorService:
    """Get release monitor service instance (singleton)."""
    global _release_monitor_service
    if _release_monitor_service is None:
        _release_monitor_service = ReleaseMonitorService()
    return _release_monitor_service
