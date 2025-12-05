"""
AI Agent using Ollama/Qwen for intelligent torrent selection and anime name resolution.
Optimized for Qwen 14B.
"""
import json
import logging
import re
from typing import List, Optional, Dict, Any
import httpx

from ..config import get_settings
from ..schemas.media import TorrentResult, MediaSearchResult

logger = logging.getLogger(__name__)


class AIAgentService:
    """
    AI-powered service for:
    - Torrent scoring and selection
    - Anime name resolution (romaji/kanji → English)
    - Filebot-compatible naming generation
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120.0)  # AI can be slow
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
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
            return []
        
        # For small lists, use simpler scoring
        if len(torrents) <= 3:
            return self._simple_score_torrents(torrents, quality_preference)
        
        # Use AI for larger lists
        prompt = self._build_scoring_prompt(media, torrents, quality_preference)
        
        try:
            response = await self._query_ollama(prompt)
            scored_torrents = self._parse_scoring_response(response, torrents)
            return sorted(scored_torrents, key=lambda t: t.ai_score or 0, reverse=True)
        except Exception as e:
            logger.error(f"AI scoring error: {e}")
            return self._simple_score_torrents(torrents, quality_preference)
    
    async def select_best_torrent(
        self,
        media: MediaSearchResult,
        torrents: List[TorrentResult],
        quality_preference: str = "1080p"
    ) -> Optional[TorrentResult]:
        """Select the best torrent from the list."""
        scored = await self.score_torrents(media, torrents, quality_preference)
        return scored[0] if scored else None
    
    def _build_scoring_prompt(
        self,
        media: MediaSearchResult,
        torrents: List[TorrentResult],
        quality_preference: str
    ) -> str:
        """Build scoring prompt for Ollama."""
        torrents_text = "\n".join([
            f"{i+1}. {t.name} | {t.size_human} | {t.seeders} seeders | {t.quality or 'unknown'}"
            for i, t in enumerate(torrents[:10])  # Limit to 10
        ])
        
        return f"""Tu es un expert en sélection de torrents pour une médiathèque Plex.

MÉDIA RECHERCHÉ:
- Titre: {media.title}
- Type: {media.media_type}
- Année: {media.year or 'inconnue'}

PRÉFÉRENCE QUALITÉ: {quality_preference}

TORRENTS DISPONIBLES:
{torrents_text}

RÈGLES DE SCORING:
- Préférer les groupes reconnus (SubsPlease, Erai-raws, Judas, SPARKS, GECKOS)
- {quality_preference} prioritaire, sinon qualité supérieure
- HEVC/x265 préféré (meilleure compression)
- Éviter les versions CAM, TS, HDTS
- Seeders > 5 minimum
- VOSTFR ou MULTI préféré pour l'audio français
- Batch complet mieux que épisodes séparés pour les séries

Réponds UNIQUEMENT avec un JSON (pas de texte avant/après):
{{
  "rankings": [
    {{"index": 1, "score": 95, "reason": "raison courte"}},
    {{"index": 2, "score": 80, "reason": "raison courte"}}
  ]
}}
"""
    
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
        prompt = f"""Tu es un expert en anime. Pour l'anime suivant, fournis les variations de nom pour la recherche de torrents.

ANIME:
- Titre affiché: {anime.title}
- Titre original: {anime.original_title or 'N/A'}
- Romaji: {anime.romaji_title or 'N/A'}
- Année: {anime.year or 'inconnue'}

Réponds UNIQUEMENT avec un JSON:
{{
  "search_terms": ["terme1", "terme2", "terme3"],
  "english_title": "titre anglais officiel",
  "romanized": "titre romanisé",
  "alternative_names": ["nom alt 1", "nom alt 2"]
}}
"""
        
        try:
            response = await self._query_ollama(prompt)
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
        prompt = f"""Génère un nom de fichier/dossier compatible Plex pour ce média.

MÉDIA:
- Titre: {media.title}
- Type: {media.media_type}
- Année: {media.year}

NOM TORRENT: {torrent.name}

Format attendu:
- Film: "Nom du Film (Année)"
- Série: "Nom de la Série (Année)/Season XX/Nom de la Série (Année) - SXXEXX - Titre Episode"

Réponds UNIQUEMENT avec le chemin, rien d'autre.
"""
        
        try:
            response = await self._query_ollama(prompt)
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
    # OLLAMA API
    # =========================================================================
    
    async def _query_ollama(self, prompt: str) -> str:
        """Query Ollama API."""
        if not self.settings.ollama_url:
            raise ValueError("Ollama URL not configured")
        
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Lower for more deterministic output
                "num_predict": 500
            }
        }
        
        try:
            response = await self.client.post(
                f"{self.settings.ollama_url}/api/generate",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = await self.client.get(f"{self.settings.ollama_url}/api/tags")
            return response.status_code == 200
        except:
            return False


def get_ai_agent_service() -> AIAgentService:
    """Get AI agent service instance."""
    return AIAgentService()
