import argparse
import uvicorn # type: ignore
from starlette.applications import Starlette # type: ignore
from starlette.routing import Mount, Route # type: ignore
from mcp.server import Server # type: ignore
from mcp.server.sse import SseServerTransport # type: ignore
from starlette.requests import Request # type: ignore

# Import the main mcp instance from modules
from modules import mcp, connect_to_plex

# Import all tools to ensure they are registered with MCP
# Library module functions
from modules.library import (
    list_libraries,
    get_library_stats,
    refresh_library,
    scan_library,
    get_library_details,
    get_recently_added,
    get_library_contents
)
# User module functions
from modules.user import (
    search_users,
    get_user_info,
    get_user_on_deck,
    get_user_watch_history
)
# Search module functions
from modules.sessions import (
    get_active_sessions,
    get_media_playback_history
)
# Server module functions
from modules.server import (
    get_plex_logs,
    get_server_info,
    get_server_activities,
    get_server_bandwidth,
    get_server_resources,
    get_server_butler_tasks,
    get_server_sessions_stats,
    get_server_alerts,
    toggle_butler_task,
    run_butler_task
)
# Playlist module functions
from modules.playlist import (
    create_playlist,
    delete_playlist,
    add_to_playlist,
    remove_from_playlist,
    edit_playlist,
    upload_playlist_poster,
    copy_playlist_to_user
)
# Collection module functions
from modules.collection import (
    list_collections,
    create_collection,
    add_to_collection,
    remove_from_collection,
    edit_collection
)
# Media module functions
from modules.media import (
    search_media,
    get_media_details,
    edit_metadata,
    extract_media_images,
    delete_media,
    get_media_artwork,
    set_media_artwork,
    list_available_artwork  
)  
# Client module functions
from modules.client import (
    list_clients, get_client_details, get_client_timelines,
    get_active_clients, start_playback, control_playback,
    navigate_client, set_streams
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

if __name__ == "__main__":
    # Setup command line arguments
    parser = argparse.ArgumentParser(description='Run Plex MCP Server')
    parser.add_argument('--transport', choices=['stdio', 'sse'], default='stdio', 
                        help='Transport method to use (stdio or sse)')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (for SSE)')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on (for SSE)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Initialize and run the server
    print(f"Starting Plex MCP Server with {args.transport} transport...")
    print("Set PLEX_URL and PLEX_TOKEN environment variables for connection")
    
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