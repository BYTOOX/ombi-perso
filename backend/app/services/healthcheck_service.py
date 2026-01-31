"""
Health check service for monitoring external service connectivity.
Provides detailed status reporting with retry logic and French error messages.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, Callable

import httpx

from ..models.service_config import ServiceName, HealthStatus
from .service_config_service import get_service_config_service

logger = logging.getLogger(__name__)


# French error messages for common issues
ERROR_MESSAGES = {
    "connection_refused": "Connexion refusée - Le service n'est pas accessible",
    "connection_timeout": "Délai d'attente dépassé - Le service ne répond pas",
    "dns_error": "Erreur DNS - Impossible de résoudre l'adresse",
    "ssl_error": "Erreur SSL - Certificat invalide ou expiré",
    "auth_error": "Erreur d'authentification - Identifiants incorrects",
    "not_configured": "Service non configuré",
    "disabled": "Service désactivé",
    "invalid_url": "URL invalide",
    "unknown_error": "Erreur inconnue",
}


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    service_name: str
    status: str  # ok, error, timeout, not_configured, disabled
    message: str
    latency_ms: Optional[int] = None
    details: Optional[Dict[str, Any]] = None
    checked_at: datetime = None

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "status": self.status,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "details": self.details,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }


class HealthCheckService:
    """
    Centralized health check service with:
    - Service-specific health checks
    - Automatic retry on temporary failures
    - Configuration validation
    - Detailed status reporting in French
    """

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2
    DEFAULT_TIMEOUT_SECONDS = 5

    def __init__(self):
        self._config_service = get_service_config_service()

    def _get_error_message(self, error: Exception) -> str:
        """Get user-friendly French error message."""
        error_str = str(error).lower()

        if "connection refused" in error_str or "connect call failed" in error_str:
            return ERROR_MESSAGES["connection_refused"]
        elif "timeout" in error_str or "timed out" in error_str:
            return ERROR_MESSAGES["connection_timeout"]
        elif "name or service not known" in error_str or "getaddrinfo failed" in error_str:
            return ERROR_MESSAGES["dns_error"]
        elif "ssl" in error_str or "certificate" in error_str:
            return ERROR_MESSAGES["ssl_error"]
        elif "401" in error_str or "403" in error_str or "unauthorized" in error_str:
            return ERROR_MESSAGES["auth_error"]
        else:
            return f"{ERROR_MESSAGES['unknown_error']}: {str(error)[:100]}"

    async def _check_with_retry(
        self,
        check_func: Callable,
        service_name: str,
        retry: bool = True
    ) -> HealthCheckResult:
        """Execute health check with optional retry logic."""
        last_error = None
        attempts = self.MAX_RETRIES if retry else 1

        for attempt in range(attempts):
            try:
                start_time = time.time()
                result = await check_func()
                latency_ms = int((time.time() - start_time) * 1000)

                if result.get("success", False):
                    return HealthCheckResult(
                        service_name=service_name,
                        status=HealthStatus.OK.value,
                        message=result.get("message", "Service opérationnel"),
                        latency_ms=latency_ms,
                        details=result.get("details"),
                    )
                else:
                    return HealthCheckResult(
                        service_name=service_name,
                        status=HealthStatus.ERROR.value,
                        message=result.get("message", ERROR_MESSAGES["unknown_error"]),
                        latency_ms=latency_ms,
                        details=result.get("details"),
                    )

            except asyncio.TimeoutError:
                last_error = ERROR_MESSAGES["connection_timeout"]
            except Exception as e:
                last_error = self._get_error_message(e)
                logger.debug(f"Health check attempt {attempt + 1}/{attempts} for {service_name}: {e}")

            if attempt < attempts - 1:
                await asyncio.sleep(self.RETRY_DELAY_SECONDS)

        return HealthCheckResult(
            service_name=service_name,
            status=HealthStatus.ERROR.value,
            message=last_error or ERROR_MESSAGES["unknown_error"],
        )

    # =========================================================================
    # SERVICE-SPECIFIC HEALTH CHECKS
    # =========================================================================

    async def check_plex(self) -> HealthCheckResult:
        """Check Plex server connectivity."""
        config = await self._config_service.get_decrypted_config(ServiceName.PLEX.value)

        if not config or not config.get("url"):
            return HealthCheckResult(
                service_name=ServiceName.PLEX.value,
                status=HealthStatus.NOT_CONFIGURED.value,
                message=ERROR_MESSAGES["not_configured"],
            )

        if not config.get("is_enabled", True):
            return HealthCheckResult(
                service_name=ServiceName.PLEX.value,
                status=HealthStatus.DISABLED.value,
                message=ERROR_MESSAGES["disabled"],
            )

        async def check():
            url = config["url"].rstrip("/")
            token = config.get("token", "")

            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS, verify=False) as client:
                response = await client.get(
                    f"{url}/",
                    headers={"X-Plex-Token": token, "Accept": "application/json"}
                )

                if response.status_code == 200:
                    data = response.json()
                    server_name = data.get("MediaContainer", {}).get("friendlyName", "Unknown")
                    version = data.get("MediaContainer", {}).get("version", "Unknown")
                    return {
                        "success": True,
                        "message": f"Connecté à {server_name}",
                        "details": {"server_name": server_name, "version": version}
                    }
                elif response.status_code == 401:
                    return {"success": False, "message": ERROR_MESSAGES["auth_error"]}
                else:
                    return {"success": False, "message": f"Erreur HTTP {response.status_code}"}

        return await self._check_with_retry(check, ServiceName.PLEX.value)

    async def check_qbittorrent(self) -> HealthCheckResult:
        """Check qBittorrent WebUI connectivity."""
        config = await self._config_service.get_decrypted_config(ServiceName.QBITTORRENT.value)

        if not config or not config.get("url"):
            return HealthCheckResult(
                service_name=ServiceName.QBITTORRENT.value,
                status=HealthStatus.NOT_CONFIGURED.value,
                message=ERROR_MESSAGES["not_configured"],
            )

        if not config.get("is_enabled", True):
            return HealthCheckResult(
                service_name=ServiceName.QBITTORRENT.value,
                status=HealthStatus.DISABLED.value,
                message=ERROR_MESSAGES["disabled"],
            )

        async def check():
            url = config["url"].rstrip("/")
            username = config.get("username", "admin")
            password = config.get("password", "")

            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS, verify=False) as client:
                # Try to login
                login_response = await client.post(
                    f"{url}/api/v2/auth/login",
                    data={"username": username, "password": password}
                )

                if login_response.text == "Ok.":
                    # Get version info
                    version_response = await client.get(f"{url}/api/v2/app/version")
                    api_version_response = await client.get(f"{url}/api/v2/app/webapiVersion")

                    return {
                        "success": True,
                        "message": f"qBittorrent {version_response.text}",
                        "details": {
                            "version": version_response.text,
                            "api_version": api_version_response.text
                        }
                    }
                else:
                    return {"success": False, "message": ERROR_MESSAGES["auth_error"]}

        return await self._check_with_retry(check, ServiceName.QBITTORRENT.value)

    async def check_ai(self) -> HealthCheckResult:
        """Check AI service (OpenAI-compatible) connectivity."""
        from .ai_provider import get_ai_service, AINotConfiguredError

        ai_service = get_ai_service()

        async def check():
            try:
                result = await ai_service.health_check()

                if result.get("available"):
                    models = result.get("models", [])
                    configured_model = result.get("configured_model", "")
                    return {
                        "success": True,
                        "message": f"IA ({len(models)} modèles)",
                        "details": {
                            "models": models,
                            "model_configured": configured_model
                        }
                    }
                else:
                    error = result.get("error", "Unknown error")
                    if "not configured" in error.lower():
                        return {"success": False, "message": ERROR_MESSAGES["not_configured"], "not_configured": True}
                    elif "disabled" in error.lower():
                        return {"success": False, "message": ERROR_MESSAGES["disabled"], "disabled": True}
                    return {"success": False, "message": error}

            except AINotConfiguredError:
                return {"success": False, "message": ERROR_MESSAGES["not_configured"], "not_configured": True}

        return await self._check_with_retry(check, ServiceName.AI.value)

    async def check_tmdb(self) -> HealthCheckResult:
        """Check TMDB API connectivity."""
        config = await self._config_service.get_decrypted_config(ServiceName.TMDB.value)

        if not config or not config.get("api_key"):
            return HealthCheckResult(
                service_name=ServiceName.TMDB.value,
                status=HealthStatus.NOT_CONFIGURED.value,
                message=ERROR_MESSAGES["not_configured"],
            )

        if not config.get("is_enabled", True):
            return HealthCheckResult(
                service_name=ServiceName.TMDB.value,
                status=HealthStatus.DISABLED.value,
                message=ERROR_MESSAGES["disabled"],
            )

        async def check():
            api_key = config["api_key"]

            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    "https://api.themoviedb.org/3/configuration",
                    params={"api_key": api_key}
                )

                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "API TMDB opérationnelle",
                        "details": {"status": "connected"}
                    }
                elif response.status_code == 401:
                    return {"success": False, "message": "Clé API invalide"}
                else:
                    return {"success": False, "message": f"Erreur HTTP {response.status_code}"}

        return await self._check_with_retry(check, ServiceName.TMDB.value)

    async def check_ygg(self) -> HealthCheckResult:
        """Check YGGtorrent connectivity (via YggAPI)."""
        # Check YggAPI first (preferred)
        yggapi_config = await self._config_service.get_decrypted_config(ServiceName.YGGAPI.value)

        if yggapi_config and yggapi_config.get("url") and yggapi_config.get("is_enabled", True):
            async def check_yggapi():
                url = yggapi_config["url"].rstrip("/")
                async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS) as client:
                    response = await client.get(f"{url}/torrents", params={"q": "test", "per_page": 1})
                    if response.status_code == 200:
                        return {
                            "success": True,
                            "message": "YggAPI opérationnelle",
                            "details": {"source": "yggapi"}
                        }
                    return {"success": False, "message": f"Erreur HTTP {response.status_code}"}

            result = await self._check_with_retry(check_yggapi, ServiceName.YGG.value, retry=False)
            if result.status == HealthStatus.OK.value:
                return result

        # Fallback: check YGG direct
        config = await self._config_service.get_decrypted_config(ServiceName.YGG.value)

        if not config or not config.get("url"):
            return HealthCheckResult(
                service_name=ServiceName.YGG.value,
                status=HealthStatus.NOT_CONFIGURED.value,
                message=ERROR_MESSAGES["not_configured"],
            )

        return HealthCheckResult(
            service_name=ServiceName.YGG.value,
            status=HealthStatus.OK.value,
            message="Configuration YGG présente (nécessite FlareSolverr)",
            details={"source": "ygg_direct", "requires_flaresolverr": True}
        )

    async def check_discord(self) -> HealthCheckResult:
        """Check Discord webhook connectivity."""
        config = await self._config_service.get_decrypted_config(ServiceName.DISCORD.value)

        if not config or not config.get("url"):
            return HealthCheckResult(
                service_name=ServiceName.DISCORD.value,
                status=HealthStatus.NOT_CONFIGURED.value,
                message=ERROR_MESSAGES["not_configured"],
            )

        if not config.get("is_enabled", True):
            return HealthCheckResult(
                service_name=ServiceName.DISCORD.value,
                status=HealthStatus.DISABLED.value,
                message=ERROR_MESSAGES["disabled"],
            )

        # Discord webhooks don't have a test endpoint, just validate URL format
        url = config["url"]
        if "discord.com/api/webhooks/" in url or "discordapp.com/api/webhooks/" in url:
            return HealthCheckResult(
                service_name=ServiceName.DISCORD.value,
                status=HealthStatus.OK.value,
                message="Webhook Discord configuré",
                details={"webhook_configured": True}
            )
        else:
            return HealthCheckResult(
                service_name=ServiceName.DISCORD.value,
                status=HealthStatus.ERROR.value,
                message="URL de webhook invalide",
            )

    async def check_flaresolverr(self) -> HealthCheckResult:
        """Check FlareSolverr connectivity."""
        config = await self._config_service.get_decrypted_config(ServiceName.FLARESOLVERR.value)

        if not config or not config.get("url"):
            return HealthCheckResult(
                service_name=ServiceName.FLARESOLVERR.value,
                status=HealthStatus.NOT_CONFIGURED.value,
                message=ERROR_MESSAGES["not_configured"],
            )

        if not config.get("is_enabled", True):
            return HealthCheckResult(
                service_name=ServiceName.FLARESOLVERR.value,
                status=HealthStatus.DISABLED.value,
                message=ERROR_MESSAGES["disabled"],
            )

        async def check():
            url = config["url"].rstrip("/")

            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{url.replace('/v1', '')}/health")
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "FlareSolverr opérationnel",
                        "details": response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    }
                return {"success": False, "message": f"Erreur HTTP {response.status_code}"}

        return await self._check_with_retry(check, ServiceName.FLARESOLVERR.value)

    # =========================================================================
    # AGGREGATE METHODS
    # =========================================================================

    async def check_service(self, service_name: str, retry: bool = True) -> HealthCheckResult:
        """Check a specific service."""
        check_methods = {
            ServiceName.PLEX.value: self.check_plex,
            ServiceName.QBITTORRENT.value: self.check_qbittorrent,
            ServiceName.AI.value: self.check_ai,
            ServiceName.TMDB.value: self.check_tmdb,
            ServiceName.YGG.value: self.check_ygg,
            ServiceName.DISCORD.value: self.check_discord,
            ServiceName.FLARESOLVERR.value: self.check_flaresolverr,
        }

        check_func = check_methods.get(service_name)
        if not check_func:
            return HealthCheckResult(
                service_name=service_name,
                status=HealthStatus.ERROR.value,
                message=f"Service inconnu: {service_name}",
            )

        result = await check_func()

        # Update status in database
        await self._config_service.update_health_status(
            service_name,
            result.status,
            result.message,
            result.latency_ms
        )

        return result

    async def check_all_services(self) -> Dict[str, HealthCheckResult]:
        """Check all configured services in parallel."""
        services = [
            ServiceName.PLEX.value,
            ServiceName.QBITTORRENT.value,
            ServiceName.AI.value,
            ServiceName.TMDB.value,
            ServiceName.YGG.value,
            ServiceName.DISCORD.value,
            ServiceName.FLARESOLVERR.value,
        ]

        # Run all checks in parallel
        tasks = [self.check_service(service, retry=False) for service in services]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            service: result if isinstance(result, HealthCheckResult) else HealthCheckResult(
                service_name=service,
                status=HealthStatus.ERROR.value,
                message=str(result),
            )
            for service, result in zip(services, results)
        }

    async def validate_config_before_save(
        self,
        service_name: str,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> HealthCheckResult:
        """
        Validate service configuration by testing connection.
        Used before saving configuration to ensure it works.
        """
        # Temporarily save config for testing
        await self._config_service.set_service_config(
            service_name,
            url=url,
            username=username,
            password=password,
            api_key=api_key,
            token=token,
            extra_config=extra_config,
            is_enabled=True,
        )

        # Test the configuration
        result = await self.check_service(service_name, retry=True)

        return result


# Singleton getter
_healthcheck_service: Optional[HealthCheckService] = None


def get_healthcheck_service() -> HealthCheckService:
    """Get health check service singleton."""
    global _healthcheck_service
    if _healthcheck_service is None:
        _healthcheck_service = HealthCheckService()
    return _healthcheck_service
