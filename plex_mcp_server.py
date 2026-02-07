import argparse
import os
import json
import uvicorn # type: ignore
from starlette.applications import Starlette # type: ignore
from starlette.routing import Mount, Route # type: ignore
from starlette.responses import JSONResponse, Response, RedirectResponse # type: ignore
from starlette.middleware import Middleware # type: ignore
from mcp.server import Server # type: ignore
from mcp.server.sse import SseServerTransport # type: ignore
from starlette.requests import Request # type: ignore
from dotenv import load_dotenv # type: ignore

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
# Client module functions
from modules.client import (
    client_list, 
    client_get_details, 
    client_get_timelines,
    client_get_active, 
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
        skip_paths = ["/.well-known/", "/authorize", "/token"]
        if any(request.url.path.startswith(p) for p in skip_paths):
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
            payload = validate_token(token)
            print(f"[OAuth] Token valid! User: {payload.get('sub', 'unknown')}")
            # Store user info in request state
            scope["oauth_user"] = payload
            await self.app(scope, receive, send)
        except ValueError as e:
            print(f"[OAuth] Token validation failed: {e}")
            response = Response(
                status_code=401,
                headers={"WWW-Authenticate": get_www_authenticate_header()},
                content=f"Invalid token: {str(e)}"
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


def create_starlette_app(mcp_server: Server, debug: bool = False):
    """Create a Starlette application that can serve the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )
        return Response()

    # Build routes
    routes = [
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ]
    
    # Add OAuth discovery endpoints if enabled
    if oauth_config.enabled:
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
            """Proxy /token requests to Authentik's token endpoint with CORS handled by middleware."""
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
                                print(f"[Token] Response content (full): {content}")
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
    
    # Build middleware stack
    middleware = []

    if oauth_config.enabled:
        middleware.append(Middleware(OAuthMiddleware))
    
    return Starlette(
        debug=debug,
        routes=routes,
        middleware=middleware,
    )

def main():
    """Main entry point for the Plex MCP Server."""
    # Load environment variables - check multiple locations
    # Priority: 1) Current directory, 2) Config directory (~/.config/plex-mcp-server/.env)
    loaded = load_dotenv()  # Current directory
    if loaded:
        print("Loaded environment variables from .env in current directory")

    config_dir = os.path.expanduser("~/.config/plex-mcp-server")
    config_env_file = os.path.join(config_dir, ".env")
    if os.path.exists(config_env_file):
        if load_dotenv(config_env_file):
            print(f"Loaded environment variables from {config_env_file}")
            loaded = True
            
    if loaded:
        print("Successfully loaded environment variables from .env file")
    
    # Setup command line arguments
    parser = argparse.ArgumentParser(description='Run Plex MCP Server')
    parser.add_argument('--transport', choices=['stdio', 'sse'], default='sse',
                        help='Transport method to use (stdio or sse)')
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
        
    # Initialize and run the server
    print(f"Starting Plex MCP Server with {args.transport} transport...")
    
    # Configuration status
    masked_token = f"{args.plex_token[:4]}...{args.plex_token[-4:]}" if args.plex_token and len(args.plex_token) > 8 else "Not set"
    if not args.plex_url or not args.plex_token:
        print("Warning: Missing Plex configuration. Set PLEX_URL/PLEX_TOKEN via args or .env")
    
    if args.transport == 'stdio':
        # Run with stdio transport (original method)
        mcp.run(transport='stdio')
    else:
        # Run with SSE transport
        mcp_server = mcp._mcp_server  # Access the underlying MCP server
        starlette_app = create_starlette_app(mcp_server, debug=args.debug)
        print(f"Starting SSE server on http://{args.host}:{args.port}")
        print("Access the SSE endpoint at /sse")
        uvicorn.run(starlette_app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()