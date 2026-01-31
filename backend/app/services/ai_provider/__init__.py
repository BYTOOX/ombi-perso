"""
AI Provider module - Unified AI service for Plex Kiosk.

Supports multiple providers:
- llama.cpp server (OpenAI-compatible)
- llama-cpp-python server (OpenAI-compatible)
- OpenAI API
- OpenRouter

Usage:
    from app.services.ai_provider import get_ai_service

    ai = get_ai_service()
    result = await ai.select_best_torrent(media, torrents)
"""
import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ChatMessage, ChatResponse, HealthCheckResult, ModelInfo
from .config import AIConfig, ProviderType
from .exceptions import (
    AIDisabledError,
    AIError,
    AINotConfiguredError,
    AIResponseError,
    AITimeoutError,
)
from .provider import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

# Re-export public types
__all__ = [
    "AIService",
    "get_ai_service",
    "AIConfig",
    "ProviderType",
    "ChatMessage",
    "ChatResponse",
    "ModelInfo",
    "HealthCheckResult",
    "AIError",
    "AINotConfiguredError",
    "AITimeoutError",
    "AIResponseError",
    "AIDisabledError",
]


class AIService:
    """
    Unified AI service facade for Plex Kiosk.

    Provides high-level methods for:
    - Torrent scoring and selection
    - Anime name resolution
    - Plex-compatible filename generation
    - Image analysis (vision)

    Configuration is loaded from database ServiceConfiguration.
    Falls back to rule-based methods if AI is unavailable.
    """

    def __init__(self):
        self._provider: Optional[OpenAICompatibleProvider] = None
        self._config: Optional[AIConfig] = None
        self._config_service = None

    def _get_config_service(self):
        """Lazy load config service to avoid circular imports."""
        if self._config_service is None:
            from ..service_config_service import get_service_config_service
            self._config_service = get_service_config_service()
        return self._config_service

    async def _load_config(self) -> Optional[AIConfig]:
        """Load AI configuration from database."""
        config_service = self._get_config_service()
        db_config = await config_service.get_service_config("ai")

        if not db_config or not db_config.url:
            return None

        extra = db_config.extra_config or {}

        # Parse provider type
        provider_type_str = extra.get("provider_type", "llama_cpp")
        try:
            provider_type = ProviderType(provider_type_str)
        except ValueError:
            provider_type = ProviderType.LLAMA_CPP

        return AIConfig(
            provider_type=provider_type,
            base_url=db_config.url.rstrip("/"),
            api_key=await config_service.get_decrypted_value("ai", "api_key"),
            model_scoring=extra.get("model_scoring"),
            model_rename=extra.get("model_rename"),
            model_analysis=extra.get("model_analysis"),
            timeout=extra.get("timeout", 120.0),
            is_enabled=db_config.is_enabled,
            default_model=extra.get("model_scoring") or extra.get("model") or "qwen3-vl-30b"
        )

    async def _get_provider(self) -> OpenAICompatibleProvider:
        """Get or create the AI provider instance."""
        if self._provider is None:
            self._config = await self._load_config()
            if not self._config:
                raise AINotConfiguredError()
            self._provider = OpenAICompatibleProvider(self._config)
        return self._provider

    async def _get_config(self) -> Optional[AIConfig]:
        """Get current config, loading if needed."""
        if self._config is None:
            self._config = await self._load_config()
        return self._config

    def invalidate_cache(self):
        """Invalidate cached provider and config (call after config changes)."""
        self._provider = None
        self._config = None

    async def is_available(self) -> bool:
        """Check if AI service is configured and enabled."""
        try:
            config = await self._get_config()
            return config is not None and config.is_enabled
        except Exception:
            return False

    async def get_config(self) -> Optional[AIConfig]:
        """Get the current AI configuration."""
        return await self._get_config()

    # =========================================================================
    # MODEL LISTING
    # =========================================================================

    async def list_models(self) -> List[ModelInfo]:
        """
        List available models from the provider.

        Returns:
            List of ModelInfo objects
        """
        provider = await self._get_provider()
        return await provider.list_models()

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if AI service is available and get status.

        Returns:
            Dict with 'available', 'models', 'configured_model', 'error'
        """
        try:
            provider = await self._get_provider()
            result = await provider.health_check()
            return result.to_dict()
        except AINotConfiguredError:
            return {
                "available": False,
                "error": "AI service not configured"
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }

    # =========================================================================
    # TORRENT SCORING
    # =========================================================================

    async def score_torrents(
        self,
        media,  # MediaSearchResult
        torrents: List,  # List[TorrentResult]
        quality_preference: str = "1080p"
    ) -> List:
        """
        Score and rank torrents using AI analysis.

        Args:
            media: The media being searched for
            torrents: List of torrent results to analyze
            quality_preference: User's quality preference

        Returns:
            Sorted list of torrents with AI scores
        """
        if not torrents:
            logger.warning("[AI] No torrents to score")
            return []

        logger.info(f"[AI] Scoring {len(torrents)} torrents for: {media.title}")
        logger.info(f"[AI] Quality preference: {quality_preference}")

        # For small lists, use simpler scoring
        if len(torrents) <= 3:
            logger.info("[AI] Using simple scoring (≤3 torrents)")
            return self._simple_score_torrents(torrents, quality_preference)

        # Check if AI is available
        if not await self.is_available():
            logger.warning("[AI] Service not available, using simple scoring")
            return self._simple_score_torrents(torrents, quality_preference)

        try:
            provider = await self._get_provider()
            config = await self._get_config()
            model = config.get_model_for_task("scoring") if config else None

            messages = self._build_scoring_messages(media, torrents, quality_preference)
            response = await provider.chat(
                messages=[ChatMessage(m["role"], m["content"]) for m in messages],
                model=model,
                temperature=0.7,
                max_tokens=1000
            )

            logger.info(f"[AI] Response received ({len(response.content)} chars)")

            scored_torrents = self._parse_scoring_response(response.content, torrents)
            sorted_torrents = sorted(scored_torrents, key=lambda t: t.ai_score or 0, reverse=True)

            logger.info("[AI] Top 3 scored torrents:")
            for i, t in enumerate(sorted_torrents[:3], 1):
                logger.info(f"  [{i}] Score: {t.ai_score} - {t.name[:60]}...")

            return sorted_torrents

        except Exception as e:
            logger.error(f"[AI] Scoring failed: {e}")
            logger.info("[AI] Falling back to simple scoring")
            return self._simple_score_torrents(torrents, quality_preference)

    async def select_best_torrent(
        self,
        media,  # MediaSearchResult
        torrents: List,  # List[TorrentResult]
        quality_preference: str = "1080p"
    ):
        """Select the best torrent from the list."""
        logger.info(f"[AI] select_best_torrent called for: {media.title}")
        scored = await self.score_torrents(media, torrents, quality_preference)
        if scored:
            logger.info(f"[AI] Best torrent selected: {scored[0].name}")
        return scored[0] if scored else None

    def _build_scoring_messages(
        self,
        media,
        torrents: List,
        quality_preference: str
    ) -> List[Dict[str, Any]]:
        """Build chat messages for torrent scoring."""
        torrents_text = "\n".join([
            f"{i+1}. {t.name} | {t.size_human} | {t.seeders} seeders | {t.quality or 'unknown'}"
            for i, t in enumerate(torrents[:10])
        ])

        system_prompt = """Tu es un expert en sélection de torrents pour une médiathèque Plex.
