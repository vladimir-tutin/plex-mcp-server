"""Account Watchlist access through Plex Discover, including non-library titles."""

import asyncio
import json
import os
import re

import aiohttp

from modules import mcp

DISCOVER = "https://discover.provider.plex.tv"
GUID = re.compile(r"plex://(movie|show)/([A-Za-z0-9._-]+)\Z")


async def _request(method, path, params=None):
    token = os.environ.get("PLEX_TOKEN", "")
    if not token:
        raise ValueError("PLEX_TOKEN is required for account Watchlist access")
    headers = {"X-Plex-Token": token, "Accept": "application/json",
               "X-Plex-Product": "Plex MCP Server", "X-Plex-Client-Identifier": "plex-mcp-server"}
    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.request(method, DISCOVER + path, params=params, allow_redirects=False) as response:
            if response.status in (401, 403):
                raise ValueError("Plex rejected Watchlist access. PLEX_TOKEN must support plex.tv account access.")
            if not 200 <= response.status < 300:
                raise ValueError(f"Plex Watchlist request failed (HTTP {response.status})")
            return await response.json() if method == "GET" else None


def _item(row):
    return {"guid": row.get("guid"), "title": row.get("title"),
            "type": row.get("type"), "year": row.get("year")}


async def _page(offset, limit):
    data = await _request("GET", "/library/sections/watchlist/all", {
        "X-Plex-Container-Start": offset, "X-Plex-Container-Size": limit, "includeGuids": 1})
    container = data["MediaContainer"]
    rows = container.get("Metadata", [])
    return rows, int(container.get("totalSize", container.get("size", len(rows))))


async def _contains(guid):
    offset = 0
    while offset < 5000:
        rows, total = await _page(offset, 100)
        if any(row.get("guid") == guid for row in rows):
            return True
        offset += len(rows)
        if offset >= total:
            return False
        if not rows:
            raise ValueError("Plex returned an incomplete Watchlist; membership could not be checked")
    raise ValueError("Watchlist exceeds the supported 5000-item membership check")


def _error(exc):
    # Do not return upstream URLs, response bodies, or credentials.
    message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else "Plex Watchlist request failed"
    return json.dumps({"status": "error", "message": message})


@mcp.tool()
async def watchlist_list(offset: int = 0, limit: int = 50) -> str:
    """List the PLEX_TOKEN account's Watchlist, including titles outside the library.

    Args:
        offset: Number of items to skip.
        limit: Page size, from 1 to 100.
    """
    try:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("offset must be nonnegative and limit must be between 1 and 100")
        rows, total = await _page(offset, limit)
        return json.dumps({"items": [_item(row) for row in rows], "totalItems": total,
                           "offset": offset, "limit": limit, "size": len(rows)})
    except Exception as exc:
        return _error(exc)


@mcp.tool()
async def watchlist_search(query: str, content_type: str = None, limit: int = 20) -> str:
    """Search Plex Discover for movie/show GUIDs to add to the Watchlist.

    Searches beyond the local library. Choose the exact title/year before adding.
    Args:
        query: Title to search for.
        content_type: Optional movie or show filter.
        limit: Maximum results, from 1 to 100.
    """
    try:
        if not query.strip() or content_type not in (None, "movie", "show") or not 1 <= limit <= 100:
            raise ValueError("Provide a query, content_type movie or show (or omit it), and limit from 1 to 100")
        data = await _request("GET", "/library/search", {
            "query": query, "limit": limit, "searchTypes": {"movie": "movies", "show": "tv"}.get(content_type, "movies,tv"),
            "searchProviders": "discover", "includeMetadata": 1})
        rows = [result["Metadata"] for group in data["MediaContainer"].get("SearchResults", [])
                if group.get("id") == "external" for result in group.get("SearchResult", [])
                if result.get("Metadata", {}).get("type") in ("movie", "show")]
        items = [_item(row) for row in rows if GUID.fullmatch(row.get("guid", ""))
                 and (content_type is None or row.get("type") == content_type)][:limit]
        return json.dumps({"items": items, "size": len(items)})
    except Exception as exc:
        return _error(exc)


async def _set(guid, desired):
    try:
        match = GUID.fullmatch(guid)
        if not match:
            raise ValueError("Use a plex://movie/... or plex://show/... GUID from watchlist_search or watchlist_list, not a local ratingKey")
        before = await _contains(guid)
        if before != desired:
            action = "addToWatchlist" if desired else "removeFromWatchlist"
            await _request("PUT", "/actions/" + action, {"ratingKey": match.group(2)})
            for attempt in range(4):
                if attempt:
                    await asyncio.sleep(0.15)
                if await _contains(guid) == desired:
                    break
            else:
                raise ValueError("Plex accepted the request but did not confirm the Watchlist change; check watchlist_list before retrying")
        return json.dumps({"status": "success", "guid": guid, "watchlisted": desired, "changed": before != desired})
    except Exception as exc:
        return _error(exc)


@mcp.tool()
async def watchlist_add(guid: str) -> str:
    """Add a movie/show GUID from watchlist_search to the PLEX_TOKEN account's Watchlist.

    The GUID is a Plex cloud identity, not a local media_id/ratingKey.
    """
    return await _set(guid, True)


@mcp.tool()
async def watchlist_remove(guid: str) -> str:
    """Remove a GUID returned by watchlist_list from the PLEX_TOKEN account's Watchlist.

    Does not delete media or change its watched status.
    """
    return await _set(guid, False)
