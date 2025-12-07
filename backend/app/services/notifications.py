"""
Notification service for Discord and Plex.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import httpx

from ..config import get_settings
from ..models.request import RequestStatus

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Multi-channel notification service:
    - Discord webhooks
    - Plex (via library update)
    """
    
    # Discord embed colors
    COLORS = {
        "info": 0x3498db,      # Blue
        "success": 0x2ecc71,   # Green
        "warning": 0xf39c12,   # Orange
        "error": 0xe74c3c,     # Red
        "pending": 0x9b59b6    # Purple
    }
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    # =========================================================================
    # HIGH-LEVEL NOTIFICATION EVENTS
    # =========================================================================
    
    async def notify_request_created(
        self,
        title: str,
        media_type: str,
        username: str,
        poster_url: Optional[str] = None
    ):
        """Notify when a new request is created."""
        await self._send_discord(
            title="📥 Nouvelle demande",
            description=f"**{title}**\n\nDemandé par **{username}**",
            color=self.COLORS["info"],
            fields=[
                {"name": "Type", "value": media_type.replace("_", " ").title(), "inline": True}
            ],
            thumbnail=poster_url
        )
    
    async def notify_download_started(
        self,
        title: str,
        media_type: str,
        torrent_name: str,
        size: str
    ):
        """Notify when a download starts."""
        await self._send_discord(
            title="⬇️ Téléchargement démarré",
            description=f"**{title}**",
            color=self.COLORS["pending"],
            fields=[
                {"name": "Torrent", "value": torrent_name[:100], "inline": False},
                {"name": "Taille", "value": size, "inline": True}
            ]
        )
    
    async def notify_download_complete(
        self,
        title: str,
        media_type: str,
        poster_url: Optional[str] = None
    ):
        """Notify when a download completes."""
        await self._send_discord(
            title="✅ Téléchargement terminé",
            description=f"**{title}**\n\nEn cours de traitement...",
            color=self.COLORS["success"],
            thumbnail=poster_url
        )
    
    async def notify_available_on_plex(
        self,
        title: str,
        media_type: str,
        username: str,
        poster_url: Optional[str] = None
    ):
        """Notify when media is available on Plex."""
        await self._send_discord(
            title="🎉 Disponible sur Plex !",
            description=f"**{title}**\n\n<@{username}>, votre demande est prête !",
            color=self.COLORS["success"],
            thumbnail=poster_url,
            fields=[
                {"name": "Statut", "value": "Disponible", "inline": True}
            ]
        )
    
    async def notify_request_completed(
        self,
        title: str,
        media_type: str,
        username: str,
        poster_url: Optional[str] = None,
        final_path: Optional[str] = None
    ):
        """Notify when a request is fully completed and available."""
        fields = [
            {"name": "Type", "value": media_type.replace("_", " ").title(), "inline": True},
            {"name": "Statut", "value": "✅ Disponible", "inline": True}
        ]
        if final_path:
            fields.append({"name": "Emplacement", "value": final_path[:50] + "..." if len(final_path) > 50 else final_path, "inline": False})
        
        await self._send_discord(
            title="🎉 Demande terminée !",
            description=f"**{title}**\n\nDemandé par **{username}**",
            color=self.COLORS["success"],
            thumbnail=poster_url,
            fields=fields
        )
    
    async def notify_error(
        self,
        title: str,
        error_message: str,
        requires_action: bool = False
    ):
        """Notify when an error occurs."""
        description = f"**{title}**\n\n{error_message}"
        if requires_action:
            description += "\n\n⚠️ **Action requise** - Vérifiez le panneau admin"
        
        await self._send_discord(
            title="❌ Erreur",
            description=description,
            color=self.COLORS["error"]
        )
    
    async def notify_quota_warning(
        self,
        username: str,
        remaining: int
    ):
        """Notify user about remaining quota."""
        # This is typically shown in UI only, but can send Discord if configured
        if remaining == 0:
            await self._send_discord(
                title="⚠️ Limite quotidienne atteinte",
                description=f"L'utilisateur **{username}** a atteint sa limite de 10 demandes par jour.",
                color=self.COLORS["warning"]
            )
    
    # =========================================================================
    # DISCORD WEBHOOK
    # =========================================================================
    
    async def _send_discord(
        self,
        title: str,
        description: str,
        color: int = 0x3498db,
        fields: Optional[list] = None,
        thumbnail: Optional[str] = None,
        footer: Optional[str] = None
    ) -> bool:
        """Send a Discord webhook message."""
        if not self.settings.discord_webhook_url:
            logger.debug("Discord webhook not configured")
            return False
        
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if fields:
            embed["fields"] = fields
        
        if thumbnail:
            embed["thumbnail"] = {"url": thumbnail}
        
        if footer:
            embed["footer"] = {"text": footer}
        else:
            embed["footer"] = {"text": self.settings.app_name}
        
        payload = {
            "embeds": [embed],
            "username": self.settings.app_name,
        }
        
        try:
            response = await self.client.post(
                self.settings.discord_webhook_url,
                json=payload
            )
            response.raise_for_status()
            logger.info(f"Discord notification sent: {title}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False
    
    # =========================================================================
    # STATUS HELPERS
    # =========================================================================
    
    def get_status_emoji(self, status: RequestStatus) -> str:
        """Get emoji for request status."""
        emojis = {
            RequestStatus.PENDING: "⏳",
            RequestStatus.SEARCHING: "🔍",
            RequestStatus.AWAITING_APPROVAL: "⚠️",
            RequestStatus.DOWNLOADING: "⬇️",
            RequestStatus.PROCESSING: "⚙️",
            RequestStatus.COMPLETED: "✅",
            RequestStatus.ERROR: "❌",
            RequestStatus.CANCELLED: "🚫"
        }
        return emojis.get(status, "❓")
    
    def get_status_color(self, status: RequestStatus) -> int:
        """Get Discord embed color for status."""
        colors = {
            RequestStatus.PENDING: self.COLORS["info"],
            RequestStatus.SEARCHING: self.COLORS["info"],
            RequestStatus.AWAITING_APPROVAL: self.COLORS["warning"],
            RequestStatus.DOWNLOADING: self.COLORS["pending"],
            RequestStatus.PROCESSING: self.COLORS["pending"],
            RequestStatus.COMPLETED: self.COLORS["success"],
            RequestStatus.ERROR: self.COLORS["error"],
            RequestStatus.CANCELLED: self.COLORS["error"]
        }
        return colors.get(status, self.COLORS["info"])
    
    # =========================================================================
    # HEALTH CHECK
    # =========================================================================
    
    def health_check(self) -> Dict[str, Any]:
        """Check notification configuration."""
        return {
            "discord": {
                "configured": bool(self.settings.discord_webhook_url),
                "url_preview": self.settings.discord_webhook_url[:50] + "..." if self.settings.discord_webhook_url else None
            }
        }


def get_notification_service() -> NotificationService:
    """Get notification service instance."""
    return NotificationService()
