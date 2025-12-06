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
        self._session_cookie_name: str = "ygg_"  # Will be updated with actual name
        self._cf_clearance: Optional[str] = None
        self._user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        logger.info(f"[Scraper] Initialized with YGG URL: {self.settings.ygg_base_url}")
    
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
            logger.info(f"[Scraper] Using category filter: {media_type} -> {self.CATEGORIES[media_type]}")
        else:
            logger.info("[Scraper] No category filter applied")
        
        search_url = f"{self.settings.ygg_base_url}/engine/search?name={quote_plus(query)}{category}&do=search&page={page * 25}"
        logger.info(f"[Scraper] Search URL: {search_url}")
        
        try:
            # Login first if credentials are configured
            await self._login_if_needed()
            
            # Get page via FlareSolverr
            logger.info("[Scraper] Fetching page via FlareSolverr...")
            html = await self._fetch_with_flaresolverr(search_url)
            
            if not html:
                logger.warning("[Scraper] FlareSolverr returned no HTML")
                return []
            
            logger.info(f"[Scraper] Received HTML response ({len(html)} bytes)")
            
            # Check if we got redirected to login page
            if "/auth/login" in html or "Connexion" in html[:500]:
                logger.warning("[Scraper] Got login page - authentication may have failed")
                # Force re-login
                self._session_cookie = None
                self._cf_clearance = None
                await self._login_if_needed()
                # Retry search
                html = await self._fetch_with_flaresolverr(search_url)
                if not html:
                    return []
            
            # Parse results
            results = self._parse_search_results(html)
            logger.info(f"[Scraper] Parsed {len(results)} torrent results from HTML")
            
            return results
        except Exception as e:
            logger.error(f"[Scraper] Search error: {e}")
            import traceback
            logger.error(f"[Scraper] Traceback: {traceback.format_exc()}")
            return []
    
    async def get_torrent_url(self, torrent_id: str) -> Optional[str]:
        """
        Get direct download URL for a torrent.
        Uses passkey if available and valid, otherwise uses authenticated download.
        """
        # Check if passkey is configured and not a placeholder
        passkey = self.settings.ygg_passkey
        if passkey and passkey not in ['your_passkey', 'votre_passkey', '', None]:
            logger.info(f"[Scraper] Using passkey URL for torrent {torrent_id}")
            return f"{self.settings.ygg_base_url}/engine/download_torrent?id={torrent_id}&passkey={passkey}"
        
        # Otherwise need to login and get authenticated download URL
        logger.info(f"[Scraper] Using authenticated download for torrent {torrent_id}")
        return await self._get_authenticated_download_url(torrent_id)
    
    async def _fetch_with_flaresolverr(self, url: str) -> Optional[str]:
        """Fetch URL using FlareSolverr to bypass Cloudflare."""
        if not self.settings.flaresolverr_url:
            logger.error("[FlareSolverr] URL not configured in settings!")
            return None
        
        logger.info(f"[FlareSolverr] Sending request to: {self.settings.flaresolverr_url}")
        logger.info(f"[FlareSolverr] Target URL: {url}")
        
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000
        }
        
        # Add all cookies we have (cf_clearance and session)
        cookies_to_send = []
        if self._cf_clearance:
            cookies_to_send.append({"name": "cf_clearance", "value": self._cf_clearance})
            logger.info("[FlareSolverr] Adding cf_clearance cookie")
        if self._session_cookie:
            cookies_to_send.append({"name": self._session_cookie_name, "value": self._session_cookie})
            logger.info(f"[FlareSolverr] Adding YGG session cookie: {self._session_cookie_name}")
        
        if cookies_to_send:
            payload["cookies"] = cookies_to_send
            logger.info(f"[FlareSolverr] Total cookies: {len(cookies_to_send)}")
        else:
            logger.info("[FlareSolverr] No cached cookies available")
        
        async with httpx.AsyncClient(timeout=70.0) as client:
            try:
                logger.info("[FlareSolverr] Sending POST request (timeout: 70s)...")
                response = await client.post(
                    self.settings.flaresolverr_url,
                    json=payload
                )
                
                logger.info(f"[FlareSolverr] Response status: {response.status_code}")
                response.raise_for_status()
                data = response.json()
                
                status = data.get("status")
                logger.info(f"[FlareSolverr] Response status: {status}")
                
                if status == "ok":
                    solution = data.get("solution", {})
                    
                    # Log solution details
                    logger.info("[FlareSolverr] Solution received:")
                    logger.info(f"  - Status code: {solution.get('status')}")
                    logger.info(f"  - URL: {solution.get('url')}")
                    logger.info(f"  - Cookies: {len(solution.get('cookies', []))} cookies")
                    
                    # Store cookies for future requests
                    for cookie in solution.get("cookies", []):
                        if cookie.get("name") == "cf_clearance":
                            self._cf_clearance = cookie.get("value")
                            logger.info("[FlareSolverr] Stored new cf_clearance cookie")
                    
                    response_html = solution.get("response", "")
                    if response_html:
                        # Check if we got an actual search page or an error
                        if "Aucun résultat" in response_html or "No results" in response_html:
                            logger.warning("[FlareSolverr] Page indicates no results found")
                        elif "table" in response_html.lower():
                            logger.info("[FlareSolverr] Response contains table element (likely results)")
                        else:
                            logger.warning("[FlareSolverr] Response may not contain results table")
                            logger.debug(f"[FlareSolverr] First 500 chars: {response_html[:500]}")
                    
                    return response_html
                else:
                    message = data.get('message', 'Unknown error')
                    logger.error(f"[FlareSolverr] Error: {message}")
                    return None
                    
            except httpx.TimeoutException:
                logger.error("[FlareSolverr] Request timed out after 70 seconds")
                return None
            except httpx.HTTPStatusError as e:
                logger.error(f"[FlareSolverr] HTTP error: {e.response.status_code} - {e.response.text[:200]}")
                return None
            except Exception as e:
                logger.error(f"[FlareSolverr] Request failed: {e}")
                import traceback
                logger.error(f"[FlareSolverr] Traceback: {traceback.format_exc()}")
                return None
    
    async def _login_if_needed(self) -> bool:
        """Login to YGGtorrent if not already logged in."""
        if self._session_cookie:
            logger.info("[YGG Login] Already logged in (have session cookie)")
            return True
        
        if not self.settings.ygg_username or not self.settings.ygg_password:
            logger.warning("[YGG Login] Credentials not configured - skipping login")
            return False
        
        logger.info(f"[YGG Login] Attempting login as: {self.settings.ygg_username}")
        login_url = f"{self.settings.ygg_base_url}/user/login"
        logger.info(f"[YGG Login] Login URL: {login_url}")
        
        payload = {
            "cmd": "request.post",
            "url": login_url,
            "maxTimeout": 60000,
            "postData": f"id={quote_plus(self.settings.ygg_username)}&pass={quote_plus(self.settings.ygg_password)}"
        }
        
        # Add existing cf_clearance if we have it
        if self._cf_clearance:
            payload["cookies"] = [{"name": "cf_clearance", "value": self._cf_clearance}]
        
        async with httpx.AsyncClient(timeout=70.0) as client:
            try:
                logger.info("[YGG Login] Sending login request via FlareSolverr...")
                response = await client.post(
                    self.settings.flaresolverr_url,
                    json=payload
                )
                data = response.json()
                
                logger.info(f"[YGG Login] FlareSolverr response status: {data.get('status')}")
                
                if data.get("status") == "ok":
                    solution = data.get("solution", {})
                    cookies = solution.get("cookies", [])
                    logger.info(f"[YGG Login] Received {len(cookies)} cookies")
                    
                    for cookie in cookies:
                        cookie_name = cookie.get("name", "")
                        if cookie_name.startswith("ygg"):
                            self._session_cookie = cookie.get("value")
                            self._session_cookie_name = cookie_name  # Store actual name!
                            logger.info(f"[YGG Login] Found session cookie: {cookie_name}")
                        if cookie_name == "cf_clearance":
                            self._cf_clearance = cookie.get("value")
                            logger.info("[YGG Login] Updated cf_clearance cookie")
                    
                    # Check if login was successful by looking at the response URL
                    response_url = solution.get("url", "")
                    if "/auth/login" in response_url or "login" in response_url.lower():
                        logger.warning("[YGG Login] Still on login page - login may have failed")
                        return False
                    
                    if self._session_cookie:
                        logger.info("[YGG Login] Login successful!")
                        return True
                    else:
                        logger.warning("[YGG Login] No session cookie found - login may have failed")
                        # Log cookie names for debugging
                        cookie_names = [c.get("name") for c in cookies]
                        logger.info(f"[YGG Login] Available cookies: {cookie_names}")
                        return False
                
                logger.error(f"[YGG Login] FlareSolverr error: {data.get('message')}")
                return False
            except Exception as e:
                logger.error(f"[YGG Login] Error: {e}")
                import traceback
                logger.error(f"[YGG Login] Traceback: {traceback.format_exc()}")
                return False
    
    async def _get_authenticated_download_url(self, torrent_id: str) -> Optional[str]:
        """
        Get download URL with authentication.
        NOTE: This returns the URL but qBittorrent can't use it without cookies.
        Use download_torrent_file() instead to get the actual torrent bytes.
        """
        if not torrent_id:
            logger.error("[Scraper] Cannot get download URL: torrent_id is empty")
            return None
        
        if not await self._login_if_needed():
            logger.error("[Scraper] Cannot get download URL: login failed")
            return None
        
        download_url = f"{self.settings.ygg_base_url}/engine/download_torrent?id={torrent_id}"
        logger.info(f"[Scraper] Authenticated download URL: {download_url}")
        return download_url
    
    async def download_torrent_file(self, torrent_id: str) -> Optional[bytes]:
        """
        Download the .torrent file using FlareSolverr and return its bytes.
        Cloudflare blocks all direct requests - FlareSolverr is required.
        """
        if not torrent_id:
            logger.error("[Scraper] Cannot download torrent: torrent_id is empty")
            return None
        
        # Build download URL - use passkey if available
        passkey = self.settings.ygg_passkey
        if passkey and passkey not in ['your_passkey', 'votre_passkey', '', None]:
            download_url = f"{self.settings.ygg_base_url}/engine/download_torrent?id={torrent_id}&passkey={passkey}"
            logger.info(f"[Scraper] Using passkey URL for download: {download_url[:80]}...")
        else:
            # Need login for non-passkey URL
            if not await self._login_if_needed():
                logger.error("[Scraper] Cannot download torrent: login failed")
                return None
            download_url = f"{self.settings.ygg_base_url}/engine/download_torrent?id={torrent_id}"
            logger.info(f"[Scraper] Using authenticated URL for download")
        
        # Build cookies for FlareSolverr
        cookies_to_send = []
        if self._cf_clearance:
            cookies_to_send.append({"name": "cf_clearance", "value": self._cf_clearance})
        if self._session_cookie:
            cookies_to_send.append({"name": self._session_cookie_name, "value": self._session_cookie})
        
        payload = {
            "cmd": "request.get",
            "url": download_url,
            "maxTimeout": 60000,
            "returnOnlyCookies": False
        }
        
        if cookies_to_send:
            payload["cookies"] = cookies_to_send
        
        logger.info(f"[Scraper] Downloading torrent via FlareSolverr...")
        
        try:
            async with httpx.AsyncClient(timeout=70.0) as client:
                response = await client.post(self.settings.flaresolverr_url, json=payload)
                data = response.json()
                
                if data.get("status") == "ok":
                    solution = data.get("solution", {})
                    response_content = solution.get("response", "")
                    response_status = solution.get("status", 0)
                    
                    logger.info(f"[Scraper] FlareSolverr response status: {response_status}, content length: {len(response_content)}")
                    
                    # Check if it's a torrent file
                    if response_content:
                        # Torrent files start with 'd' (bencoded dict) and contain 'announce'
                        if response_content.startswith("d") and "announce" in response_content[:500]:
                            content_bytes = response_content.encode('latin-1')
                            logger.info(f"[Scraper] Successfully downloaded torrent file ({len(content_bytes)} bytes)")
                            return content_bytes
                        elif "<!DOCTYPE" in response_content[:100] or "<html" in response_content[:100]:
                            logger.warning("[Scraper] Got HTML instead of torrent - Cloudflare challenge or error page")
                            logger.debug(f"[Scraper] HTML preview: {response_content[:300]}")
                        else:
                            logger.warning(f"[Scraper] Unknown content type. First 100 chars: {response_content[:100]}")
                    else:
                        logger.error("[Scraper] FlareSolverr returned empty response")
                else:
                    logger.error(f"[Scraper] FlareSolverr error: {data.get('message')}")
        except Exception as e:
            logger.error(f"[Scraper] FlareSolverr download error: {e}")
        
        return None
    
    def _parse_search_results(self, html: str) -> List[TorrentResult]:
        """Parse YGGtorrent search results HTML."""
        soup = BeautifulSoup(html, "lxml")
        results = []
        
        table = soup.find("table", class_="table")
        if not table:
            logger.warning("[Parser] No results table found in HTML")
            # Log some context to understand why
            tables = soup.find_all("table")
            logger.warning(f"[Parser] Found {len(tables)} table elements total")
            if "maintenance" in html.lower() or "erreur" in html.lower():
                logger.error("[Parser] Page may be in maintenance or showing error")
            return results
        
        rows = table.find_all("tr")[1:]  # Skip header
        logger.info(f"[Parser] Found {len(rows)} torrent rows in table")
        
        for row in rows:
            try:
                result = self._parse_torrent_row(row)
                if result:
                    results.append(result)
            except Exception as e:
                logger.debug(f"[Parser] Error parsing row: {e}")
                continue
        
        logger.info(f"[Parser] Successfully parsed {len(results)} torrents out of {len(rows)} rows")
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
        
        # Extract ID from href - try multiple patterns
        torrent_id = ""
        # Pattern 1: /torrent/ID/name or /torrent/ID-name
        id_match = re.search(r"/torrent/(\d+)", href)
        if id_match:
            torrent_id = id_match.group(1)
        else:
            # Pattern 2: id=ID in URL
            id_match = re.search(r"[?&]id=(\d+)", href)
            if id_match:
                torrent_id = id_match.group(1)
            else:
                # Pattern 3: /ID/ or -ID-
                id_match = re.search(r"/(\d{5,})", href)
                if id_match:
                    torrent_id = id_match.group(1)
        
        if not torrent_id:
            logger.warning(f"[Parser] Could not extract ID from href: {href[:100]}")
        
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
            torrent_url=f"{self.settings.ygg_base_url}{href}" if href.startswith("/") else href,
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
