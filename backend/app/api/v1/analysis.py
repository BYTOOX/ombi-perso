"""
API endpoints for library analysis.
Allows admin to trigger and view library quality analysis.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...models import User
from ...models.library_analysis import AnalysisType, Severity, AnalysisRunStatus
from ...services.library_analysis_service import get_library_analysis_service
from .auth import get_current_admin

router = APIRouter(prefix="/analysis", tags=["Analysis"])


# =========================================================================
# SCHEMAS
# =========================================================================

class StartAnalysisRequest(BaseModel):
    """Request schema for starting a new analysis."""
    analysis_types: Optional[List[str]] = Field(
        None,
        description="Types of analysis to run (None = all)"
    )
    media_types: Optional[List[str]] = Field(
        None,
        description="Media types to analyze (movie, series, anime)"
    )


class AnalysisRunResponse(BaseModel):
    """Response schema for an analysis run."""
    id: str
    status: str
    status_message: Optional[str]
    analysis_types: Optional[List[str]]
    media_types: Optional[List[str]]
    total_items_to_analyze: int
    items_analyzed: int
    progress_percent: int
    current_phase: Optional[str]
    issues_found: int
    issues_by_type: Optional[dict]
    issues_by_severity: Optional[dict]
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_seconds: Optional[int]
    error_message: Optional[str]
    created_at: Optional[str]


class AnalysisResultResponse(BaseModel):
    """Response schema for an analysis result."""
    id: int
    analysis_run_id: str
    analysis_type: str
    severity: str
    plex_rating_key: Optional[str]
    tmdb_id: Optional[str]
    title: str
    year: Optional[int]
    media_type: str
    poster_url: Optional[str]
    issue_description: str
    recommended_action: str
    # Type-specific
    collection_name: Optional[str]
    missing_titles: Optional[list]
    current_quality: Optional[str]
    current_codec: Optional[str]
    recommended_quality: Optional[str]
    missing_seasons: Optional[list]
    missing_episodes: Optional[dict]
    total_missing: Optional[int]
    # AI
    ai_reasoning: Optional[str]
    ai_confidence: Optional[float]
    # Status
    is_dismissed: bool
    dismissed_at: Optional[str]
    is_actioned: bool
    actioned_request_id: Optional[int]
    actioned_at: Optional[str]
    created_at: Optional[str]


class DismissRequest(BaseModel):
    """Request schema for dismissing a result."""
    reason: Optional[str] = Field(None, description="Reason for dismissing")


class ActionRequest(BaseModel):
    """Request schema for actioning a result."""
    request_id: int = Field(..., description="Media request ID created")


# =========================================================================
# RUN ENDPOINTS
# =========================================================================

@router.post("/run", response_model=AnalysisRunResponse)
async def start_analysis(
    request: StartAnalysisRequest,
    current_user: User = Depends(get_current_admin)
):
    """
    Démarrer une nouvelle analyse de bibliothèque.
    L'analyse s'exécute en arrière-plan et retourne immédiatement.
    """
    # Validate analysis types
    if request.analysis_types:
        valid_types = [t.value for t in AnalysisType]
        for at in request.analysis_types:
            if at not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Type d'analyse invalide: {at}. Valides: {valid_types}"
                )

    # Validate media types
    if request.media_types:
        valid_media = ["movie", "series", "anime"]
        for mt in request.media_types:
            if mt not in valid_media:
                raise HTTPException(
                    status_code=400,
                    detail=f"Type de média invalide: {mt}. Valides: {valid_media}"
                )

    analysis_service = get_library_analysis_service()

    run = await analysis_service.start_analysis(
        analysis_types=request.analysis_types,
        media_types=request.media_types,
        user_id=current_user.id
    )

    return AnalysisRunResponse(**run.to_dict())


@router.get("/runs", response_model=List[AnalysisRunResponse])
async def list_analysis_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_admin)
):
    """Lister les analyses passées."""
    analysis_service = get_library_analysis_service()
    runs = await analysis_service.get_all_runs(limit=limit, offset=offset)

    return [AnalysisRunResponse(**run.to_dict()) for run in runs]


@router.get("/runs/{run_id}", response_model=AnalysisRunResponse)
async def get_analysis_run(
    run_id: str,
    current_user: User = Depends(get_current_admin)
):
    """Obtenir les détails d'une analyse."""
    analysis_service = get_library_analysis_service()
    run = await analysis_service.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Analyse non trouvée")

    return AnalysisRunResponse(**run.to_dict())


@router.get("/runs/{run_id}/results", response_model=List[AnalysisResultResponse])
async def get_run_results(
    run_id: str,
    analysis_type: Optional[str] = Query(None, description="Filtrer par type"),
    severity: Optional[str] = Query(None, description="Filtrer par sévérité"),
    include_dismissed: bool = Query(False, description="Inclure les ignorés"),
    current_user: User = Depends(get_current_admin)
):
    """Obtenir les résultats d'une analyse."""
    analysis_service = get_library_analysis_service()

    # Validate filters
    if analysis_type:
        valid_types = [t.value for t in AnalysisType]
        if analysis_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Type d'analyse invalide: {analysis_type}"
            )

    if severity:
        valid_severities = [s.value for s in Severity]
        if severity not in valid_severities:
            raise HTTPException(
                status_code=400,
                detail=f"Sévérité invalide: {severity}"
            )

    results = await analysis_service.get_run_results(
        run_id=run_id,
        analysis_type=analysis_type,
        severity=severity,
        include_dismissed=include_dismissed
    )

    return [AnalysisResultResponse(**r.to_dict()) for r in results]


