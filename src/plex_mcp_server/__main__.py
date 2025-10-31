"""Entry point for running the package as a module."""

import os
import uvicorn  # type: ignore

# Import the main mcp instance from modules
from .modules import mcp

# Import all tools to ensure they are registered with MCP
# This also has the side effect of registering the tools
from .server import create_starlette_app


def main():
    """Main entry point for the application."""
    # Get configuration from environment variables
    host = os.environ.get('FASTMCP_HOST', '0.0.0.0')
    port = int(os.environ.get('FASTMCP_PORT', '3001'))

    print(f"Starting Plex MCP Server with SSE transport...")
    print(f"Server will listen on http://{host}:{port}")
    print(f"SSE endpoint: /sse")
    print(f"Plex URL: {os.environ.get('PLEX_URL', 'Not set')}")

    # Run with SSE transport using proper Starlette app
    mcp_server = mcp._mcp_server  # Access the underlying MCP server
    starlette_app = create_starlette_app(mcp_server, debug=False)
    uvicorn.run(starlette_app, host=host, port=port)


if __name__ == "__main__":
    main()
