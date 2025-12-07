"""
File renaming service for Plex/Filebot compatible naming.
"""
import os
import re
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from ..models.request import MediaType
from .settings_service import get_settings_service

logger = logging.getLogger(__name__)


class FileRenamerService:
    """
    File management for:
    - Renaming to Plex/Filebot format
    - Moving to appropriate library
    - Handling season/episode detection
    """
    
    # Video file extensions
    VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    
    # Subtitle extensions
    SUBTITLE_EXTENSIONS = {'.srt', '.ass', '.ssa', '.sub', '.idx', '.vtt'}
    
    def __init__(self):
        self._settings_service = get_settings_service()
    
    def process_download(
        self,
        download_path: str,
        media_type: MediaType,
        media_title: str,
        year: Optional[int] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process a completed download:
        1. Detect video files
        2. Rename to Plex format
        3. Move to appropriate library
        
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
        
        try:
            # Find video files
            video_files = self._find_video_files(download_path)
            
            if not video_files:
                return {"success": False, "error": "No video files found"}
            
            processed_files = []
            final_path = None
            
            # Process based on media type
            if media_type == MediaType.MOVIE or media_type == MediaType.ANIMATED_MOVIE:
                result = self._process_movie(
                    video_files[0],  # Use first/largest video
                    library_path,
                    media_title,
                    year
                )
                processed_files.append(result)
                final_path = result.get("final_path")
            else:
                # Series/Anime - process all episodes
                for video_file in video_files:
                    result = self._process_episode(
                        video_file,
                        library_path,
                        media_title,
                        year,
                        season,
                        episode
                    )
                    processed_files.append(result)
                    if result.get("final_path"):
                        final_path = Path(result["final_path"]).parent
            
            return {
                "success": all(f.get("success") for f in processed_files),
                "final_path": str(final_path) if final_path else None,
                "files_processed": processed_files
            }
        except Exception as e:
            logger.error(f"Error processing download: {e}")
            return {"success": False, "error": str(e)}
    
    def _process_movie(
        self,
        video_path: Path,
        library_path: str,
        title: str,
        year: Optional[int]
    ) -> Dict[str, Any]:
        """Process a movie file."""
        # Clean title
        clean_title = self._sanitize_filename(title)
        year_str = f" ({year})" if year else ""
        
        # Create folder name: "Movie Name (Year)"
        folder_name = f"{clean_title}{year_str}"
        target_folder = Path(library_path) / folder_name
        target_folder.mkdir(parents=True, exist_ok=True)
        
        # New filename: "Movie Name (Year).ext"
        new_name = f"{clean_title}{year_str}{video_path.suffix}"
        target_path = target_folder / new_name
        
        try:
            shutil.move(str(video_path), str(target_path))
            
            # Also move subtitles if present
            self._move_subtitles(video_path, target_folder, clean_title, year_str)
            
            logger.info(f"Moved movie to: {target_path}")
            return {"success": True, "final_path": str(target_path), "original": str(video_path)}
        except Exception as e:
            return {"success": False, "error": str(e), "original": str(video_path)}
    
    def _process_episode(
        self,
        video_path: Path,
        library_path: str,
        show_title: str,
        year: Optional[int],
        forced_season: Optional[int] = None,
        forced_episode: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process a series episode file."""
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
            # Try to extract episode from filename numbers
            episode = self._extract_episode_number(video_path.name) or 1
        
        # Clean title
        clean_title = self._sanitize_filename(show_title)
        year_str = f" ({year})" if year else ""
        
        # Create folder structure: "Show Name (Year)/Season XX/"
        show_folder = f"{clean_title}{year_str}"
        season_folder = f"Season {season:02d}"
        target_folder = Path(library_path) / show_folder / season_folder
        target_folder.mkdir(parents=True, exist_ok=True)
        
        # New filename: "Show Name (Year) - SxxExx.ext"
        new_name = f"{clean_title}{year_str} - S{season:02d}E{episode:02d}{video_path.suffix}"
        target_path = target_folder / new_name
        
        try:
            shutil.move(str(video_path), str(target_path))
            logger.info(f"Moved episode to: {target_path}")
            return {
                "success": True,
                "final_path": str(target_path),
                "original": str(video_path),
                "season": season,
                "episode": episode
            }
        except Exception as e:
            return {"success": False, "error": str(e), "original": str(video_path)}
    
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
        title: str,
        year_str: str
    ):
        """Move associated subtitle files."""
        video_stem = video_path.stem
        parent = video_path.parent
        
        for item in parent.iterdir():
            if item.suffix.lower() in self.SUBTITLE_EXTENSIONS:
                # Check if subtitle is for this video
                if video_stem in item.stem or item.stem.startswith(video_stem):
                    # Determine language suffix
                    lang = ""
                    for lang_code in [".fr", ".en", ".vf", ".vostfr", ".french", ".english"]:
                        if lang_code in item.stem.lower():
                            lang = lang_code
                            break
                    
                    new_sub_name = f"{title}{year_str}{lang}{item.suffix}"
                    try:
                        shutil.move(str(item), str(target_folder / new_sub_name))
                        logger.info(f"Moved subtitle: {new_sub_name}")
                    except Exception as e:
                        logger.warning(f"Failed to move subtitle {item}: {e}")
    
    def _sanitize_filename(self, name: str) -> str:
        """Remove invalid filename characters."""
        # Windows-invalid characters
        invalid_chars = '<>:"/\\|?*'
        result = name
        for char in invalid_chars:
            result = result.replace(char, '')
        
        # Remove trailing dots/spaces
        result = result.strip('. ')
        
        return result
    
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