# =========================================================================
# RESULTS ENDPOINTS
# =========================================================================

@router.get("/results", response_model=List[AnalysisResultResponse])
async def get_latest_results(
    analysis_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_admin)
):
    """Obtenir les derniers résultats d'analyse (non ignorés)."""
    analysis_service = get_library_analysis_service()

    results = await analysis_service.get_latest_results(
        analysis_type=analysis_type,
        severity=severity,
        limit=limit
    )

    return [AnalysisResultResponse(**r.to_dict()) for r in results]


@router.post("/results/{result_id}/dismiss")
async def dismiss_result(
    result_id: int,
    request: DismissRequest,
    current_user: User = Depends(get_current_admin)
):
    """Ignorer un résultat d'analyse."""
    analysis_service = get_library_analysis_service()

    success = await analysis_service.dismiss_result(
        result_id=result_id,
        user_id=current_user.id,
        reason=request.reason
    )

    if not success:
        raise HTTPException(status_code=404, detail="Résultat non trouvé")

    return {"success": True, "message": "Résultat ignoré"}


@router.post("/results/{result_id}/action")
async def action_result(
    result_id: int,
    request: ActionRequest,
    current_user: User = Depends(get_current_admin)
):
    """Marquer un résultat comme traité (demande créée)."""
    analysis_service = get_library_analysis_service()

    success = await analysis_service.action_result(
        result_id=result_id,
        request_id=request.request_id
    )

    if not success:
        raise HTTPException(status_code=404, detail="Résultat non trouvé")

    return {"success": True, "message": "Résultat marqué comme traité"}


# =========================================================================
# SUMMARY ENDPOINT
# =========================================================================

@router.get("/summary")
async def get_analysis_summary(
    current_user: User = Depends(get_current_admin)
):
    """
    Obtenir un résumé des problèmes détectés.
    Inclut les statistiques par type et par sévérité.
    """
    analysis_service = get_library_analysis_service()
    summary = await analysis_service.get_summary()

    return summary


# =========================================================================
# TYPES INFO ENDPOINT
# =========================================================================

@router.get("/types")
async def get_analysis_types(
    current_user: User = Depends(get_current_admin)
):
    """Obtenir la liste des types d'analyse disponibles."""
    return {
        "analysis_types": [
            {
                "value": t.value,
                "label": _get_type_label(t.value),
                "description": _get_type_description(t.value)
            }
            for t in AnalysisType
        ],
        "severities": [
            {
                "value": s.value,
                "label": _get_severity_label(s.value),
                "color": _get_severity_color(s.value)
            }
            for s in Severity
        ]
    }


def _get_type_label(type_value: str) -> str:
    """Get human-readable label for analysis type."""
    labels = {
        "missing_collection": "Collections manquantes",
        "low_quality": "Qualité basse",
        "bad_codec": "Codec obsolète",
        "vostfr_upgradable": "VOSTFR upgradable",
        "missing_episodes": "Épisodes manquants",
        "missing_seasons": "Saisons manquantes",
        "low_bitrate": "Bitrate faible",
        "bad_audio": "Audio de mauvaise qualité",
        "duplicate": "Doublons"
    }
    return labels.get(type_value, type_value)


def _get_type_description(type_value: str) -> str:
    """Get description for analysis type."""
    descriptions = {
        "missing_collection": "Films manquants dans les collections/franchises",
        "low_quality": "Contenu en basse résolution (480p, SD)",
        "bad_codec": "Codecs obsolètes (MPEG4, Xvid, non-HEVC)",
        "vostfr_upgradable": "Contenu VOSTFR pouvant être upgradé en MULTI",
        "missing_episodes": "Épisodes manquants dans les séries",
        "missing_seasons": "Saisons complètes manquantes",
        "low_bitrate": "Fichiers avec un bitrate trop faible",
        "bad_audio": "Audio avec codec ou qualité médiocre",
        "duplicate": "Fichiers en double dans la bibliothèque"
    }
    return descriptions.get(type_value, "")


def _get_severity_label(severity_value: str) -> str:
    """Get human-readable label for severity."""
    labels = {
        "low": "Basse",
        "medium": "Moyenne",
        "high": "Haute"
    }
    return labels.get(severity_value, severity_value)


def _get_severity_color(severity_value: str) -> str:
    """Get color code for severity."""
    colors = {
        "low": "#10b981",   # Green
        "medium": "#f59e0b",  # Orange
        "high": "#ef4444"   # Red
    }
    return colors.get(severity_value, "#6b7280")
