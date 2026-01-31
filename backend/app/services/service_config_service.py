"""
Service configuration service for managing external service credentials.
Handles encryption/decryption of sensitive data using Fernet symmetric encryption.
"""
import base64
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.database import SessionLocal, AsyncSessionLocal
from ..models.service_config import ServiceConfiguration, ServiceName, HealthStatus

logger = logging.getLogger(__name__)


# Service display names and descriptions (French)
SERVICE_METADATA = {
    ServiceName.PLEX.value: {
        "display_name": "Plex Media Server",
        "description": "Serveur de médias pour la bibliothèque",
        "icon": "bi-play-circle",
        "fields": ["url", "token"],
    },
    ServiceName.QBITTORRENT.value: {
        "display_name": "qBittorrent",
        "description": "Client de téléchargement BitTorrent",
        "icon": "bi-download",
        "fields": ["url", "username", "password"],
    },
    ServiceName.AI.value: {
        "display_name": "IA (OpenAI-compatible)",
        "description": "llama.cpp, OpenAI, OpenRouter",
        "icon": "bi-robot",
        "fields": ["url", "api_key"],
        "extra_fields": ["provider_type", "model_scoring", "model_rename", "model_analysis", "timeout"],
    },
    ServiceName.YGG.value: {
        "display_name": "YGGtorrent",
        "description": "Source de torrents français",
        "icon": "bi-magnet",
        "fields": ["url", "username", "password"],
        "extra_fields": ["passkey"],
    },
    ServiceName.TMDB.value: {
        "display_name": "TMDB",
        "description": "Base de données de films et séries",
        "icon": "bi-film",
        "fields": ["api_key"],
    },
    ServiceName.DISCORD.value: {
        "display_name": "Discord",
        "description": "Notifications via webhook",
        "icon": "bi-discord",
        "fields": ["url"],
    },
    ServiceName.FLARESOLVERR.value: {
        "display_name": "FlareSolverr",
        "description": "Bypass Cloudflare (fallback)",
        "icon": "bi-shield-check",
        "fields": ["url"],
    },
    ServiceName.YGGAPI.value: {
        "display_name": "YggAPI",
        "description": "API YGG alternative (sans Cloudflare)",
        "icon": "bi-cloud",
        "fields": ["url"],
    },
}


