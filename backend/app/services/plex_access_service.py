"""
Plex Server Access Verification Service.

Verifies that a user has access to the configured Plex server
by checking the plex.tv/api/v2/resources endpoint.
"""
import logging
from typing import Dict, List

import httpx

logger = logging.getLogger(__name__)


async def get_user_plex_servers(user_token: str) -> List[Dict]:
    """
    Retrieve the list of Plex servers the user has access to.

    Uses the Plex.tv API: https://plex.tv/api/v2/resources

    Args:
        user_token: The user's Plex authentication token

    Returns:
        List of server dictionaries with keys:
        - name: Server name
        - machineIdentifier: Unique server identifier
        - owned: Whether the user owns this server
        - accessToken: Server-specific access token
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://plex.tv/api/v2/resources",
            params={"includeHttps": 1, "includeRelay": 1},
            headers={
                "X-Plex-Token": user_token,
                "Accept": "application/json"
            }
        )
        response.raise_for_status()

        # Filter only Plex servers (not players, etc.)
        resources = response.json()
        servers = [r for r in resources if r.get("provides") == "server"]

        return [
            {
                "name": s.get("name"),
                "machineIdentifier": s.get("clientIdentifier"),
                "owned": s.get("owned", False),
                "accessToken": s.get("accessToken"),
            }
            for s in servers
        ]


async def check_plex_server_access(
    user_token: str,
    required_machine_id: str
) -> bool:
    """
    Verify if the user has access to the specified Plex server.

    Args:
        user_token: The user's Plex authentication token
        required_machine_id: The machineIdentifier of the required server

    Returns:
        True if the user has access, False otherwise
    """
    if not required_machine_id:
        logger.warning("[Plex] No machine_identifier configured, skipping access check")
        return True  # No restriction if not configured

    try:
        servers = await get_user_plex_servers(user_token)

        for server in servers:
            if server["machineIdentifier"] == required_machine_id:
                logger.info(f"[Plex] User has access to server: {server['name']}")
                return True

        logger.warning(f"[Plex] User does NOT have access to server {required_machine_id}")
        return False

    except httpx.HTTPStatusError as e:
        logger.error(f"[Plex] HTTP error checking server access: {e.response.status_code}")
        return False
    except Exception as e:
        logger.error(f"[Plex] Error checking server access: {e}")
        return False  # Fail secure: deny on error
