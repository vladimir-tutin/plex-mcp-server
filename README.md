# Plex MCP Server

Plex MCP Server is a versatile control panel for your Plex Media Server, allowing AI assistants and other applications to interact with your Plex libraries, collections, media, and users.

## Features

- Comprehensive access to Plex libraries
- Media search and playback control
- Collection and playlist management
- Media metadata editing
- User management
- Server monitoring

## Installation

1. Clone this repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Configure your Plex connection:
   - Create a `.env` file with your Plex URL and token:
   ```
   PLEX_URL=http://your-plex-server:32400
   PLEX_TOKEN=your-plex-token
   ```
   - Alternatively, set environment variables directly:
   ```bash
   export PLEX_URL=http://your-plex-server:32400
   export PLEX_TOKEN=your-plex-token
   ```

## Running the Server

The server can be launched in two different modes depending on your needs:

### Command Line Mode (Default)

Run the server directly from the command line:

```bash
python plex_mcp_server.py
# or explicitly specify stdio transport
python plex_mcp_server.py --transport stdio
```

### Web Server Mode

Run the server as a web service to allow access from web applications:

```bash
python plex_mcp_server.py --transport sse --host 0.0.0.0 --port 8080
```

In this mode, the server endpoints are:
- Server URL: `http://[host]:[port]`
- SSE endpoint: `/sse`
- Message endpoint: `/messages/`

## Integrating with Claude Desktop or Cursor

You can easily integrate Plex MCP Server with Claude Desktop or other MCP-compatible applications.

### Claude Desktop Integration

1. Open Claude Desktop and go to Settings → Developer → Edit Config
2. Add the following to your configuration file (replacing paths as needed):

```json
{
  "mcpServers": {
    "plex-server": {
      "command": "python",
      "args": [
        "C:\\path\\to\\plex_mcp_server.py",
        "--transport",
        "stdio"
      ],
      "env": {
        "PLEX_URL": "http://your-plex-server:32400",
        "PLEX_TOKEN": "your-plex-token"
      }
    }
  }
}
```

3. Restart Claude Desktop
4. Look for the tools icon in the input box to access Plex functions
   
## Available Tools

Plex MCP Server provides numerous tools for interacting with your Plex server:

- Library management: list, refresh, scan libraries
- Media operations: search, play, edit metadata
- Collection management: create, edit, delete collections
- Playlist handling: create and manage playlists
- User information: view activity, history, and details
- Server monitoring: logs, active sessions

## Environment Variables

- `PLEX_URL`: URL of your Plex server (required)
- `PLEX_TOKEN`: Authentication token for your Plex server (required)
- `PLEX_USERNAME`: Plex username (optional, alternative to token)
- `PLEX_PASSWORD`: Plex password (optional, alternative to token)
- `PLEX_SERVER_NAME`: Name of your Plex server (required if using username/password)

## Restarting the Server

If you make changes to the configuration or the server is unresponsive, restart it using the same command you used to start it initially.

## Troubleshooting

- Verify your Plex server is running and accessible
- Check that your Plex token is valid
- Ensure required Python packages are installed
- Check logs for detailed error information

## License

[License information]
