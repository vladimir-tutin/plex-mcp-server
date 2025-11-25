import os
import time
from mcp.server.fastmcp import FastMCP # type: ignore
from plexapi.server import PlexServer # type: ignore
from plexapi.myplex import MyPlexAccount # type: ignore

# Add dotenv for .env file support
try:
    from dotenv import load_dotenv # type: ignore
    # Load environment variables from .env file
    load_dotenv()
    print("Successfully loaded environment variables from .env file")
except ImportError:
    print("Warning: python-dotenv not installed. Environment variables won't be loaded from .env file.")
    print("Install with: pip install python-dotenv")

# Initialize FastMCP server with configurable host/port from env
mcp = FastMCP(
    "plex-server",
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MCP_PORT", "8000"))
)

# Global variables for Plex connection
plex_url = os.environ.get("PLEX_URL", "")
plex_token = os.environ.get("PLEX_TOKEN", "")
server = None
last_connection_time = 0
CONNECTION_TIMEOUT = 30  # seconds
SESSION_TIMEOUT = 60 * 30  # 30 minutes

def connect_to_plex() -> PlexServer:
    """Connect to Plex server using environment variables or stored credentials.
    
    Returns a PlexServer instance with automatic reconnection if needed.
    """
    global server, last_connection_time
    current_time = time.time()
    
    # Check if we have a valid connection
    if server is not None:
        # If we've connected recently, reuse the connection
        if current_time - last_connection_time < SESSION_TIMEOUT:
            # Verify the connection is still alive with a simple request
            try:
                # Simple API call to verify the connection
                server.library.sections()
                last_connection_time = current_time
                return server
            except:
                # Connection failed, reset and create a new one
                server = None
    
    # Create a new connection
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            # Try connecting directly with a token
            if plex_token:
                server = PlexServer(plex_url, plex_token, timeout=CONNECTION_TIMEOUT)
                last_connection_time = current_time
                return server
            
            # If no direct connection, try with MyPlex account
            username = os.environ.get("PLEX_USERNAME")
            password = os.environ.get("PLEX_PASSWORD")
            server_name = os.environ.get("PLEX_SERVER_NAME")
            
            if username and password and server_name:
                account = MyPlexAccount(username, password)
                # Use the plex_token if available to avoid resource.connect()
                # which can be problematic
                for resource in account.resources():
                    if resource.name.lower() == server_name.lower() and resource.provides == 'server':
                        if resource.connections:
                            # Try each connection until one works
                            for connection in resource.connections:
                                try:
                                    server = PlexServer(connection.uri, account.authenticationToken, timeout=CONNECTION_TIMEOUT)
                                    last_connection_time = current_time
                                    return server
                                except:
                                    continue
                            
                # If we get here, none of the connection attempts worked
                # Fall back to resource.connect() as a last resort
                server = account.resource(server_name).connect(timeout=CONNECTION_TIMEOUT)
                last_connection_time = current_time
                return server
            
            raise ValueError("Insufficient Plex credentials provided")
            
        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt failed
                raise ValueError(f"Failed to connect to Plex after {max_retries} attempts: {str(e)}")
            
            # Wait before retrying
            time.sleep(retry_delay)
    
    # We shouldn't get here but just in case
    raise ValueError("Failed to connect to Plex server")