class ServiceConfigurationService:
    """
    Service for managing external service configurations.

    Features:
    - Fernet encryption for sensitive data (passwords, API keys, tokens)
    - Database storage for persistence
    - Migration from .env on first run
    - Connection testing before saving
    """

    _instance: Optional["ServiceConfigurationService"] = None
    _fernet: Optional[Fernet] = None

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._init_encryption()

    def _init_encryption(self):
        """Initialize Fernet encryption using SECRET_KEY."""
        settings = get_settings()

        # Derive a 32-byte key from SECRET_KEY using SHA256
        key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
        # Fernet requires base64-encoded 32-byte key
        fernet_key = base64.urlsafe_b64encode(key_bytes)

        self._fernet = Fernet(fernet_key)
        logger.debug("Encryption initialized")

    def _encrypt(self, value: str) -> str:
        """Encrypt a sensitive value."""
        if not value:
            return ""
        try:
            encrypted = self._fernet.encrypt(value.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def _decrypt(self, encrypted_value: str) -> str:
        """Decrypt a sensitive value."""
        if not encrypted_value:
            return ""
        try:
            decrypted = self._fernet.decrypt(encrypted_value.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("Decryption failed: invalid token (key may have changed)")
            return ""
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return ""

    # =========================================================================
    # SYNCHRONOUS METHODS (for non-async contexts)
    # =========================================================================

    def get_service_config_sync(self, service_name: str) -> Optional[ServiceConfiguration]:
        """Get service configuration (sync)."""
        with SessionLocal() as db:
            return db.query(ServiceConfiguration).filter(
                ServiceConfiguration.service_name == service_name
            ).first()

    def get_all_services_sync(self) -> List[Dict[str, Any]]:
        """Get all service configurations with metadata (sync)."""
        with SessionLocal() as db:
            configs = db.query(ServiceConfiguration).all()
            config_map = {c.service_name: c for c in configs}

        result = []
        for service_name in ServiceName:
            name = service_name.value
            config = config_map.get(name)
            metadata = SERVICE_METADATA.get(name, {})

            result.append({
                "service_name": name,
                "display_name": metadata.get("display_name", name),
                "description": metadata.get("description", ""),
                "icon": metadata.get("icon", "bi-gear"),
                "fields": metadata.get("fields", []),
                "extra_fields": metadata.get("extra_fields", []),
                "is_configured": config is not None and config.url is not None,
                "is_enabled": config.is_enabled if config else False,
                "config": config.to_dict() if config else None,
            })

        return result

    def set_service_config_sync(
        self,
        service_name: str,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        is_enabled: bool = True,
    ) -> ServiceConfiguration:
        """Set service configuration with encryption (sync)."""
        with SessionLocal() as db:
            config = db.query(ServiceConfiguration).filter(
                ServiceConfiguration.service_name == service_name
            ).first()

            if not config:
                config = ServiceConfiguration(
                    service_name=service_name,
                    display_name=SERVICE_METADATA.get(service_name, {}).get("display_name", service_name)
                )
                db.add(config)

            # Update fields
            if url is not None:
                config.url = url.strip() if url else None
            if username is not None:
                config.username = username.strip() if username else None
            if password is not None:
                config.password_encrypted = self._encrypt(password) if password else None
            if api_key is not None:
                config.api_key_encrypted = self._encrypt(api_key) if api_key else None
            if token is not None:
                config.token_encrypted = self._encrypt(token) if token else None
            if extra_config is not None:
                config.extra_config = extra_config

            config.is_enabled = is_enabled
            config.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(config)

            logger.info(f"Service configuration updated: {service_name}")
            return config

    def get_decrypted_config_sync(self, service_name: str) -> Dict[str, Any]:
        """Get service configuration with decrypted sensitive fields (sync)."""
        config = self.get_service_config_sync(service_name)

        if not config:
            return {}

        result = config.to_dict()

        # Add decrypted sensitive fields
        if config.password_encrypted:
            result["password"] = self._decrypt(config.password_encrypted)
        if config.api_key_encrypted:
            result["api_key"] = self._decrypt(config.api_key_encrypted)
        if config.token_encrypted:
            result["token"] = self._decrypt(config.token_encrypted)

        return result

    def update_health_status_sync(
        self,
        service_name: str,
        status: str,
        message: str,
        latency_ms: Optional[int] = None
    ):
        """Update service health status (sync)."""
        with SessionLocal() as db:
            config = db.query(ServiceConfiguration).filter(
                ServiceConfiguration.service_name == service_name
            ).first()

            if config:
                config.last_health_check = datetime.utcnow()
                config.last_health_status = status
                config.last_health_message = message
                config.last_health_latency_ms = latency_ms
                db.commit()

    # =========================================================================
    # ASYNCHRONOUS METHODS
    # =========================================================================

    async def get_service_config(self, service_name: str) -> Optional[ServiceConfiguration]:
        """Get service configuration (async)."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ServiceConfiguration).where(
                    ServiceConfiguration.service_name == service_name
                )
            )
            return result.scalar_one_or_none()

    async def get_all_services(self) -> List[Dict[str, Any]]:
        """Get all service configurations with metadata (async)."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(ServiceConfiguration))
            configs = result.scalars().all()
            config_map = {c.service_name: c for c in configs}

        services = []
        for service_name in ServiceName:
            name = service_name.value
            config = config_map.get(name)
            metadata = SERVICE_METADATA.get(name, {})

            services.append({
                "service_name": name,
                "display_name": metadata.get("display_name", name),
                "description": metadata.get("description", ""),
                "icon": metadata.get("icon", "bi-gear"),
                "fields": metadata.get("fields", []),
                "extra_fields": metadata.get("extra_fields", []),
                "is_configured": config is not None and config.url is not None,
                "is_enabled": config.is_enabled if config else False,
                "config": config.to_dict() if config else None,
            })

        return services

    async def set_service_config(
        self,
        service_name: str,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        is_enabled: bool = True,
    ) -> ServiceConfiguration:
        """Set service configuration with encryption (async)."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ServiceConfiguration).where(
                    ServiceConfiguration.service_name == service_name
                )
            )
            config = result.scalar_one_or_none()

            if not config:
                config = ServiceConfiguration(
                    service_name=service_name,
                    display_name=SERVICE_METADATA.get(service_name, {}).get("display_name", service_name)
                )
                session.add(config)

            # Update fields
            if url is not None:
                config.url = url.strip() if url else None
            if username is not None:
                config.username = username.strip() if username else None
            if password is not None:
                config.password_encrypted = self._encrypt(password) if password else None
            if api_key is not None:
                config.api_key_encrypted = self._encrypt(api_key) if api_key else None
            if token is not None:
                config.token_encrypted = self._encrypt(token) if token else None
            if extra_config is not None:
                config.extra_config = extra_config

            config.is_enabled = is_enabled
            config.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(config)

            logger.info(f"Service configuration updated: {service_name}")
            return config

    async def get_decrypted_config(self, service_name: str) -> Dict[str, Any]:
        """Get service configuration with decrypted sensitive fields (async)."""
        config = await self.get_service_config(service_name)

        if not config:
            return {}

        result = config.to_dict()

        # Add decrypted sensitive fields
        if config.password_encrypted:
            result["password"] = self._decrypt(config.password_encrypted)
        if config.api_key_encrypted:
            result["api_key"] = self._decrypt(config.api_key_encrypted)
        if config.token_encrypted:
            result["token"] = self._decrypt(config.token_encrypted)

        return result

    async def update_health_status(
        self,
        service_name: str,
        status: str,
        message: str,
        latency_ms: Optional[int] = None
    ):
        """Update service health status (async)."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ServiceConfiguration).where(
                    ServiceConfiguration.service_name == service_name
                )
            )
            config = result.scalar_one_or_none()

            if config:
                config.last_health_check = datetime.utcnow()
                config.last_health_status = status
                config.last_health_message = message
                config.last_health_latency_ms = latency_ms
                await session.commit()

    async def delete_service_config(self, service_name: str) -> bool:
        """Delete service configuration (async)."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ServiceConfiguration).where(
                    ServiceConfiguration.service_name == service_name
                )
            )
            config = result.scalar_one_or_none()

            if config:
                await session.delete(config)
                await session.commit()
                logger.info(f"Service configuration deleted: {service_name}")
                return True
            return False

    # =========================================================================
    # MIGRATION FROM .ENV
    # =========================================================================

    def migrate_from_env(self) -> Dict[str, bool]:
        """
        Migrate service configurations from environment variables to database.
        Only migrates if no configuration exists for a service.
        Returns dict of service_name -> migrated (True/False).
        """
        settings = get_settings()
        migrations = {}

        # Plex
        if settings.plex_url and settings.plex_token:
            existing = self.get_service_config_sync(ServiceName.PLEX.value)
            if not existing:
                self.set_service_config_sync(
                    ServiceName.PLEX.value,
                    url=settings.plex_url,
                    token=settings.plex_token,
                    is_enabled=True
                )
                migrations[ServiceName.PLEX.value] = True
                logger.info("Migrated Plex configuration from .env")
            else:
                migrations[ServiceName.PLEX.value] = False

        # qBittorrent
        if settings.qbittorrent_url:
            existing = self.get_service_config_sync(ServiceName.QBITTORRENT.value)
            if not existing:
                self.set_service_config_sync(
                    ServiceName.QBITTORRENT.value,
                    url=settings.qbittorrent_url,
                    username=settings.qbittorrent_username,
                    password=settings.qbittorrent_password,
                    is_enabled=True
                )
                migrations[ServiceName.QBITTORRENT.value] = True
                logger.info("Migrated qBittorrent configuration from .env")
            else:
                migrations[ServiceName.QBITTORRENT.value] = False

        # Ollama/AI
        if settings.ollama_url:
            existing = self.get_service_config_sync(ServiceName.AI.value)
            if not existing:
                self.set_service_config_sync(
                    ServiceName.AI.value,
                    url=settings.ollama_url,
                    extra_config={
                        "model": settings.ollama_model or "qwen3-vl-30b",
                        "timeout": 120,
                        "backend": "ollama"  # Will be changed to "llamacpp" later
                    },
                    is_enabled=True
                )
                migrations[ServiceName.AI.value] = True
                logger.info("Migrated AI (Ollama) configuration from .env")
            else:
                migrations[ServiceName.AI.value] = False

        # YGGtorrent
        if settings.ygg_username or settings.ygg_passkey:
            existing = self.get_service_config_sync(ServiceName.YGG.value)
            if not existing:
                self.set_service_config_sync(
                    ServiceName.YGG.value,
                    url=settings.ygg_base_url,
                    username=settings.ygg_username,
                    password=settings.ygg_password,
                    extra_config={
                        "passkey": settings.ygg_passkey
                    } if settings.ygg_passkey else None,
                    is_enabled=True
                )
                migrations[ServiceName.YGG.value] = True
                logger.info("Migrated YGGtorrent configuration from .env")
            else:
                migrations[ServiceName.YGG.value] = False

        # TMDB
        if settings.tmdb_api_key:
            existing = self.get_service_config_sync(ServiceName.TMDB.value)
            if not existing:
                self.set_service_config_sync(
                    ServiceName.TMDB.value,
                    api_key=settings.tmdb_api_key,
                    is_enabled=True
                )
                migrations[ServiceName.TMDB.value] = True
                logger.info("Migrated TMDB configuration from .env")
            else:
                migrations[ServiceName.TMDB.value] = False

        # Discord
        if settings.discord_webhook_url:
            existing = self.get_service_config_sync(ServiceName.DISCORD.value)
            if not existing:
                self.set_service_config_sync(
                    ServiceName.DISCORD.value,
                    url=settings.discord_webhook_url,
                    is_enabled=True
                )
                migrations[ServiceName.DISCORD.value] = True
                logger.info("Migrated Discord configuration from .env")
            else:
                migrations[ServiceName.DISCORD.value] = False

        # FlareSolverr
        if settings.flaresolverr_url:
            existing = self.get_service_config_sync(ServiceName.FLARESOLVERR.value)
            if not existing:
                self.set_service_config_sync(
                    ServiceName.FLARESOLVERR.value,
                    url=settings.flaresolverr_url,
                    is_enabled=True
                )
                migrations[ServiceName.FLARESOLVERR.value] = True
                logger.info("Migrated FlareSolverr configuration from .env")
            else:
                migrations[ServiceName.FLARESOLVERR.value] = False

        # YggAPI
        if settings.yggapi_url:
            existing = self.get_service_config_sync(ServiceName.YGGAPI.value)
            if not existing:
                self.set_service_config_sync(
                    ServiceName.YGGAPI.value,
                    url=settings.yggapi_url,
                    is_enabled=True
                )
                migrations[ServiceName.YGGAPI.value] = True
                logger.info("Migrated YggAPI configuration from .env")
            else:
                migrations[ServiceName.YGGAPI.value] = False

        return migrations


# Singleton getter
_service_config_service: Optional[ServiceConfigurationService] = None


def get_service_config_service() -> ServiceConfigurationService:
    """Get service configuration service singleton."""
    global _service_config_service
    if _service_config_service is None:
        _service_config_service = ServiceConfigurationService()
    return _service_config_service


def init_service_configurations():
    """
    Initialize service configurations on app startup.
    Migrates from .env if configurations don't exist.
    """
    service = get_service_config_service()
    migrations = service.migrate_from_env()

    migrated = [k for k, v in migrations.items() if v]
    if migrated:
        logger.info(f"✓ Migrated {len(migrated)} service configurations from .env: {', '.join(migrated)}")
    else:
        logger.info("✓ Service configurations already initialized")
