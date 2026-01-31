"""
AI Agent using llama.cpp (OpenAI-compatible API) for intelligent torrent selection and anime name resolution.
Optimized for Qwen3-VL-30B-A3B model with vision capabilities.

Uses database configuration instead of .env for service URL/settings.
Falls back to rule-based scoring if AI is unavailable.
"""
import base64
import json
import logging
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
import httpx

from ..schemas.media import TorrentResult, MediaSearchResult
from .service_config_service import get_service_config_service

logger = logging.getLogger(__name__)


class LlamaCppService:
    """
    AI-powered service using llama.cpp with OpenAI-compatible API.

    Features:
    - Torrent scoring and selection
    - Anime name resolution (romaji/kanji → English)
    - Filebot-compatible naming generation
    - Vision capabilities for image analysis (Qwen3-VL)

    Configuration loaded from database ServiceConfiguration.
    """

    DEFAULT_MODEL = "qwen3-vl-30b"
    DEFAULT_TIMEOUT = 120.0

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._config_service = get_service_config_service()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get_config(self) -> Dict[str, Any]:
        """Get AI service configuration from database."""
        config = await self._config_service.get_service_config("ai")
        if not config or not config.url:
            return {}

        return {
            "url": config.url.rstrip("/"),
            "api_key": await self._config_service.get_decrypted_value("ai", "api_key"),
            "model": config.extra_config.get("model", self.DEFAULT_MODEL) if config.extra_config else self.DEFAULT_MODEL,
            "timeout": config.extra_config.get("timeout", self.DEFAULT_TIMEOUT) if config.extra_config else self.DEFAULT_TIMEOUT,
            "is_enabled": config.is_enabled,
        }

    async def is_available(self) -> bool:
        """Check if AI service is configured and enabled."""
        config = await self._get_config()
        return bool(config.get("url") and config.get("is_enabled", True))

    # =========================================================================
    # TORRENT SCORING
    # =========================================================================

    async def score_torrents(
        self,
        media: MediaSearchResult,
        torrents: List[TorrentResult],
        quality_preference: str = "1080p"
    ) -> List[TorrentResult]:
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

        # Use AI for larger lists
        logger.info(f"[AI] Using llama.cpp for scoring ({len(torrents)} torrents)")

        try:
            messages = self._build_scoring_messages(media, torrents, quality_preference)
            response = await self._chat_completion(messages)
            logger.info(f"[AI] llama.cpp response received ({len(response)} chars)")

            scored_torrents = self._parse_scoring_response(response, torrents)
            sorted_torrents = sorted(scored_torrents, key=lambda t: t.ai_score or 0, reverse=True)

            logger.info("[AI] Top 3 scored torrents:")
            for i, t in enumerate(sorted_torrents[:3], 1):
                logger.info(f"  [{i}] Score: {t.ai_score} - {t.name[:60]}...")

            return sorted_torrents
        except Exception as e:
            logger.error(f"[AI] llama.cpp scoring failed: {e}")
            logger.info("[AI] Falling back to simple scoring")
            return self._simple_score_torrents(torrents, quality_preference)

    async def select_best_torrent(
        self,
        media: MediaSearchResult,
        torrents: List[TorrentResult],
        quality_preference: str = "1080p"
    ) -> Optional[TorrentResult]:
        """Select the best torrent from the list."""
        logger.info(f"[AI] select_best_torrent called for: {media.title}")
        scored = await self.score_torrents(media, torrents, quality_preference)
        if scored:
            logger.info(f"[AI] Best torrent selected: {scored[0].name}")
        return scored[0] if scored else None

    def _build_scoring_messages(
        self,
        media: MediaSearchResult,
        torrents: List[TorrentResult],
        quality_preference: str
    ) -> List[Dict[str, Any]]:
        """Build chat messages for torrent scoring."""
        torrents_text = "\n".join([
            f"{i+1}. {t.name} | {t.size_human} | {t.seeders} seeders | {t.quality or 'unknown'}"
            for i, t in enumerate(torrents[:10])  # Limit to 10
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

    def _parse_scoring_response(
        self,
        response: str,
        torrents: List[TorrentResult]
    ) -> List[TorrentResult]:
        """Parse AI scoring response."""
        try:
            # Extract JSON from response
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

    def _simple_score_torrents(
        self,
        torrents: List[TorrentResult],
        quality_preference: str
    ) -> List[TorrentResult]:
        """Simple rule-based scoring fallback."""
        logger.info("[AI] Running simple rule-based scoring...")

        for t in torrents:
            score = 50  # Base score

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
        anime: MediaSearchResult,
        search_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolve anime name variations for better search results.

        Returns dict with:
        - search_terms: List of terms to search for
        - english_title: English title if available
        - romanized: Romanized Japanese title
        """
        if not await self.is_available():
            # Fallback
            return {
                "search_terms": [anime.title, anime.romaji_title] if anime.romaji_title else [anime.title],
                "english_title": anime.title,
                "romanized": anime.romaji_title,
                "alternative_names": []
            }

        messages = [
            {
                "role": "system",
                "content": "Tu es un expert en anime. Tu fournis les variations de nom pour la recherche de torrents. Réponds uniquement en JSON valide."
            },
            {
                "role": "user",
                "content": f"""Pour l'anime suivant, fournis les variations de nom:

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
            }
        ]

        try:
            response = await self._chat_completion(messages)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"Anime name resolution error: {e}")

        # Fallback
        return {
            "search_terms": [anime.title, anime.romaji_title] if anime.romaji_title else [anime.title],
            "english_title": anime.title,
            "romanized": anime.romaji_title,
            "alternative_names": []
        }

    # =========================================================================
    # FILEBOT NAMING
    # =========================================================================

    async def generate_plex_name(
        self,
        media: MediaSearchResult,
        torrent: TorrentResult,
        episode_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate Plex/Filebot compatible filename.

        Format examples:
        - Movie: "Movie Name (2024).mkv"
        - Series: "Show Name (2024)/Season 01/Show Name (2024) - S01E01 - Episode Title.mkv"
        - Anime: "Anime Name (2024)/Season 01/Anime Name (2024) - S01E01 - Episode Title.mkv"
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

    async def _ai_generate_name(
        self,
        media: MediaSearchResult,
        torrent: TorrentResult
    ) -> str:
        """Use AI to generate Plex-compatible name."""
        if not await self.is_available():
            year = f" ({media.year})" if media.year else ""
            return f"{self._sanitize_filename(media.title)}{year}"

        messages = [
            {
                "role": "system",
                "content": "Tu génères des noms de fichiers compatibles Plex. Réponds uniquement avec le chemin, sans guillemets ni explication."
            },
            {
                "role": "user",
                "content": f"""Génère un nom de fichier/dossier compatible Plex:

MÉDIA:
- Titre: {media.title}
- Type: {media.media_type}
- Année: {media.year}

NOM TORRENT: {torrent.name}

Format attendu:
- Film: "Nom du Film (Année)"
- Série: "Nom de la Série (Année)/Season XX/Nom de la Série (Année) - SXXEXX - Titre Episode"
"""
            }
        ]

        try:
            response = await self._chat_completion(messages)
            return response.strip().strip('"\'')
        except Exception as e:
            logger.error(f"AI naming error: {e}")
            year = f" ({media.year})" if media.year else ""
            return f"{self._sanitize_filename(media.title)}{year}"

    def _extract_season_episode(self, filename: str) -> Optional[tuple]:
        """Extract season and episode from filename."""
        patterns = [
            r'S(\d{1,2})E(\d{1,3})',
            r'S(\d{1,2})\.E(\d{1,3})',
            r'(\d{1,2})x(\d{1,3})',
            r'Season[\s._-]?(\d{1,2})[\s._-]?Episode[\s._-]?(\d{1,3})',
            r'\[?(\d{1,2})\]?\s*-\s*\[?(\d{1,3})\]?',  # Some anime formats
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
    # VISION CAPABILITIES (Qwen3-VL)
    # =========================================================================

    async def analyze_image(
        self,
        image_path: str,
        prompt: str
    ) -> str:
        """
        Analyze an image using Qwen3-VL vision capabilities.

        Args:
            image_path: Path to the image file
            prompt: Question or instruction about the image

        Returns:
            AI analysis of the image
        """
        if not await self.is_available():
            return "Service IA non disponible"

        # Read and encode image
        try:
            path = Path(image_path)
            if not path.exists():
                return f"Image non trouvée: {image_path}"

            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            # Determine media type
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
            {
                "role": "user",
                "content": [
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
            }
        ]

        try:
            return await self._chat_completion(messages)
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return f"Erreur analyse: {e}"

    async def analyze_image_url(
        self,
        image_url: str,
        prompt: str
    ) -> str:
        """
        Analyze an image from URL using Qwen3-VL vision capabilities.

        Args:
            image_url: URL of the image
            prompt: Question or instruction about the image

        Returns:
            AI analysis of the image
        """
        if not await self.is_available():
            return "Service IA non disponible"

        messages = [
            {
                "role": "user",
                "content": [
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
            }
        ]

        try:
            return await self._chat_completion(messages)
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return f"Erreur analyse: {e}"

    # =========================================================================
    # LLAMA.CPP API (OpenAI-compatible)
    # =========================================================================

    async def _chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        """
        Query llama.cpp using OpenAI-compatible chat completions API.

        Args:
            messages: List of chat messages
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        config = await self._get_config()

        if not config.get("url"):
            raise ValueError("AI service URL not configured")

        url = config["url"]
        model = config.get("model", self.DEFAULT_MODEL)
        api_key = config.get("api_key")
        timeout = config.get("timeout", self.DEFAULT_TIMEOUT)

        logger.info(f"[AI] Querying llama.cpp at: {url}")
        logger.info(f"[AI] Model: {model}")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        try:
            logger.info(f"[AI] Sending request to llama.cpp (timeout: {timeout}s)...")

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{url}/v1/chat/completions",
                    headers=headers,
                    json=payload
                )

            logger.info(f"[AI] llama.cpp response status: {response.status_code}")
            response.raise_for_status()

            data = response.json()

            # Extract response content
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("No choices in response")

            content = choices[0].get("message", {}).get("content", "")

            # Strip <think>...</think> tags from qwen3 responses
            if "<think>" in content:
                content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE)
                content = content.strip()
                logger.info(f"[AI] Stripped thinking tags, remaining: {len(content)} chars")

            logger.info(f"[AI] Response: {content[:200]}..." if len(content) > 200 else f"[AI] Response: {content}")

            return content

        except httpx.HTTPStatusError as e:
            logger.error(f"[AI] llama.cpp HTTP error: {e.response.status_code}")
            logger.error(f"[AI] Response body: {e.response.text[:500]}")
            raise
        except httpx.TimeoutException:
            logger.error(f"[AI] llama.cpp request timed out after {timeout} seconds")
            raise
        except Exception as e:
            logger.error(f"[AI] llama.cpp error: {e}")
            import traceback
            logger.error(f"[AI] Traceback: {traceback.format_exc()}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if llama.cpp is available and get model info.

        Returns:
            Dict with status, available models, etc.
        """
        config = await self._get_config()

        if not config.get("url"):
            return {
                "available": False,
                "error": "URL non configurée"
            }

        if not config.get("is_enabled", True):
            return {
                "available": False,
                "error": "Service désactivé"
            }

        url = config["url"]
        api_key = config.get("api_key")

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{url}/v1/models",
                    headers=headers
                )

            if response.status_code == 200:
                data = response.json()
                models = [m.get("id") for m in data.get("data", [])]
                return {
                    "available": True,
                    "models": models,
                    "configured_model": config.get("model", self.DEFAULT_MODEL)
                }
            else:
                return {
                    "available": False,
                    "error": f"HTTP {response.status_code}"
                }

        except httpx.TimeoutException:
            return {
                "available": False,
                "error": "Timeout"
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }


# Singleton instance
_llama_cpp_service: Optional[LlamaCppService] = None


def get_llama_cpp_service() -> LlamaCppService:
    """Get llama.cpp service instance (singleton)."""
    global _llama_cpp_service
    if _llama_cpp_service is None:
        _llama_cpp_service = LlamaCppService()
    return _llama_cpp_service
