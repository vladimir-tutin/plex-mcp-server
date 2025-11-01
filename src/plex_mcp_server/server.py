from mcp.server import Server  # type: ignore
from mcp.server.sse import SseServerTransport  # type: ignore
from starlette.applications import Starlette  # type: ignore
from starlette.requests import Request
from starlette.routing import Mount, Route  # type: ignore

# Import the main mcp instance from modules

# Client module functions

# Collection module functions

# Import all tools to ensure they are registered with MCP
# Library module functions

# Media module functions

# Playlist module functions

# Server module functions

# Search module functions

# User module functions


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can serve the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
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

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )
