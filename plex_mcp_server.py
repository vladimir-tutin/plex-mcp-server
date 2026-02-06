import argparse
import os
import uvicorn # type: ignore
from starlette.applications import Starlette # type: ignore
from starlette.routing import Mount, Route # type: ignore
from mcp.server import Server # type: ignore
from mcp.server.sse import SseServerTransport # type: ignore
from starlette.requests import Request # type: ignore

# Import the main mcp instance from modules
import modules
from modules import mcp, connect_to_plex

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

def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
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

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

def main():
    """Main entry point for the Plex MCP Server."""
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

    args = parser.parse_args()

    # Apply configuration updates
    if args.plex_url:
        modules.plex_url = args.plex_url
        os.environ['PLEX_URL'] = args.plex_url
        
    if args.plex_token:
        modules.plex_token = args.plex_token
        os.environ['PLEX_TOKEN'] = args.plex_token
        
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