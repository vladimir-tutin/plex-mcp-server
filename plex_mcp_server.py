import argparse
from modules import mcp

# Import all tools to ensure they are registered with MCP
from modules.library import *
from modules.user import *
from modules.sessions import *
from modules.server import *
from modules.playlist import *
from modules.collection import *
from modules.media import *
from modules.client import *

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run Plex MCP Server')
    parser.add_argument('--transport', choices=['stdio', 'sse', 'streamable-http'], 
                        default='stdio', help='Transport method to use')
    
    args = parser.parse_args()
    
    print(f"Starting Plex MCP Server with {args.transport} transport...")
    mcp.run(transport=args.transport)