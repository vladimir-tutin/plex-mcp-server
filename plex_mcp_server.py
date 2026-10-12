import argparse
import sys
import os
import json
import uvicorn # type: ignore
from starlette.applications import Starlette # type: ignore
from starlette.routing import Mount, Route # type: ignore
from starlette.responses import JSONResponse, Response, RedirectResponse # type: ignore
from starlette.middleware import Middleware # type: ignore
from mcp.server import Server # type: ignore
from mcp.server.sse import SseServerTransport # type: ignore
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager # type: ignore
from mcp.server.transport_security import TransportSecuritySettings
from starlette._utils import get_route_path
from urllib.parse import urlsplit
from starlette.requests import Request # type: ignore
from dotenv import load_dotenv # type: ignore

def init_environment():
    """Load environment variables from standard locations."""
    # Priority: 1) Current directory, 2) Config directory (~/.config/plex-mcp-server/.env)
    loaded = load_dotenv()  # Current directory
    
    config_dir = os.path.expanduser("~/.config/plex-mcp-server")
    config_env_file = os.path.join(config_dir, ".env")
    if os.path.exists(config_env_file):
        if load_dotenv(config_env_file):
            loaded = True
    return loaded

# Load environment before any other modules are imported
env_loaded = init_environment()

# Import the main mcp instance from modules
import modules
from modules import mcp, connect_to_plex
from modules.auth import (
    oauth_config,
    validate_token,
    extract_bearer_token,
    get_protected_resource_metadata,
    get_www_authenticate_header
)

# Import all tools to ensure they are registered with MCP
# Library module functions
from modules.library import (
    library_list,
    library_get_stats,
    library_refresh,
    library_scan,
    library_get_details,
    library_get_recently_added,
    library_get_contents
)
# User module functions
from modules.user import (
    user_search_users,
    user_list_all_users,
    user_get_info,
    user_get_on_deck,
    user_get_continue_watching,
    user_get_watch_history,
    user_get_statistics
)
# Search module functions
from modules.sessions import (
    sessions_get_active,
    sessions_get_media_playback_history
)
# Server module functions
from modules.server import (
    server_get_plex_logs,
    server_get_info,
    server_get_bandwidth,
    server_get_current_resources,
    server_get_butler_tasks,
    server_get_alerts,
    server_run_butler_task
)
# Playlist module functions
from modules.playlist import (
    playlist_list,
    playlist_get_contents,
    playlist_create,
    playlist_delete,
    playlist_add_to,
    playlist_remove_from,
    playlist_edit,
    playlist_upload_poster,
    playlist_copy_to_user
)
# Collection module functions
from modules.collection import (
    collection_list,
    collection_create,
    collection_add_to,
    collection_remove_from,
    collection_edit
)
# Media module functions
from modules.media import (
    media_search,
    media_get_details,
    media_edit_metadata,
    media_delete,
    media_get_artwork,
    media_set_artwork,
    media_list_available_artwork  
)  
from modules.watchlist import watchlist_list, watchlist_search, watchlist_add, watchlist_remove

# Client module functions
from modules.client import (
    client_list, 
    client_get_details, 
    client_get_timelines,
    client_start_playback, 
    client_control_playback,
    client_navigate, 
    client_set_streams
)

class OAuthMiddleware:
    """Pure ASGI middleware to validate OAuth tokens for protected endpoints.
    
    Avoids BaseHTTPMiddleware to prevent issues with SSE and AssertionError.
    """
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        print(f"[OAuth] Request: {request.method} {request.url.path}")
        
        # Skip OAuth for discovery and auth flow endpoints
        route_path = get_route_path(scope)
        if route_path.startswith("/.well-known/") or route_path in ("/authorize", "/token"):
            print(f"[OAuth] Skipping auth for {request.url.path}")
            await self.app(scope, receive, send)
            return
        
        # Skip OAuth if not enabled
        if not oauth_config.enabled:
            await self.app(scope, receive, send)
            return
        
        # Extract and validate token
        auth_header = request.headers.get("authorization")
        token = extract_bearer_token(auth_header)
        print(f"[OAuth] Token present: {bool(token)}")
        
        if not token:
            print(f"[OAuth] No token, returning 401")
            response = Response(
                status_code=401,
                headers={"WWW-Authenticate": get_www_authenticate_header()},
                content="Authorization required"
            )
            await response(scope, receive, send)
            return
        
        try:
            # Validate token
            print(f"[OAuth] Validating token...")
            payload = await validate_token(token)
            print("[OAuth] Token valid")
            # Store user info in request state
            scope["oauth_user"] = payload
            await self.app(scope, receive, send)
        except ValueError:
            print("[OAuth] Token validation failed")
            response = Response(
                status_code=401,
                headers={"WWW-Authenticate": get_www_authenticate_header()},
                content="Invalid token"
            )
            await response(scope, receive, send)


