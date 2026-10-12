"""Account Watchlist access through Plex Discover, including non-library titles."""

import asyncio
import json
import os
import re
import inspect
from contextvars import ContextVar
from functools import wraps

import aiohttp
from plexapi.myplex import MyPlexAccount

from modules import mcp

DISCOVER = "https://discover.provider.plex.tv"
GUID = re.compile(r"plex://(movie|show)/([A-Za-z0-9._-]+)\Z")
_profile_token = ContextVar("watchlist_profile_token", default=None)


def _home_token(user_id, pin, username=None):
    token = os.environ.get("PLEX_TOKEN", "")
    if not token:
        raise ValueError("PLEX_TOKEN is required for account Watchlist access")
    if user_id is None and username is None:
        if pin:
            raise ValueError("username or home_user_id is required when supplying a PIN")
        return token
    if user_id is not None and user_id <= 0:
        raise ValueError("home_user_id must be a positive Plex Home user ID")
    try:
        account = MyPlexAccount(token=token, timeout=15)
        def matches(user):
            if user_id is not None:
                return str(user.id) == str(user_id)
            return any(isinstance(name, str) and name.casefold() == username.strip().casefold()
                       for name in (getattr(user, "username", None), getattr(user, "title", None)))

        if username is not None and not username.strip():
            raise ValueError("username must not be empty")
        if matches(account):
            return token
        candidates = [user for user in account.users() if matches(user)]
        if not candidates:
            raise ValueError("Plex user not found")
        if len(candidates) != 1:
            raise ValueError("Multiple users match that username; supply home_user_id")
        target = candidates[0]
        if getattr(target, "protected", False) and not pin:
            raise ValueError("This Plex Home profile requires its PIN")
        selected = account.switchHomeUser(target, pin=pin)
        if str(selected.id) != str(target.id) or not selected.authenticationToken:
            raise ValueError("Plex did not confirm the requested Home profile")
        return selected.authenticationToken
    except ValueError:
        raise
    except Exception:
        raise ValueError("Plex could not access the requested user profile") from None


def _with_home_profile(func):
    @wraps(func)
    async def wrapped(*args, **kwargs):
        try:
            bound = inspect.signature(func).bind(*args, **kwargs)
            selectors = (bound.arguments.get("home_user_id"), bound.arguments.get("pin"))
            username = bound.arguments.get("username")
            token = await asyncio.to_thread(_home_token, *selectors, username=username) if username is not None else await asyncio.to_thread(_home_token, *selectors)
            state = _profile_token.set(token)
            try:
                return await func(*args, **kwargs)
            finally:
                _profile_token.reset(state)
        except Exception as exc:
            return _error(exc)
    return wrapped


async def _request(method, path, params=None):
    token = _profile_token.get() or os.environ.get("PLEX_TOKEN", "")
    if not token:
        raise ValueError("PLEX_TOKEN is required for account Watchlist access")
    headers = {"X-Plex-Token": token, "Accept": "application/json",
               "X-Plex-Product": "Plex MCP Server", "X-Plex-Client-Identifier": "plex-mcp-server"}
    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.request(method, DISCOVER + path, params=params, allow_redirects=False) as response:
            if response.status in (401, 403):
                raise ValueError(f"Plex rejected Watchlist access (HTTP {response.status})")
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
@_with_home_profile
async def watchlist_list(offset: int = 0, limit: int = 50, home_user_id: int = None, pin: str = None, username: str = None) -> str:
    """List the PLEX_TOKEN account's Watchlist, including titles outside the library.

    Args:
        offset: Number of items to skip.
        limit: Page size, from 1 to 100.
        home_user_id: Optional Plex Home profile ID from user_list_all_users. Omit for the configured account.
        pin: Profile PIN, only if required by Plex.
        username: Exact Plex username or profile title. Uses the configured admin credentials; returns an error if access fails. home_user_id takes precedence.
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
@_with_home_profile
async def watchlist_search(query: str, content_type: str = None, limit: int = 20, home_user_id: int = None, pin: str = None, username: str = None) -> str:
    """Search Plex Discover for movie/show GUIDs to add to the Watchlist.

    Searches beyond the local library. Choose the exact title/year before adding.
    Args:
        query: Title to search for.
        content_type: Optional movie or show filter.
        limit: Maximum results, from 1 to 100.
        home_user_id: Optional Plex Home profile ID from user_list_all_users.
        pin: Profile PIN, only if required by Plex.
        username: Exact Plex username or profile title. Uses the configured admin credentials; returns an error if access fails. home_user_id takes precedence.
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
@_with_home_profile
async def watchlist_add(guid: str, home_user_id: int = None, pin: str = None, username: str = None) -> str:
    """Add a movie/show GUID from watchlist_search to the PLEX_TOKEN account's Watchlist.

    The GUID is a Plex cloud identity, not a local media_id/ratingKey.
    Select a user with username (exact username or profile title), or home_user_id
    from user_list_all_users (takes precedence). Uses configured admin credentials.
    Supply pin if required. Omit selectors for the configured account. Failed access returns an error.
    """
    return await _set(guid, True)


@mcp.tool()
@_with_home_profile
async def watchlist_remove(guid: str, home_user_id: int = None, pin: str = None, username: str = None) -> str:
    """Remove a GUID returned by watchlist_list from the PLEX_TOKEN account's Watchlist.

    Does not delete media or change its watched status.
    Select a user with username (exact username or profile title), or home_user_id
    from user_list_all_users (takes precedence). Uses configured admin credentials.
    Supply pin if required. Omit selectors for the configured account. Failed access returns an error.
    """
    return await _set(guid, False)
