"""
VOSTFR Upgrade Service for automatic replacement of VOSTFR content with MULTI versions.

Scans Plex library for VOSTFR-only content and searches for MULTI replacements.
Supports movies, series, and anime.
"""
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import select, and_

from ..models.database import AsyncSessionLocal
from ..models.upgrade_candidate import UpgradeCandidate, UpgradeStatus
from .service_config_service import get_service_config_service
from .notifications import NotificationService

logger = logging.getLogger(__name__)


class VOSTFRUpgradeService:
    """
    Service for detecting and upgrading VOSTFR content to MULTI versions.

    Workflow:
    1. Scan Plex library for VOSTFR-only content
    2. Create upgrade candidates for each VOSTFR item
    3. Periodically search for MULTI versions on torrent sites
    4. When found, notify admin and wait for approval
    5. Download MULTI version
    6. Replace original file and update Plex
    """

    # Audio type detection patterns
    VOSTFR_PATTERNS = [
        r'vostfr',
        r'vost',
        r'subfrench',
        r'french\.sub',
        r'fr\.sub',
    ]

    MULTI_PATTERNS = [
        r'multi',
        r'truefrench',
        r'french',
        r'vff',
        r'vf2',
    ]

    def __init__(self):
        self._config_service = get_service_config_service()
        self._notification_service = NotificationService()

    async def _get_plex_config(self) -> Dict[str, Any]:
        """Get Plex configuration from database."""
        config = await self._config_service.get_service_config("plex")
        if not config:
            return {}

        return {
            "url": config.url,
            "token": await self._config_service.get_decrypted_value("plex", "token"),
            "is_enabled": config.is_enabled
        }

    # =========================================================================
    # LIBRARY SCANNING
    # =========================================================================

    async def scan_library_for_vostfr(
        self,
        library_sections: Optional[List[str]] = None,
        media_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Scan Plex library for VOSTFR-only content.

        Args:
            library_sections: Specific library sections to scan (None = all)
            media_types: Filter by media type (movie, series, anime)

        Returns:
            Scan results with counts and new candidates
        """
        logger.info("Starting VOSTFR library scan...")

        results = {
            "total_scanned": 0,
            "vostfr_found": 0,
            "new_candidates": 0,
            "already_tracked": 0,
            "errors": []
        }

        plex_config = await self._get_plex_config()
        if not plex_config.get("url") or not plex_config.get("is_enabled"):
            logger.warning("Plex not configured or disabled")
            return results

        try:
            # Get all media from Plex (this would integrate with Plex API)
            # For now, this is a placeholder - actual implementation would use plexapi
            media_items = await self._get_plex_media_items(plex_config, library_sections)

            for item in media_items:
                results["total_scanned"] += 1

                # Detect audio type from filename
                audio_type = self._detect_audio_type(item.get("file_path", ""))

                if audio_type in ["vostfr", "vost"]:
                    results["vostfr_found"] += 1

                    # Check if already tracked
                    existing = await self._get_existing_candidate(item.get("file_path"))

                    if existing:
                        results["already_tracked"] += 1
                    else:
                        # Create new candidate
                        await self._create_upgrade_candidate(item, audio_type)
                        results["new_candidates"] += 1

        except Exception as e:
            error_msg = f"Error during scan: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)

        logger.info(f"VOSTFR scan complete: {results}")
        return results

    async def _get_plex_media_items(
        self,
        plex_config: Dict[str, Any],
        library_sections: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get media items from Plex library.

        This is a placeholder - actual implementation would use plexapi library.
        """
        # TODO: Integrate with actual Plex API
        # from plexapi.server import PlexServer
        # plex = PlexServer(plex_config["url"], plex_config["token"])
        # ...

        logger.info("Fetching media items from Plex...")
        return []

    async def _get_existing_candidate(self, file_path: str) -> Optional[UpgradeCandidate]:
        """Check if a file is already tracked as an upgrade candidate."""
        async with AsyncSessionLocal() as session:
            query = select(UpgradeCandidate).where(
                UpgradeCandidate.current_file_path == file_path
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def _create_upgrade_candidate(
        self,
        item: Dict[str, Any],
        audio_type: str
    ) -> UpgradeCandidate:
        """Create a new upgrade candidate from a Plex item."""
        async with AsyncSessionLocal() as session:
            candidate = UpgradeCandidate(
                plex_rating_key=item.get("rating_key"),
                current_file_path=item.get("file_path"),
                current_audio_type=audio_type,
                current_quality=item.get("quality"),
                current_codec=item.get("codec"),
                title=item.get("title"),
                tmdb_id=item.get("tmdb_id"),
                year=item.get("year"),
                media_type=item.get("media_type", "series"),
                season=item.get("season"),
                episode=item.get("episode"),
                episode_title=item.get("episode_title"),
                status=UpgradeStatus.PENDING.value
            )

            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)

            logger.info(f"Created upgrade candidate: {candidate.title}")
            return candidate

    def _detect_audio_type(self, filename: str) -> str:
        """Detect audio type from filename."""
        filename_lower = filename.lower()

        # Check for MULTI first (takes priority)
        for pattern in self.MULTI_PATTERNS:
            if re.search(pattern, filename_lower):
                return "multi"

        # Check for VOSTFR
        for pattern in self.VOSTFR_PATTERNS:
            if re.search(pattern, filename_lower):
                return "vostfr"

        # Default to unknown
        return "unknown"

    # =========================================================================
    # UPGRADE MANAGEMENT
    # =========================================================================

    async def get_all_candidates(
        self,
        status: Optional[str] = None,
        media_type: Optional[str] = None
    ) -> List[UpgradeCandidate]:
        """Get all upgrade candidates with optional filters."""
        async with AsyncSessionLocal() as session:
            query = select(UpgradeCandidate)

            conditions = []
            if status:
                conditions.append(UpgradeCandidate.status == status)
            if media_type:
                conditions.append(UpgradeCandidate.media_type == media_type)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(UpgradeCandidate.created_at.desc())

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_candidate(self, candidate_id: int) -> Optional[UpgradeCandidate]:
        """Get a single upgrade candidate."""
        async with AsyncSessionLocal() as session:
            return await session.get(UpgradeCandidate, candidate_id)

    async def get_pending_candidates(self) -> List[UpgradeCandidate]:
        """Get candidates pending approval (MULTI found)."""
        return await self.get_all_candidates(status=UpgradeStatus.FOUND.value)

    async def approve_upgrade(self, candidate_id: int) -> bool:
        """Approve an upgrade for download."""
        async with AsyncSessionLocal() as session:
            candidate = await session.get(UpgradeCandidate, candidate_id)
            if not candidate:
                return False

            if candidate.status != UpgradeStatus.FOUND.value:
                logger.warning(f"Candidate {candidate_id} not in FOUND status")
                return False

            candidate.status = UpgradeStatus.APPROVED.value
            await session.commit()

            logger.info(f"Approved upgrade: {candidate.title}")

            # TODO: Trigger download here
            # await self._start_upgrade_download(candidate)

            return True

    async def skip_upgrade(self, candidate_id: int) -> bool:
        """Skip an upgrade candidate."""
        async with AsyncSessionLocal() as session:
            candidate = await session.get(UpgradeCandidate, candidate_id)
            if not candidate:
                return False

            candidate.status = UpgradeStatus.SKIPPED.value
            await session.commit()

            logger.info(f"Skipped upgrade: {candidate.title}")
            return True

    async def retry_search(self, candidate_id: int) -> bool:
        """Retry searching for MULTI version."""
        async with AsyncSessionLocal() as session:
            candidate = await session.get(UpgradeCandidate, candidate_id)
            if not candidate:
                return False

            candidate.status = UpgradeStatus.PENDING.value
            candidate.status_message = None
            await session.commit()

            logger.info(f"Retrying search for: {candidate.title}")
            return True

    async def delete_candidate(self, candidate_id: int) -> bool:
        """Delete an upgrade candidate."""
        async with AsyncSessionLocal() as session:
            candidate = await session.get(UpgradeCandidate, candidate_id)
            if not candidate:
                return False

            await session.delete(candidate)
            await session.commit()

            logger.info(f"Deleted candidate: {candidate.title}")
            return True

    # =========================================================================
    # UPGRADE SEARCH (called by scheduler)
    # =========================================================================

    async def search_for_upgrades(self) -> Dict[str, Any]:
        """
        Search for MULTI versions for all pending candidates.
        Called periodically by the scheduler.

        Returns:
            Summary of search results
        """
        logger.info("Starting upgrade search...")

        results = {
            "candidates_checked": 0,
            "upgrades_found": 0,
            "notifications_sent": 0,
            "errors": []
        }

        # Get pending candidates
        candidates = await self.get_all_candidates(status=UpgradeStatus.PENDING.value)
        results["candidates_checked"] = len(candidates)

        for candidate in candidates:
            try:
                # Update status
                async with AsyncSessionLocal() as session:
                    c = await session.get(UpgradeCandidate, candidate.id)
                    if c:
                        c.status = UpgradeStatus.SEARCHING.value
                        c.checked_at = datetime.utcnow()
                        await session.commit()

                # Search for MULTI version
                torrent = await self._search_multi_torrent(candidate)

                if torrent:
                    # Update candidate with found torrent
                    async with AsyncSessionLocal() as session:
                        c = await session.get(UpgradeCandidate, candidate.id)
                        if c:
                            c.status = UpgradeStatus.FOUND.value
                            c.upgrade_torrent_name = torrent.get("name")
                            c.upgrade_torrent_url = torrent.get("url")
                            c.upgrade_torrent_size = torrent.get("size")
                            c.upgrade_torrent_seeders = torrent.get("seeders")
                            c.upgrade_quality = torrent.get("quality")
                            c.upgrade_found_at = datetime.utcnow()
                            await session.commit()

                    results["upgrades_found"] += 1

                    # Send notification
                    await self._send_upgrade_found_notification(candidate, torrent)
                    results["notifications_sent"] += 1

                else:
                    # No upgrade found
                    async with AsyncSessionLocal() as session:
                        c = await session.get(UpgradeCandidate, candidate.id)
                        if c:
                            c.status = UpgradeStatus.NO_UPGRADE.value
                            c.status_message = "Aucune version MULTI trouvée"
                            await session.commit()

            except Exception as e:
                error_msg = f"Error searching for {candidate.title}: {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

                # Mark as pending to retry later
                async with AsyncSessionLocal() as session:
                    c = await session.get(UpgradeCandidate, candidate.id)
                    if c:
                        c.status = UpgradeStatus.PENDING.value
                        c.status_message = str(e)
                        await session.commit()

        logger.info(f"Upgrade search complete: {results}")
        return results

    async def _search_multi_torrent(
        self,
        candidate: UpgradeCandidate
    ) -> Optional[Dict[str, Any]]:
        """
        Search for MULTI version torrent.

        Args:
            candidate: The upgrade candidate to search for

        Returns:
            Torrent info if found, None otherwise
        """
        # Build search query
        search_terms = []

        if candidate.media_type == "movie":
            search_terms.append(f"{candidate.title} {candidate.year or ''} MULTI")
            search_terms.append(f"{candidate.title} {candidate.year or ''} FRENCH")
        else:
            # Series/Anime
            if candidate.season and candidate.episode:
                ep_code = f"S{candidate.season:02d}E{candidate.episode:02d}"
                search_terms.append(f"{candidate.title} {ep_code} MULTI")
                search_terms.append(f"{candidate.title} {ep_code} FRENCH")
            else:
                search_terms.append(f"{candidate.title} MULTI")

        # TODO: Integrate with YGG torrent search service
        logger.info(f"Searching for: {search_terms[0]}")

        # Placeholder - would integrate with actual torrent search
        # torrent = await self._ygg_search(search_terms, candidate.current_quality)

        return None

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    async def _send_upgrade_found_notification(
        self,
        candidate: UpgradeCandidate,
        torrent: Dict[str, Any]
    ) -> bool:
        """Send notification when MULTI version is found."""
        discord_config = await self._config_service.get_service_config("discord")

        if not discord_config or not discord_config.url or not discord_config.is_enabled:
            return False

        # Build approval URL
        approval_url = f"/admin/monitoring/upgrades/approve/{candidate.id}"

        if candidate.season and candidate.episode:
            title_text = f"{candidate.title} S{candidate.season:02d}E{candidate.episode:02d}"
        else:
            title_text = f"{candidate.title} ({candidate.year or ''})"

        description = f"""**{title_text}**

Version actuelle: {candidate.current_audio_type.upper()}
Version trouvée: MULTI

**Torrent:**
{torrent.get('name', 'N/A')[:100]}

Qualité: {torrent.get('quality', 'N/A')} | Taille: {torrent.get('size', 'N/A')}
Seeders: {torrent.get('seeders', 0)}

[Approuver le remplacement]({approval_url})"""

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                payload = {
                    "embeds": [{
                        "title": "🔄 Upgrade MULTI disponible",
                        "description": description,
                        "color": 0x3498db,  # Blue
                        "timestamp": datetime.utcnow().isoformat(),
                        "footer": {"text": "Plex Kiosk - VOSTFR Upgrade"}
                    }],
                    "username": "Plex Kiosk"
                }

                response = await client.post(discord_config.url, json=payload)
                response.raise_for_status()
                return True

        except Exception as e:
            logger.error(f"Failed to send upgrade notification: {e}")
            return False

    # =========================================================================
    # STATISTICS
    # =========================================================================

    async def get_statistics(self) -> Dict[str, Any]:
        """Get upgrade statistics."""
        async with AsyncSessionLocal() as session:
            all_candidates = await session.execute(select(UpgradeCandidate))
            candidates = list(all_candidates.scalars().all())

            by_status = {}
            for c in candidates:
                by_status[c.status] = by_status.get(c.status, 0) + 1

            by_media_type = {}
            for c in candidates:
                by_media_type[c.media_type] = by_media_type.get(c.media_type, 0) + 1

            return {
                "total": len(candidates),
                "by_status": by_status,
                "by_media_type": by_media_type,
                "pending": by_status.get(UpgradeStatus.PENDING.value, 0),
                "found": by_status.get(UpgradeStatus.FOUND.value, 0),
                "completed": by_status.get(UpgradeStatus.COMPLETED.value, 0)
            }


# Singleton instance
_vostfr_upgrade_service: Optional[VOSTFRUpgradeService] = None


def get_vostfr_upgrade_service() -> VOSTFRUpgradeService:
    """Get VOSTFR upgrade service instance (singleton)."""
    global _vostfr_upgrade_service
    if _vostfr_upgrade_service is None:
        _vostfr_upgrade_service = VOSTFRUpgradeService()
    return _vostfr_upgrade_service
