"""
Enhanced File Renaming Service for Plex/Filebot compatible naming.
Integrates with TitleResolverService and configurable settings.
"""
import os
import re
import shutil
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List

from ..models.request import MediaType
from .settings_service import get_settings_service
from .title_resolver import get_title_resolver_service

logger = logging.getLogger(__name__)


class FileRenamerService:
    """
    Enhanced file management for:
    - Renaming to Plex/Filebot format using configurable templates
    - Title resolution via TMDB/TVDB
    - Moving to appropriate library
    - Handling season/episode detection
    - AI fallback for ambiguous cases
    """
    
    # Video file extensions
    VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    
    # Subtitle extensions
    SUBTITLE_EXTENSIONS = {'.srt', '.ass', '.ssa', '.sub', '.idx', '.vtt'}
    
    # Audio priority patterns for torrent selection (MULTI > VF > VOSTFR)
    AUDIO_PRIORITY = [
        (r'\b(MULTI|TRUEFRENCH)\b', 100),  # Multi-language with French
        (r'\bVF\s*F?\b', 80),               # French dubbing
        (r'\b(VOSTFR|SUBFRENCH)\b', 60),   # French subtitles
        (r'\b(VO|ENGLISH)\b', 40),          # Original/English only
    ]
    
    def __init__(self):
        self._settings_service = get_settings_service()
        self._title_resolver = get_title_resolver_service()
    
    def process_download(
        self,
        download_path: str,
        media_type: MediaType,
        media_title: str,
        year: Optional[int] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process a completed download:
        1. Detect video files
        2. Resolve title via TMDB/TVDB if needed
        3. Apply configurable naming template
        4. Move to appropriate library
        
        Returns:
            Dict with 'success', 'final_path', 'files_processed'
        """
        download_path = Path(download_path)
        
        if not download_path.exists():
            return {"success": False, "error": f"Path not found: {download_path}"}
        
        # Get target library path from database settings
        library_path = self._settings_service.get_library_path(media_type.value)
        if not library_path:
            return {"success": False, "error": f"No library configured for type: {media_type.value}"}
        
        # Get rename settings
        rename_settings = self._settings_service.get_rename_settings()
        
        try:
            # Find video files
            video_files = self._find_video_files(download_path)
            
            if not video_files:
                return {"success": False, "error": "No video files found"}
            
            # Resolve title if not provided with IDs
            resolved_info = self._resolve_title(
                media_title, year, media_type, tmdb_id, tvdb_id
            )
            
            processed_files = []
            final_path = None
            
            # Process based on media type
            if media_type == MediaType.MOVIE or media_type == MediaType.ANIMATED_MOVIE:
                result = self._process_movie(
                    video_files[0],  # Use first/largest video
                    library_path,
                    resolved_info,
                    rename_settings
                )
                processed_files.append(result)
                final_path = result.get("final_path")
            else:
                # Series/Anime - process all episodes
                for video_file in video_files:
                    result = self._process_episode(
                        video_file,
                        library_path,
                        resolved_info,
                        rename_settings,
                        media_type,
                        season,
                        episode
                    )
                    processed_files.append(result)
                    if result.get("final_path"):
                        final_path = Path(result["final_path"]).parent
            
            return {
                "success": all(f.get("success") for f in processed_files),
                "final_path": str(final_path) if final_path else None,
                "files_processed": processed_files,
                "resolved_title": resolved_info.get("title"),
                "resolution_source": resolved_info.get("source")
            }
        except Exception as e:
            logger.error(f"Error processing download: {e}")
            return {"success": False, "error": str(e)}
    
    def _resolve_title(
        self,
        title: str,
        year: Optional[int],
        media_type: MediaType,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Resolve title using TitleResolver or return provided info."""
        
        # If we already have IDs, just build the info dict
        if tmdb_id or tvdb_id:
            return {
                "title": title,
                "year": year,
                "tmdb_id": tmdb_id,
                "tvdb_id": tvdb_id,
                "source": "provided",
                "confidence": 1.0
            }
        
        # Try to resolve via TMDB/TVDB
        try:
            if media_type == MediaType.MOVIE or media_type == MediaType.ANIMATED_MOVIE:
                resolved = asyncio.get_event_loop().run_until_complete(
                    self._title_resolver.resolve_title(title, "movie", year, tmdb_id)
                )
            elif media_type == MediaType.ANIME or media_type == MediaType.ANIME_MOVIE:
                resolved = asyncio.get_event_loop().run_until_complete(
                    self._title_resolver.resolve_title(title, "anime", year, tmdb_id, tvdb_id)
                )
            else:
                resolved = asyncio.get_event_loop().run_until_complete(
                    self._title_resolver.resolve_title(title, "series", year, tmdb_id, tvdb_id)
                )
            
            if resolved.get("confidence", 0) > 0.5:
                return resolved
        except Exception as e:
            logger.warning(f"Title resolution failed: {e}")
        
        # Fallback to provided title
        return {
            "title": title,
            "year": year,
            "tmdb_id": None,
            "tvdb_id": None,
            "source": "fallback",
            "confidence": 0.3
        }
    
    def _process_movie(
        self,
        video_path: Path,
        library_path: str,
        resolved_info: Dict[str, Any],
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a movie file with configurable template."""
        title = resolved_info.get("title", "Unknown")
        year = resolved_info.get("year")
        tmdb_id = resolved_info.get("tmdb_id")
        
        # Clean title
        clean_title = self._sanitize_filename(title, settings.get("replace_special_chars", False))
        
        # Build folder and filename from template
        template = settings.get("movie_format", "{title} ({year})")
        
        folder_name = self._apply_template(template, {
            "title": clean_title,
            "year": year or "",
        })
        
        # Add TMDB ID if configured
        if settings.get("include_tmdb_id") and tmdb_id:
            folder_name = f"{folder_name} {{tmdb-{tmdb_id}}}"
        
        target_folder = Path(library_path) / folder_name
        target_folder.mkdir(parents=True, exist_ok=True)
        
        # New filename
        new_name = f"{folder_name}{video_path.suffix}"
        target_path = target_folder / new_name
        
        try:
            logger.info(f"📁 Renaming movie:")
            logger.info(f"   FROM: {video_path}")
            logger.info(f"   TO:   {target_path}")
            shutil.move(str(video_path), str(target_path))
            
            # Also move subtitles if present (French only as per settings)
            self._move_subtitles(video_path, target_folder, folder_name)
            
            logger.info(f"✅ Moved movie successfully: {target_path}")
            return {
                "success": True,
                "final_path": str(target_path),
                "original": str(video_path),
                "resolved_title": title
            }
        except Exception as e:
            return {"success": False, "error": str(e), "original": str(video_path)}
    
    def _process_episode(
        self,
        video_path: Path,
        library_path: str,
        resolved_info: Dict[str, Any],
        settings: Dict[str, Any],
        media_type: MediaType,
        forced_season: Optional[int] = None,
        forced_episode: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process a series episode file with configurable template."""
        title = resolved_info.get("title", "Unknown")
        year = resolved_info.get("year")
        tvdb_id = resolved_info.get("tvdb_id")
        
        # Extract season/episode from filename
        season, episode = self._extract_season_episode(video_path.name)
        
        # Override if provided
        if forced_season is not None:
            season = forced_season
        if forced_episode is not None:
            episode = forced_episode
        
        # Default to season 1 if not found
        if season is None:
            season = 1
        if episode is None:
            episode = self._extract_episode_number(video_path.name) or 1
        
        # Clean title - for anime, apply title preference
        if media_type in [MediaType.ANIME, MediaType.ANIMATED_MOVIE]:
            # Could apply anime title preference here if we had alt titles
            pass
        
        clean_title = self._sanitize_filename(title, settings.get("replace_special_chars", False))
        
        # Get appropriate template
        if media_type in [MediaType.ANIME, MediaType.ANIMATED_MOVIE]:
            template = settings.get("anime_format", "{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}")
        else:
            template = settings.get("series_format", "{title} ({year})/Season {season:02d}/{title} ({year}) - S{season:02d}E{episode:02d}")
        
        # Parse template to get folder and file parts
        template_parts = template.split("/")
        
        vars_dict = {
            "title": clean_title,
            "year": year or "",
            "season": season,
            "episode": episode,
        }
        
        # Build folder path
        show_folder = self._apply_template(template_parts[0], vars_dict)
        season_folder = self._apply_template(template_parts[1], vars_dict) if len(template_parts) > 1 else f"Season {season:02d}"
        
        # Add TVDB ID if configured
        if settings.get("include_tvdb_id") and tvdb_id:
            show_folder = f"{show_folder} {{tvdb-{tvdb_id}}}"
        
        target_folder = Path(library_path) / show_folder / season_folder
        target_folder.mkdir(parents=True, exist_ok=True)
        
        # Build filename
        filename_template = template_parts[-1] if len(template_parts) > 2 else f"{{title}} ({{year}}) - S{{season:02d}}E{{episode:02d}}"
        new_name = self._apply_template(filename_template, vars_dict) + video_path.suffix
        target_path = target_folder / new_name
        
        try:
            logger.info(f"📁 Renaming episode:")
            logger.info(f"   FROM: {video_path}")
            logger.info(f"   TO:   {target_path}")
            shutil.move(str(video_path), str(target_path))
            logger.info(f"✅ Moved episode successfully: {target_path}")
            return {
                "success": True,
                "final_path": str(target_path),
                "original": str(video_path),
                "season": season,
                "episode": episode,
                "resolved_title": title
            }
        except Exception as e:
            return {"success": False, "error": str(e), "original": str(video_path)}
    
    def _apply_template(self, template: str, variables: Dict[str, Any]) -> str:
        """Apply variables to a template string."""
        result = template
        
        for key, value in variables.items():
            # Handle formatted placeholders like {season:02d}
            pattern = r'\{' + key + r'(?::([^}]+))?\}'
            
            def replacer(match):
                format_spec = match.group(1)
                if format_spec and isinstance(value, int):
                    return f"{value:{format_spec}}"
                return str(value) if value else ""
            
            result = re.sub(pattern, replacer, result)
        
        # Clean up empty parentheses
        result = re.sub(r'\s*\(\s*\)', '', result)
        result = re.sub(r'\s+', ' ', result).strip()
        
        return result
    
    def _find_video_files(self, path: Path) -> List[Path]:
        """Find all video files in a path."""
        video_files = []
        
        if path.is_file():
            if path.suffix.lower() in self.VIDEO_EXTENSIONS:
                return [path]
            return []
        
        # Walk directory
        for item in path.rglob("*"):
            if item.is_file() and item.suffix.lower() in self.VIDEO_EXTENSIONS:
                # Skip sample files
                if "sample" in item.name.lower():
                    continue
                video_files.append(item)
        
        # Sort by size (largest first - usually the main video)
        video_files.sort(key=lambda f: f.stat().st_size, reverse=True)
        
        return video_files
    
    def _extract_season_episode(self, filename: str) -> tuple:
        """Extract season and episode numbers from filename."""
        patterns = [
            r'[Ss](\d{1,2})[Ee](\d{1,3})',       # S01E01
            r'[Ss](\d{1,2})\.?[Ee](\d{1,3})',    # S01.E01
            r'(\d{1,2})[xX](\d{1,3})',            # 1x01
            r'Season\s*(\d{1,2}).*Episode\s*(\d{1,3})',  # Season 1 Episode 1
            r'\[(\d{1,2})\]\s*-?\s*\[?(\d{1,3})\]?',     # [01] - [01]
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        
        return (None, None)
    
    def _extract_episode_number(self, filename: str) -> Optional[int]:
        """Try to extract just episode number from filename."""
        # For anime that use just episode numbers like [01] or - 01 -
        patterns = [
            r'[\[\s-](\d{2,3})[\]\s-]',
            r'Episode\s*(\d{1,3})',
            r'Ep\.?\s*(\d{1,3})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return None
    
    def _move_subtitles(
        self,
        video_path: Path,
        target_folder: Path,
        base_name: str
    ):
        """Move associated subtitle files (French only)."""
        video_stem = video_path.stem
        parent = video_path.parent
        
        for item in parent.iterdir():
            if item.suffix.lower() in self.SUBTITLE_EXTENSIONS:
                # Check if subtitle is for this video
                if video_stem in item.stem or item.stem.startswith(video_stem):
                    # Only keep French subtitles
                    item_lower = item.stem.lower()
                    is_french = any(x in item_lower for x in ['.fr', '.french', '.vf', '.vostfr', 'french', 'fra'])
                    
                    if is_french or len(list(parent.glob(f"*{item.suffix}"))) == 1:
                        # Determine language suffix
                        lang = ".fr" if is_french else ""
                        new_sub_name = f"{base_name}{lang}{item.suffix}"
                        try:
                            shutil.move(str(item), str(target_folder / new_sub_name))
                            logger.info(f"Moved subtitle: {new_sub_name}")
                        except Exception as e:
                            logger.warning(f"Failed to move subtitle {item}: {e}")
    
    def _sanitize_filename(self, name: str, replace_special: bool = False) -> str:
        """Remove invalid filename characters."""
        # Windows-invalid characters
        invalid_chars = '<>:"/\\|?*'
        result = name
        for char in invalid_chars:
            result = result.replace(char, '')
        
        # Optionally replace special characters
        if replace_special:
            special_map = {
                'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
                'à': 'a', 'â': 'a', 'ä': 'a',
                'î': 'i', 'ï': 'i',
                'ô': 'o', 'ö': 'o',
                'ù': 'u', 'û': 'u', 'ü': 'u',
                'ç': 'c', 'ñ': 'n',
            }
            for special, replacement in special_map.items():
                result = result.replace(special, replacement)
        
        # Remove trailing dots/spaces
        result = result.strip('. ')
        
        return result
    
    def get_audio_priority_score(self, torrent_name: str) -> int:
        """
        Calculate audio priority score for torrent selection.
        Higher score = better match for MULTI > VF > VOSTFR preference.
        """
        for pattern, score in self.AUDIO_PRIORITY:
            if re.search(pattern, torrent_name, re.IGNORECASE):
                return score
        return 20  # Default low score for unknown
    
    def get_library_info(self) -> Dict[str, str]:
        """Get configured library paths from database."""
        return self._settings_service.get_library_paths()
    
    def verify_library_paths(self) -> Dict[str, Dict[str, Any]]:
        """Verify that configured library paths exist."""
        results = {}
        
        for media_type, path in self._settings_service.get_library_paths().items():
            p = Path(path)
            results[media_type] = {
                "path": path,
                "exists": p.exists(),
                "writable": p.exists() and os.access(p, os.W_OK)
            }
        
        return results


def get_file_renamer_service() -> FileRenamerService:
    """Get file renamer service instance."""
    return FileRenamerService()