Tu analyses les torrents et attribues des scores de 0 à 100.

RÈGLES DE SCORING:
- Préférer les groupes reconnus (SubsPlease, Erai-raws, Judas, SPARKS, GECKOS, NTB, FLUX)
- Qualité demandée prioritaire, sinon qualité supérieure
- HEVC/x265 préféré (meilleure compression)
- Éviter les versions CAM, TS, HDTS, SCREENER
- Seeders > 5 minimum
- VOSTFR ou MULTI préféré pour l'audio français
- Batch complet mieux que épisodes séparés pour les séries

Réponds UNIQUEMENT avec un JSON valide, sans texte avant ou après."""

        user_prompt = f"""MÉDIA RECHERCHÉ:
- Titre: {media.title}
- Type: {media.media_type}
- Année: {media.year or 'inconnue'}

PRÉFÉRENCE QUALITÉ: {quality_preference}

TORRENTS DISPONIBLES:
{torrents_text}

Analyse ces torrents et réponds avec ce format JSON:
{{
  "rankings": [
    {{"index": 1, "score": 95, "reason": "raison courte"}},
    {{"index": 2, "score": 80, "reason": "raison courte"}}
  ]
}}"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def _parse_scoring_response(self, response: str, torrents: List) -> List:
        """Parse AI scoring response."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                raise ValueError("No JSON found in response")

            data = json.loads(json_match.group())
            rankings = data.get("rankings", [])

            for rank in rankings:
                idx = rank.get("index", 0) - 1
                if 0 <= idx < len(torrents):
                    torrents[idx].ai_score = rank.get("score", 0)
                    torrents[idx].ai_reasoning = rank.get("reason", "")

            return torrents
        except Exception as e:
            logger.error(f"Error parsing scoring response: {e}")
            return self._simple_score_torrents(torrents, "1080p")

    def _simple_score_torrents(self, torrents: List, quality_preference: str) -> List:
        """Simple rule-based scoring fallback."""
        logger.info("[AI] Running simple rule-based scoring...")

        for t in torrents:
            score = 50

            # Quality bonus
            if t.quality == quality_preference:
                score += 30
            elif t.quality == "4K" and quality_preference != "4K":
                score += 20
            elif t.quality == "1080p":
                score += 25
            elif t.quality == "720p":
                score += 10

            # Seeders bonus
            if t.seeders > 50:
                score += 20
            elif t.seeders > 20:
                score += 15
            elif t.seeders > 10:
                score += 10
            elif t.seeders > 5:
                score += 5

            # Release group bonus
            known_groups = ["subsplease", "erai-raws", "judas", "sparks", "geckos", "ntb", "flux"]
            if t.release_group and t.release_group.lower() in known_groups:
                score += 15

            # French audio bonus
            if t.has_french_audio:
                score += 10

            # HEVC bonus
            if "x265" in t.name.lower() or "hevc" in t.name.lower():
                score += 10

            # Penalties
            if any(bad in t.name.lower() for bad in ["cam", "ts", "hdts", "screener"]):
                score -= 50

            t.ai_score = min(100, max(0, score))
            t.ai_reasoning = "Score automatique"

        return sorted(torrents, key=lambda t: t.ai_score or 0, reverse=True)

    # =========================================================================
    # ANIME NAME RESOLUTION
    # =========================================================================

    async def resolve_anime_name(
        self,
        anime,  # MediaSearchResult
        search_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolve anime name variations for better search results.

        Returns dict with:
        - search_terms: List of terms to search for
        - english_title: English title if available
        - romanized: Romanized Japanese title
        """
        fallback = {
            "search_terms": [anime.title, anime.romaji_title] if anime.romaji_title else [anime.title],
            "english_title": anime.title,
            "romanized": anime.romaji_title,
            "alternative_names": []
        }

        if not await self.is_available():
            return fallback

        try:
            provider = await self._get_provider()
            config = await self._get_config()
            model = config.get_model_for_task("rename") if config else None

            messages = [
                ChatMessage(
                    role="system",
                    content="Tu es un expert en anime. Tu fournis les variations de nom pour la recherche de torrents. Réponds uniquement en JSON valide."
                ),
                ChatMessage(
                    role="user",
                    content=f"""Pour l'anime suivant, fournis les variations de nom:

ANIME:
- Titre affiché: {anime.title}
- Titre original: {anime.original_title or 'N/A'}
- Romaji: {anime.romaji_title or 'N/A'}
- Année: {anime.year or 'inconnue'}

Réponds avec ce format JSON:
{{
  "search_terms": ["terme1", "terme2", "terme3"],
  "english_title": "titre anglais officiel",
  "romanized": "titre romanisé",
  "alternative_names": ["nom alt 1", "nom alt 2"]
}}"""
                )
            ]

            response = await provider.chat(messages, model=model)
            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            logger.error(f"Anime name resolution error: {e}")

        return fallback

    # =========================================================================
    # PLEX NAMING
    # =========================================================================

    async def generate_plex_name(
        self,
        media,  # MediaSearchResult
        torrent,  # TorrentResult
        episode_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate Plex/Filebot compatible filename.

        Format examples:
        - Movie: "Movie Name (2024).mkv"
        - Series: "Show Name (2024)/Season 01/Show Name (2024) - S01E01 - Episode Title.mkv"
        """
        # For movies
        if media.media_type == "movie":
            year = media.year or ""
            return f"{self._sanitize_filename(media.title)} ({year})"

        # For series/anime - try to detect season/episode from torrent name
        season_ep = self._extract_season_episode(torrent.name)

        if season_ep:
            season, episode = season_ep
            year = f" ({media.year})" if media.year else ""
            show_name = self._sanitize_filename(media.title)
            return f"{show_name}{year}/Season {season:02d}/{show_name}{year} - S{season:02d}E{episode:02d}"

        # Fallback - use AI to parse
        return await self._ai_generate_name(media, torrent)

    async def _ai_generate_name(self, media, torrent) -> str:
        """Use AI to generate Plex-compatible name."""
        fallback = f"{self._sanitize_filename(media.title)}"
        if media.year:
            fallback += f" ({media.year})"

        if not await self.is_available():
            return fallback

        try:
            provider = await self._get_provider()
            config = await self._get_config()
            model = config.get_model_for_task("rename") if config else None

            messages = [
                ChatMessage(
                    role="system",
                    content="Tu génères des noms de fichiers compatibles Plex. Réponds uniquement avec le chemin, sans guillemets ni explication."
                ),
                ChatMessage(
                    role="user",
                    content=f"""Génère un nom de fichier/dossier compatible Plex:

MÉDIA:
- Titre: {media.title}
- Type: {media.media_type}
- Année: {media.year}

NOM TORRENT: {torrent.name}

Format attendu:
- Film: "Nom du Film (Année)"
- Série: "Nom de la Série (Année)/Season XX/Nom de la Série (Année) - SXXEXX - Titre Episode"
"""
                )
            ]

            response = await provider.chat(messages, model=model)
            return response.content.strip().strip('"\'')

        except Exception as e:
            logger.error(f"AI naming error: {e}")
            return fallback

    def _extract_season_episode(self, filename: str) -> Optional[tuple]:
        """Extract season and episode from filename."""
        patterns = [
            r'S(\d{1,2})E(\d{1,3})',
            r'S(\d{1,2})\.E(\d{1,3})',
            r'(\d{1,2})x(\d{1,3})',
            r'Season[\s._-]?(\d{1,2})[\s._-]?Episode[\s._-]?(\d{1,3})',
            r'\[?(\d{1,2})\]?\s*-\s*\[?(\d{1,3})\]?',
        ]

        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return (int(match.group(1)), int(match.group(2)))

        return None

    def _sanitize_filename(self, name: str) -> str:
        """Remove invalid filename characters."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        return name.strip()

    # =========================================================================
    # VISION CAPABILITIES
    # =========================================================================

    async def analyze_image(self, image_path: str, prompt: str) -> str:
        """
        Analyze an image using vision capabilities.

        Args:
            image_path: Path to the image file
            prompt: Question or instruction about the image

        Returns:
            AI analysis of the image
        """
        if not await self.is_available():
            return "Service IA non disponible"

        try:
            path = Path(image_path)
            if not path.exists():
                return f"Image non trouvée: {image_path}"

            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            suffix = path.suffix.lower()
            media_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp"
            }.get(suffix, "image/jpeg")

        except Exception as e:
            logger.error(f"Error reading image: {e}")
            return f"Erreur lecture image: {e}"

        # Build vision message
        messages = [
            ChatMessage(
                role="user",
                content=[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_data}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            )
        ]

        try:
            provider = await self._get_provider()
            config = await self._get_config()
            model = config.get_model_for_task("analysis") if config else None
            response = await provider.chat(messages, model=model)
            return response.content
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return f"Erreur analyse: {e}"

    async def analyze_image_url(self, image_url: str, prompt: str) -> str:
        """
        Analyze an image from URL using vision capabilities.

        Args:
            image_url: URL of the image
            prompt: Question or instruction about the image

        Returns:
            AI analysis of the image
        """
        if not await self.is_available():
            return "Service IA non disponible"

        messages = [
            ChatMessage(
                role="user",
                content=[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            )
        ]

        try:
            provider = await self._get_provider()
            config = await self._get_config()
            model = config.get_model_for_task("analysis") if config else None
            response = await provider.chat(messages, model=model)
            return response.content
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return f"Erreur analyse: {e}"

    # =========================================================================
    # RAW CHAT (for advanced use)
    # =========================================================================

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        task: str = "scoring"
    ) -> str:
        """
        Send a raw chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            task: Task type for model selection ('scoring', 'rename', 'analysis')

        Returns:
            Generated text response
        """
        provider = await self._get_provider()
        config = await self._get_config()

        # Select model for task if not specified
        if not model and config:
            model = config.get_model_for_task(task)

        chat_messages = [
            ChatMessage(m["role"], m["content"]) for m in messages
        ]

        response = await provider.chat(
            messages=chat_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response.content


# Singleton instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get AI service instance (singleton)."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
