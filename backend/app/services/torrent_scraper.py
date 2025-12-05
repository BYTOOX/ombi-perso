"""
YGGtorrent scraper with FlareSolverr for Cloudflare bypass.
"""
import re
import logging
from typing import List, Optional, Any
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup

from ..config import get_settings
from ..schemas.media import TorrentResult

logger = logging.getLogger(__name__)


class TorrentScraperService:
    """
    YGGtorrent scraper with FlareSolverr integration.
    Handles Cloudflare bypass and session management.
    """
    
    YGG_BASE_URL = "https://www.yggtorrent.wtf"
    
    # Category mappings
    CATEGORIES = {
        "movie": "2145",          # Films
        "animated_movie": "2178", # Films d'animation
        "series": "2184",         # Séries TV
        "animated_series_us": "2182",  # Séries animées US
        "anime": "2179"           # Anime
    }
    
    # Quality patterns for parsing
    QUALITY_PATTERNS = [
        (r"4K|2160p", "4K"),
        (r"1080p|FHD", "1080p"),
        (r"720p|HD", "720p"),
        (r"480p|SD", "480p"),
    ]
    
    # Release group patterns
    RELEASE_GROUPS = [
        "SubsPlease", "Erai-raws", "Judas", "Commie", "HorribleSubs",
        "SPARKS", "GECKOS", "FGT", "AMIABLE", "EXTRATORRENT",
        "YTS", "YIFY", "RARBG", "NTb", "NTG", "AMZN", "FLUX"
    ]
    
    def __init__(self):
        self.settings = get_settings()
        self._session_cookie: Optional[str] = None
        self._cf_clearance: Optional[str] = None
        self._user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
    
    async def search(
        self,
        query: str,
        media_type: Optional[str] = None,
        page: int = 0
    ) -> List[TorrentResult]:
        """
        Search YGGtorrent for torrents.
        
        Args:
            query: Search query
            media_type: Optional category filter
            page: Page number (0-indexed)
            
        Returns:
            List of torrent results
        """
        # Build search URL
        category = ""
        if media_type and media_type in self.CATEGORIES:
            category = f"&category={self.CATEGORIES[media_type]}"
        
        search_url = f"{self.YGG_BASE_URL}/engine/search?name={quote_plus(query)}{category}&do=search&page={page * 25}"
        
        try:
            # Get page via FlareSolverr
            html = await self._fetch_with_flaresolverr(search_url)
            if not html:
                return []
            
            # Parse results
            return self._parse_search_results(html)
        except Exception as e:
            logger.error(f"Torrent search error: {e}")
            return []
    
    async def get_torrent_url(self, torrent_id: str) -> Optional[str]:
        """
        Get direct download URL for a torrent.
        Uses passkey if available.
        """
        if self.settings.ygg_passkey:
            return f"{self.YGG_BASE_URL}/engine/download_torrent?id={torrent_id}&passkey={self.settings.ygg_passkey}"
        
        # Otherwise need to login and get from page
        return await self._get_authenticated_download_url(torrent_id)
    
    async def _fetch_with_flaresolverr(self, url: str) -> Optional[str]:
        """Fetch URL using FlareSolverr to bypass Cloudflare."""
        if not self.settings.flaresolverr_url:
            logger.error("FlareSolverr URL not configured")
            return None
        
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000
        }
        
        # Add existing cookies if we have them
        if self._cf_clearance:
            payload["cookies"] = [
                {"name": "cf_clearance", "value": self._cf_clearance}
            ]
        
        async with httpx.AsyncClient(timeout=70.0) as client:
            try:
                response = await client.post(
                    self.settings.flaresolverr_url,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "ok":
                    # Store cookies for future requests
                    for cookie in data.get("solution", {}).get("cookies", []):
                        if cookie.get("name") == "cf_clearance":
                            self._cf_clearance = cookie.get("value")
                    
                    return data.get("solution", {}).get("response")
                else:
                    logger.error(f"FlareSolverr error: {data.get('message')}")
                    return None
            except Exception as e:
                logger.error(f"FlareSolverr request failed: {e}")
                return None
    
    async def _login_if_needed(self) -> bool:
        """Login to YGGtorrent if not already logged in."""
        if self._session_cookie:
            return True
        
        if not self.settings.ygg_username or not self.settings.ygg_password:
            logger.warning("YGG credentials not configured")
            return False
        
        login_url = f"{self.YGG_BASE_URL}/user/login"
        
        payload = {
            "cmd": "request.post",
            "url": login_url,
            "maxTimeout": 60000,
            "postData": f"id={quote_plus(self.settings.ygg_username)}&pass={quote_plus(self.settings.ygg_password)}"
        }
        
        async with httpx.AsyncClient(timeout=70.0) as client:
            try:
                response = await client.post(
                    self.settings.flaresolverr_url,
                    json=payload
                )
                data = response.json()
                
                if data.get("status") == "ok":
                    for cookie in data.get("solution", {}).get("cookies", []):
                        if cookie.get("name") == "ygg_":
                            self._session_cookie = cookie.get("value")
                            return True
                
                logger.error("YGG login failed")
                return False
            except Exception as e:
                logger.error(f"YGG login error: {e}")
                return False
    
    async def _get_authenticated_download_url(self, torrent_id: str) -> Optional[str]:
        """Get download URL with authentication."""
        if not await self._login_if_needed():
            return None
        
        # This would return the authenticated URL
        # For now, return passkey URL which is simpler
        return None
    
    def _parse_search_results(self, html: str) -> List[TorrentResult]:
        """Parse YGGtorrent search results HTML."""
        soup = BeautifulSoup(html, "lxml")
        results = []
        
        table = soup.find("table", class_="table")
        if not table:
            return results
        
        rows = table.find_all("tr")[1:]  # Skip header
        
        for row in rows:
            try:
                result = self._parse_torrent_row(row)
                if result:
                    results.append(result)
            except Exception as e:
                logger.debug(f"Error parsing row: {e}")
                continue
        
        return results
    
    def _parse_torrent_row(self, row) -> Optional[TorrentResult]:
        """Parse a single torrent row."""
        cells = row.find_all("td")
        if len(cells) < 6:
            return None
        
        # Name and link
        name_cell = cells[1]
        link = name_cell.find("a")
        if not link:
            return None
        
        name = link.get_text(strip=True)
        href = link.get("href", "")
        
        # Extract ID from href
        torrent_id = ""
        id_match = re.search(r"/torrent/(\d+)/", href)
        if id_match:
            torrent_id = id_match.group(1)
        
        # Size
        size_text = cells[5].get_text(strip=True)
        size_bytes = self._parse_size(size_text)
        
        # Seeders/leechers
        seeders = self._parse_int(cells[7].get_text(strip=True)) if len(cells) > 7 else 0
        leechers = self._parse_int(cells[8].get_text(strip=True)) if len(cells) > 8 else 0
        
        # Date
        date_text = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        upload_date = self._parse_date(date_text)
        
        # Analyze name for quality and release group
        quality = self._detect_quality(name)
        release_group = self._detect_release_group(name)
        has_french = self._detect_french(name)
        
        return TorrentResult(
            id=torrent_id,
            name=name,
            size_bytes=size_bytes,
            size_human=size_text,
            seeders=seeders,
            leechers=leechers,
            upload_date=upload_date,
            torrent_url=f"{self.YGG_BASE_URL}{href}" if href.startswith("/") else href,
            quality=quality,
            release_group=release_group,
            has_french_audio=has_french,
            has_french_subs=has_french
        )
    
    def _parse_size(self, size_text: str) -> int:
        """Parse size string to bytes."""
        size_text = size_text.upper().replace(",", ".")
        
        multipliers = {
            "KO": 1024, "KB": 1024,
            "MO": 1024**2, "MB": 1024**2,
            "GO": 1024**3, "GB": 1024**3,
            "TO": 1024**4, "TB": 1024**4
        }
        
        for suffix, multiplier in multipliers.items():
            if suffix in size_text:
                try:
                    value = float(re.sub(r'[^\d.]', '', size_text.replace(suffix, '').strip()))
                    return int(value * multiplier)
                except ValueError:
                    pass
        
        return 0
    
    def _parse_int(self, text: str) -> int:
        """Parse integer from string."""
        try:
            return int(re.sub(r'[^\d]', '', text))
        except ValueError:
            return 0
    
    def _parse_date(self, date_text: str) -> Optional[Any]:
        """Parse date from YGG format."""
        try:
            # YGG uses format like "09/01/2024" or timestamps
            if "/" in date_text:
                from datetime import datetime
                return datetime.strptime(date_text, "%d/%m/%Y").date()
        except Exception:
            pass
        return None
    
    def _detect_quality(self, name: str) -> Optional[str]:
        """Detect video quality from torrent name."""
        name_upper = name.upper()
        for pattern, quality in self.QUALITY_PATTERNS:
            if re.search(pattern, name_upper):
                return quality
        return None
    
    def _detect_release_group(self, name: str) -> Optional[str]:
        """Detect release group from torrent name."""
        for group in self.RELEASE_GROUPS:
            if group.lower() in name.lower():
                return group
        
        # Try to extract from brackets
        match = re.search(r'\[([^\]]+)\]', name)
        if match:
            return match.group(1)
        
        return None
    
    def _detect_french(self, name: str) -> bool:
        """Detect if torrent has French audio/subs."""
        name_lower = name.lower()
        french_indicators = [
            "french", "français", "vff", "vfi", "vf2", "truefrench",
            "vostfr", "multi", "french", "fr"
        ]
        return any(ind in name_lower for ind in french_indicators)


def get_torrent_scraper_service() -> TorrentScraperService:
    """Get torrent scraper service instance."""
    return TorrentScraperService()