async def handle_protected_resource_metadata(request: Request):
    """OAuth 2.0 Protected Resource Metadata endpoint (RFC 9728)."""
    metadata = get_protected_resource_metadata()
    return JSONResponse(metadata)


async def handle_authorization_server_metadata(request: Request):
    """Fetch and return OAuth authorization server metadata, using local proxies."""
    import aiohttp
    
    # Get server base URL
    server_url = oauth_config.server_url.rstrip('/')
    
    # Fetch Authentik's OIDC discovery metadata for other values
    discovery_url = f"{oauth_config.issuer.rstrip('/')}/.well-known/openid-configuration"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(discovery_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    authentik_metadata = await resp.json()
                    
                    # Return metadata pointing to OUR proxy endpoints, not Authentik's directly
                    return JSONResponse({
                        "issuer": server_url,
                        "authorization_endpoint": f"{server_url}/authorize",
                        "token_endpoint": f"{server_url}/token",
                        "jwks_uri": authentik_metadata.get("jwks_uri"),
                        "response_types_supported": ["code"],
                        "grant_types_supported": ["authorization_code", "refresh_token"],
                        "code_challenge_methods_supported": ["S256"],
                        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
                    })
                else:
                    return JSONResponse({"error": f"Failed to fetch Authentik metadata: {resp.status}"}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": f"Failed to connect to Authentik: {str(e)}"}, status_code=502)


def _build_oauth_extras():
    """Build the OAuth discovery/proxy routes and auth middleware shared by every
    network transport. No-ops (returns empty lists) when OAuth isn't enabled, so
    callers can unconditionally extend their own routes/middleware with these.
    """
    routes = []
    middleware = []

    if not oauth_config.enabled:
        return routes, middleware

    async def handle_authorize_redirect(request: Request):
        """Redirect /authorize to Authentik's authorization endpoint."""
        import aiohttp
        # Get Authentik's authorize endpoint
        discovery_url = f"{oauth_config.issuer.rstrip('/')}/.well-known/openid-configuration"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(discovery_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        metadata = await resp.json()
                        auth_endpoint = metadata.get("authorization_endpoint")
                        # Forward all query params to Authentik
                        query_string = request.url.query
                        redirect_url = f"{auth_endpoint}?{query_string}" if query_string else auth_endpoint
                        return RedirectResponse(url=redirect_url, status_code=302)
        except Exception as e:
            return JSONResponse({"error": f"Failed to redirect to Authentik: {str(e)}"}, status_code=502)
        return JSONResponse({"error": "Could not determine authorization endpoint"}, status_code=502)

    async def handle_token_proxy(request: Request):
        """Proxy /token requests to Authentik's token endpoint."""
        import aiohttp

        # Get Authentik's token endpoint
        discovery_url = f"{oauth_config.issuer.rstrip('/')}/.well-known/openid-configuration"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(discovery_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        metadata = await resp.json()
                        token_endpoint = metadata.get("token_endpoint")
                        # Forward the token request to Authentik
                        body = await request.body()
                        headers = {k: v for k, v in request.headers.items()
                                  if k.lower() in ['content-type', 'authorization']}
                        async with session.post(token_endpoint, data=body, headers=headers) as token_resp:
                            content = await token_resp.text()
                            print(f"[Token] Response status: {token_resp.status}")
                            response_headers = {
                                "Content-Type": token_resp.headers.get("Content-Type", "application/json"),
                            }
                            return Response(
                                content=content,
                                status_code=token_resp.status,
                                headers=response_headers
                            )
        except Exception as e:
            return JSONResponse({"error": f"Failed to proxy token request: {str(e)}"}, status_code=502)
        return JSONResponse({"error": "Could not determine token endpoint"}, status_code=502)

    routes.extend([
        Route("/.well-known/oauth-protected-resource",
              endpoint=handle_protected_resource_metadata),
        Route("/.well-known/oauth-authorization-server",
              endpoint=handle_authorization_server_metadata),
        Route("/authorize", endpoint=handle_authorize_redirect),
        Route("/token", endpoint=handle_token_proxy, methods=["POST", "OPTIONS"]),
    ])
    middleware.append(Middleware(OAuthMiddleware))

    return routes, middleware


def _transport_security_settings() -> TransportSecuritySettings:
    """DNS-rebinding protection shared by the SSE and Streamable HTTP transports.

    Loopback is always allowed; the public hostname comes from --server-url /
    MCP_SERVER_URL, and MCP_ALLOWED_HOSTS / MCP_ALLOWED_ORIGINS add extras (e.g. a
    LAN IP or reverse-proxy name). Origin is only checked when a browser sends one.
    """
    public_url = urlsplit(oauth_config.server_url or "")
    hosts = ["127.0.0.1:*", "127.0.0.1", "localhost:*", "localhost", "[::1]:*", "[::1]"]
    origins = ["http://127.0.0.1:*", "http://localhost:*"]
    if public_url.netloc:
        hosts.append(public_url.netloc)
        origins.append(f"{public_url.scheme}://{public_url.netloc}")
    hosts.extend(x.strip() for x in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if x.strip())
    origins.extend(x.strip() for x in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",") if x.strip())
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


class _SSEASGIApp:
    """Raw ASGI endpoint for the SSE stream (see _StreamableHTTPASGIApp for why a
    class instance rather than a function).

    When Host/Origin validation fails, connect_sse sends the 421/403 itself and
    then raises ValueError to abort. Swallow that only after a response has
    started, so genuine errors still propagate.
    """

    def __init__(self, sse: SseServerTransport, mcp_server: Server):
        self.sse = sse
        self.mcp_server = mcp_server

    async def __call__(self, scope, receive, send) -> None:
        response_started = False

        async def tracking_send(message):
            nonlocal response_started
            response_started = True
            await send(message)

        try:
            async with self.sse.connect_sse(scope, receive, tracking_send) as (read_stream, write_stream):
                await self.mcp_server.run(
                    read_stream,
                    write_stream,
                    self.mcp_server.create_initialization_options(),
                )
        except ValueError:
            if not response_started:
                raise


def create_starlette_app(mcp_server: Server, debug: bool = False):
    """Create a Starlette application that can serve the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/", security_settings=_transport_security_settings())

    # Build routes
    routes = [
        # GET only: clients configured with the /sse URL probe it with a Streamable
        # HTTP POST first and rely on the 405 to fall back to classic SSE.
        Route("/sse", endpoint=_SSEASGIApp(sse, mcp_server), methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ]

    oauth_routes, middleware = _build_oauth_extras()
    routes.extend(oauth_routes)

    return Starlette(
        debug=debug,
        routes=routes,
        middleware=middleware,
    )


class _StreamableHTTPASGIApp:
    """Thin ASGI wrapper around a StreamableHTTPSessionManager.

    Must be a class instance (not a plain function) so Starlette's Route treats
    it as a raw ASGI sub-application instead of wrapping it as a
    request->response handler restricted to GET (see starlette.routing.Route.__init__:
    it only takes the ASGI-app branch for non function/method endpoints).
    """

    def __init__(self, session_manager: StreamableHTTPSessionManager):
        self.session_manager = session_manager

    async def __call__(self, scope, receive, send) -> None:
        await self.session_manager.handle_request(scope, receive, send)


def create_streamable_http_app(mcp_server: Server, debug: bool = False, path: str = "/mcp"):
    """Create a Starlette application that can serve the provided mcp server with
    Streamable HTTP — a single endpoint, unlike SSE's /sse + /messages/ pair, so it
    doesn't embed any root-relative URL in its responses and can be mounted behind a
    reverse proxy at an arbitrary path prefix.
    """
    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        security_settings=_transport_security_settings(),
    )

    # Keep legacy SSE available while clients migrate to Streamable HTTP.
    routes = [
        Route(path, endpoint=_StreamableHTTPASGIApp(session_manager)),
        *create_starlette_app(mcp_server, debug=debug).routes,
    ]
    _, middleware = _build_oauth_extras()

    return Starlette(
        debug=debug,
        routes=routes,
        middleware=middleware,
        lifespan=lambda app: session_manager.run(),
    )

def main():
    """Main entry point for the Plex MCP Server."""
    if env_loaded:
        print("Successfully loaded environment variables from .env file", file=sys.stderr)
    
    # Setup command line arguments
    parser = argparse.ArgumentParser(description='Run Plex MCP Server')
    parser.add_argument('--transport', choices=['stdio', 'sse', 'streamable-http'], default='sse',
                        help='Transport method to use (stdio, sse, or streamable-http)')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (for SSE)')
    parser.add_argument('--port', type=int, default=3001, help='Port to listen on (for SSE)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    # Plex configuration arguments
    parser.add_argument('--plex-url', default=os.environ.get('PLEX_URL'), 
                        help='Plex Server URL (default: PLEX_URL env var)')
    parser.add_argument('--plex-token', default=os.environ.get('PLEX_TOKEN'), 
                        help='Plex Auth Token (default: PLEX_TOKEN env var)')
    
    # OAuth configuration arguments
    parser.add_argument('--oauth-enabled', action='store_true',
                        default=os.environ.get('MCP_OAUTH_ENABLED', '').lower() == 'true',
                        help='Enable OAuth authentication')
    parser.add_argument('--oauth-issuer', default=os.environ.get('MCP_OAUTH_ISSUER'),
                        help='OAuth issuer URL (e.g., Authentik provider URL)')
    parser.add_argument('--server-url', default=os.environ.get('MCP_SERVER_URL'),
                        help='Public server URL for OAuth callbacks')
    parser.add_argument('--oauth-audience', default=os.environ.get('MCP_OAUTH_AUDIENCE'),
                        help='Expected token audience (your OAuth client ID); unset disables the check')

    args = parser.parse_args()

    # Apply configuration updates to modules
    # This ensures that both CLI args and environment variables (loaded above)
    # are reflected in the modules' shared state.
    modules.plex_url = args.plex_url
    modules.plex_token = args.plex_token
    
    if args.plex_url:
        os.environ['PLEX_URL'] = args.plex_url
        
    if args.plex_token:
        os.environ['PLEX_TOKEN'] = args.plex_token
    
    # Apply OAuth configuration from command line
    if args.oauth_enabled:
        os.environ['MCP_OAUTH_ENABLED'] = 'true'
    if args.oauth_issuer:
        os.environ['MCP_OAUTH_ISSUER'] = args.oauth_issuer
    if args.server_url:
        os.environ['MCP_SERVER_URL'] = args.server_url
    if args.oauth_audience:
        os.environ['MCP_OAUTH_AUDIENCE'] = args.oauth_audience

    # Refresh OAuth configuration to pick up any CLI overrides or late-loaded environment variables
    oauth_config.reload()
        
    # Initialize and run the server
    print(f"Starting Plex MCP Server with {args.transport} transport...", file=sys.stderr)
    
    # Configuration status
    if not args.plex_url or not args.plex_token:
        print("Warning: Missing Plex configuration. Set PLEX_URL/PLEX_TOKEN via args or .env", file=sys.stderr)
    
    if args.transport == 'stdio':
        # Run with stdio transport (original method)
        mcp.run(transport='stdio')
    elif args.transport == 'streamable-http':
        mcp_server = mcp._mcp_server  # Access the underlying MCP server
        starlette_app = create_streamable_http_app(mcp_server, debug=args.debug)
        print(f"Starting Streamable HTTP server on http://{args.host}:{args.port}", file=sys.stderr)
        print("Access the MCP endpoint at /mcp", file=sys.stderr)
        uvicorn.run(starlette_app, host=args.host, port=args.port)
    else:
        # Run with SSE transport
        mcp_server = mcp._mcp_server  # Access the underlying MCP server
        starlette_app = create_starlette_app(mcp_server, debug=args.debug)
        print(f"Starting SSE server on http://{args.host}:{args.port}", file=sys.stderr)
        print("Access the SSE endpoint at /sse", file=sys.stderr)
        uvicorn.run(starlette_app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
