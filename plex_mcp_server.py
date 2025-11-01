import argparse

import uvicorn  # type: ignore
from mcp.server import Server  # type: ignore
from mcp.server.sse import SseServerTransport  # type: ignore

# Import the main mcp instance from modules
from modules import mcp

# Client module functions
# Collection module functions
# Import all tools to ensure they are registered with MCP
# Library module functions
# Media module functions
# Playlist module functions
# Server module functions
# Search module functions
# User module functions
from starlette.applications import Starlette  # type: ignore
from starlette.requests import Request  # type: ignore
from starlette.responses import StreamingResponse
from starlette.routing import Mount, Route  # type: ignore


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can serve the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        sse = SseServerTransport("/messages/")

        async def event_generator():
            async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
            ) as (read_stream, write_stream):
                await mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp_server.create_initialization_options(),
                )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            },
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
    parser = argparse.ArgumentParser(description="Run Plex MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="sse",
        help="Transport method to use (stdio or sse)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (for SSE)")
    parser.add_argument("--port", type=int, default=3001, help="Port to listen on (for SSE)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    # Initialize and run the server
    print(f"Starting Plex MCP Server with {args.transport} transport...")
    print("Set PLEX_URL and PLEX_TOKEN environment variables for connection")

    if args.transport == "stdio":
        # Run with stdio transport (original method)
        mcp.run(transport="stdio")
    else:
        # Run with SSE transport
        mcp_server = mcp._mcp_server  # Access the underlying MCP server
        starlette_app = create_starlette_app(mcp_server, debug=args.debug)
        print(f"Starting SSE server on http://{args.host}:{args.port}")
        print("Access the SSE endpoint at /sse")
        uvicorn.run(starlette_app, host=args.host, port=args.port)
