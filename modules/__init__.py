import os
import time
from mcp.server.fastmcp import FastMCP # type: ignore
from plexapi.server import PlexServer # type: ignore
from plexapi.myplex import MyPlexAccount # type: ignore

# Add dotenv for .env file support
try:
    from dotenv import load_dotenv # type: ignore

    # Config directory for the application
    CONFIG_DIR = os.path.expanduser("~/.config/plex-mcp-server")
    CONFIG_ENV_FILE = os.path.join(CONFIG_DIR, ".env")

    # Load environment variables - check multiple locations
    # Priority: 1) Current directory, 2) Config directory
    loaded = load_dotenv()  # Current directory
    if loaded:
        print("Loaded environment variables from .env in current directory")

    if os.path.exists(CONFIG_ENV_FILE):
        load_dotenv(CONFIG_ENV_FILE)
        print(f"Loaded environment variables from {CONFIG_ENV_FILE}")
    elif not loaded:
        print(f"No .env file found. Create one at {CONFIG_ENV_FILE} or in your current directory.")
        print("Required variables: PLEX_URL, PLEX_TOKEN")
except ImportError:
    print("Warning: python-dotenv not installed. Environment variables won't be loaded from .env file.")
    print("Install with: pip install python-dotenv")

# Initialize FastMCP server
mcp = FastMCP("plex-server")

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
            # Connect directly with URL and token
            if not plex_url or not plex_token:
                raise ValueError("PLEX_URL and PLEX_TOKEN are required")
            
            server = PlexServer(plex_url, plex_token, timeout=CONNECTION_TIMEOUT)
            last_connection_time = current_time
            return server
            
        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt failed
                raise ValueError(f"Failed to connect to Plex after {max_retries} attempts: {str(e)}")
            
            # Wait before retrying
            time.sleep(retry_delay)
    
    # We shouldn't get here but just in case
    raise ValueError("Failed to connect to Plex server")
