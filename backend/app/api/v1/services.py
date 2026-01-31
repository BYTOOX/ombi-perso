"""
API endpoints for external service configuration.
Allows admin to configure services (Plex, qBittorrent, AI, etc.) from the admin panel.
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ...models import User
from ...models.service_config import ServiceName
from ...services.service_config_service import get_service_config_service, SERVICE_METADATA
from ...services.healthcheck_service import get_healthcheck_service
from .auth import get_current_admin

router = APIRouter(prefix="/services", tags=["Services"])


# =========================================================================
# SCHEMAS
# =========================================================================

class ServiceConfigUpdate(BaseModel):
    """Schema for updating service configuration."""
    url: Optional[str] = Field(None, description="Service URL")
    username: Optional[str] = Field(None, description="Username for authentication")
    password: Optional[str] = Field(None, description="Password (will be encrypted)")
    api_key: Optional[str] = Field(None, description="API key (will be encrypted)")
    token: Optional[str] = Field(None, description="Token (will be encrypted)")
    extra_config: Optional[Dict[str, Any]] = Field(None, description="Service-specific configuration")
    is_enabled: bool = Field(True, description="Whether service is enabled")


class ServiceConfigResponse(BaseModel):
    """Schema for service configuration response."""
    service_name: str
    display_name: str
    description: str
    icon: str
    fields: List[str]
    extra_fields: List[str] = []
    is_configured: bool
    is_enabled: bool
    config: Optional[Dict[str, Any]] = None


class HealthCheckResponse(BaseModel):
    """Schema for health check response."""
    service_name: str
    status: str
    message: str
    latency_ms: Optional[int] = None
    details: Optional[Dict[str, Any]] = None
    checked_at: Optional[str] = None


# =========================================================================
# ENDPOINTS
# =========================================================================

@router.get("", response_model=List[ServiceConfigResponse])
async def list_services(
    current_user: User = Depends(get_current_admin)
):
    """
    Lister tous les services avec leur configuration et état.
    Retourne les métadonnées de chaque service (champs requis, icône, etc.).
    """
    config_service = get_service_config_service()
    services = await config_service.get_all_services()
    return services


@router.get("/{service_name}")
async def get_service_config(
    service_name: str,
    current_user: User = Depends(get_current_admin)
):
    """
    Obtenir la configuration d'un service spécifique.
    Les mots de passe et tokens sont masqués (indiqués par has_password, has_token).
    """
    # Validate service name
    valid_services = [s.value for s in ServiceName]
    if service_name not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Service invalide. Services disponibles: {', '.join(valid_services)}"
        )

    config_service = get_service_config_service()
    config = await config_service.get_service_config(service_name)

    metadata = SERVICE_METADATA.get(service_name, {})

    return {
        "service_name": service_name,
        "display_name": metadata.get("display_name", service_name),
        "description": metadata.get("description", ""),
        "icon": metadata.get("icon", "bi-gear"),
        "fields": metadata.get("fields", []),
        "extra_fields": metadata.get("extra_fields", []),
        "is_configured": config is not None and config.url is not None,
        "is_enabled": config.is_enabled if config else False,
        "config": config.to_dict() if config else None,
    }


@router.put("/{service_name}")
async def update_service_config(
    service_name: str,
    config: ServiceConfigUpdate,
    current_user: User = Depends(get_current_admin)
):
    """
    Mettre à jour la configuration d'un service.
    Les champs sensibles (password, api_key, token) seront chiffrés.
    """
    # Validate service name
    valid_services = [s.value for s in ServiceName]
    if service_name not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Service invalide. Services disponibles: {', '.join(valid_services)}"
        )

    config_service = get_service_config_service()

    # Update configuration
    updated = await config_service.set_service_config(
        service_name=service_name,
        url=config.url,
        username=config.username,
        password=config.password,
        api_key=config.api_key,
        token=config.token,
        extra_config=config.extra_config,
        is_enabled=config.is_enabled,
    )

    return {
        "success": True,
        "message": f"Configuration de {service_name} mise à jour",
        "config": updated.to_dict()
    }


@router.post("/{service_name}/test", response_model=HealthCheckResponse)
async def test_service_connection(
    service_name: str,
    config: Optional[ServiceConfigUpdate] = Body(None),
    current_user: User = Depends(get_current_admin)
):
    """
    Tester la connexion à un service.

    Si 'config' est fourni, teste avec ces paramètres (sans les sauvegarder).
    Sinon, teste avec la configuration existante.
    """
    # Validate service name
    valid_services = [s.value for s in ServiceName]
    if service_name not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Service invalide. Services disponibles: {', '.join(valid_services)}"
        )

    healthcheck_service = get_healthcheck_service()
    config_service = get_service_config_service()

    # If config provided, temporarily save it for testing
    if config:
        await config_service.set_service_config(
            service_name=service_name,
            url=config.url,
            username=config.username,
            password=config.password,
            api_key=config.api_key,
            token=config.token,
            extra_config=config.extra_config,
            is_enabled=config.is_enabled,
        )

    # Run health check
    result = await healthcheck_service.check_service(service_name, retry=True)

    return HealthCheckResponse(
        service_name=result.service_name,
        status=result.status,
        message=result.message,
        latency_ms=result.latency_ms,
        details=result.details,
        checked_at=result.checked_at.isoformat() if result.checked_at else None,
    )


@router.get("/{service_name}/health", response_model=HealthCheckResponse)
async def get_service_health(
    service_name: str,
    current_user: User = Depends(get_current_admin)
):
    """
    Obtenir l'état de santé détaillé d'un service.
    Exécute un healthcheck en temps réel.
    """
    # Validate service name
    valid_services = [s.value for s in ServiceName]
    if service_name not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Service invalide. Services disponibles: {', '.join(valid_services)}"
        )

    healthcheck_service = get_healthcheck_service()
    result = await healthcheck_service.check_service(service_name, retry=False)

    return HealthCheckResponse(
        service_name=result.service_name,
        status=result.status,
        message=result.message,
        latency_ms=result.latency_ms,
        details=result.details,
        checked_at=result.checked_at.isoformat() if result.checked_at else None,
    )


@router.delete("/{service_name}")
async def delete_service_config(
    service_name: str,
    current_user: User = Depends(get_current_admin)
):
    """
    Supprimer la configuration d'un service.
    Le service sera marqué comme non configuré.
    """
    # Validate service name
    valid_services = [s.value for s in ServiceName]
    if service_name not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Service invalide. Services disponibles: {', '.join(valid_services)}"
        )

    config_service = get_service_config_service()
    deleted = await config_service.delete_service_config(service_name)

    if deleted:
        return {"success": True, "message": f"Configuration de {service_name} supprimée"}
    else:
        return {"success": False, "message": f"Aucune configuration trouvée pour {service_name}"}


@router.post("/{service_name}/toggle")
async def toggle_service(
    service_name: str,
    enabled: bool = Query(..., description="Activer ou désactiver le service"),
    current_user: User = Depends(get_current_admin)
):
    """
    Activer ou désactiver un service sans modifier sa configuration.
    """
    # Validate service name
    valid_services = [s.value for s in ServiceName]
    if service_name not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Service invalide. Services disponibles: {', '.join(valid_services)}"
        )

    config_service = get_service_config_service()
    config = await config_service.get_service_config(service_name)

    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Service {service_name} non configuré"
        )

    # Update only the enabled status
    await config_service.set_service_config(
        service_name=service_name,
        is_enabled=enabled,
    )

    status_text = "activé" if enabled else "désactivé"
    return {"success": True, "message": f"Service {service_name} {status_text}"}


@router.get("/health/all")
async def get_all_services_health(
    current_user: User = Depends(get_current_admin)
):
    """
    Vérifier l'état de santé de tous les services en parallèle.
    Retourne un résumé de l'état de chaque service.
    """
    healthcheck_service = get_healthcheck_service()
    results = await healthcheck_service.check_all_services()

    # Format results
    formatted = {}
    for service_name, result in results.items():
        formatted[service_name] = {
            "status": result.status,
            "message": result.message,
            "latency_ms": result.latency_ms,
        }

    # Calculate summary
    statuses = [r.status for r in results.values()]
    ok_count = statuses.count("ok")
    error_count = statuses.count("error")
    not_configured_count = statuses.count("not_configured")

    return {
        "services": formatted,
        "summary": {
            "total": len(results),
            "ok": ok_count,
            "error": error_count,
            "not_configured": not_configured_count,
            "overall_status": "ok" if error_count == 0 else "degraded" if ok_count > 0 else "error"
        }
    }


@router.post("/migrate-env")
async def migrate_from_env(
    current_user: User = Depends(get_current_admin)
):
    """
    Migrer les configurations depuis le fichier .env vers la base de données.
    Cette opération ne migre que les services qui ne sont pas déjà configurés.
    """
    config_service = get_service_config_service()
    migrations = config_service.migrate_from_env()

    migrated = [k for k, v in migrations.items() if v]
    skipped = [k for k, v in migrations.items() if not v]

    return {
        "success": True,
        "migrated": migrated,
        "skipped": skipped,
        "message": f"{len(migrated)} service(s) migré(s), {len(skipped)} déjà configuré(s)"
    }
