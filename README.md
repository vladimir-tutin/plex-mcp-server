# Plex MCP Server

A powerful Model-Controller-Protocol server for interacting with Plex Media Server, providing a standardized JSON-based interface for automation, scripting, and integration with other tools.

## Overview

Plex MCP Server creates a unified API layer on top of the Plex Media Server API, offering:

- **Standardized JSON responses** for compatibility with automation tools, AI systems, and other integrations
- **Multiple transport methods** (stdio, SSE, and streamable-http) for flexible integration options
- **Rich command set** for managing libraries, collections, playlists, media, users, and more
- **Error handling** with consistent response formats
- **Easy integration** with automation platforms (like n8n) and custom scripts

## Requirements

- Python 3.8+
- Plex Media Server with valid authentication token
- Access to the Plex server (locally or remotely)

## Installation

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file based on the `.env.example`:
   ```
   cp .env.example .env
   ```
4. Add your Plex server URL and token to the `.env` file:
   ```
   PLEX_URL=http://your-plex-server:32400
   PLEX_TOKEN=your-plex-token
   ```

## Usage

The server can be run in three transport modes: stdio (Standard Input/Output), SSE (Server-Sent Events), or streamable-http. Each mode is suitable for different integration scenarios.

### Running with stdio Transport

The stdio transport is ideal for direct integration with applications like Claude Desktop or Cursor. It accepts commands via standard input and outputs results to standard output in JSON format.

Basic command line usage:
```bash
python3 -m plex_mcp
```
or
```bash
python3 plex_mcp_server.py --transport stdio
```

#### Configuration Example for Claude Desktop/Cursor
Add this configuration to your application's settings:
```json
{
  "plex": {
    "command": "python",
    "args": [
      "C://Users//User//Documents//plex-mcp-server//plex_mcp_server.py",
      "--transport=stdio"
    ],
    "env": {
      "PLEX_URL":"http://localhost:32400",
      "PLEX_TOKEN":"av3khi56h634v3",
      "PLEX_USERNAME:"Administrator"
    }
  }
}
```

### Running with SSE Transport

The Server-Sent Events (SSE) transport provides a web-based interface for integration with web applications and services.

Start the server:
```bash
python3 plex_mcp_server.py --transport sse --host 0.0.0.0 --port 3001
```

Default options:
- Host: 0.0.0.0 (accessible from any network interface)
- Port: 3001
- SSE endpoint: `/sse`
- Message endpoint: `/messages/`

#### Configuration Example for SSE Client
When the server is running in SSE mode, configure your client to connect using:
```json
{
  "plex": {
    "url": "http://localhost:3001/sse"
  }
}
```

With SSE, you can connect to the server via web applications or tools that support SSE connections.

### Running with Streamable-HTTP Transport

The streamable-http transport provides a RESTful API interface for integration with web services and applications.

Start the server:
```bash
python3 plex_mcp_server.py --transport streamable-http
```

Default options:
- Host: 127.0.0.1
- Port: 8000

The streamable-http transport is ideal for containerized deployments and microservice architectures. When running in Docker:
```bash
docker run --rm -p 8000:8000 plex-mcp-server --transport streamable-http
```

## Command Modules

### Library Module
- List libraries
- Get library statistics
- Refresh libraries
- Scan for new content
- Get library details
- Get recently added content
- Get library contents

### Media Module
- Search for media
- Get detailed media information
- Edit media metadata
- Delete media
- Get and set artwork
- List available artwork

### Playlist Module
- List playlists
- Get playlist contents
- Create playlists
- Delete playlists
- Add items to playlists
- Remove items from playlists
- Edit playlists
- Upload custom poster images
- Copy playlists to other users

### Collection Module
- List collections
- Create collections
- Add items to collections
- Remove items from collections
- Edit collections

### User Module
- Search for users
- Get user information
- Get user's on deck content
- Get user watch history

### Sessions Module
- Get active sessions
- Get media playback history

### Server Module
- Get Plex server logs
- Get server information
- Get bandwidth statistics
- Get current resource usage
- Get and run butler tasks
- Get server alerts

### Client Module
- List clients
- Get client details
- Get client timelines
- Get active clients
- Start media playback
- Control playback (play, pause, etc.)
- Navigate client interfaces
- Set audio/subtitle streams

**Note:** The Client Module functionality is currently limited and not fully implemented. Some features may not work as expected or may be incomplete.

## Response Format

All commands return standardized JSON responses for maximum compatibility with various tools, automation platforms, and AI systems. This consistent structure makes it easy to process responses programmatically.

For successful operations, the response typically includes:
```json
{
  "success_field": true,
  "relevant_data": "value",
  "additional_info": {}
}
```

For errors, the response format is:
```json
{
  "error": "Error message describing what went wrong"
}
```

For multiple matches (when searching by title), results are returned as an array of objects with identifying information:
```json
[
  {
    "title": "Item Title",
    "id": 12345,
    "type": "movie",
    "year": 2023
  },
  {
    "title": "Another Item",
    "id": 67890,
    "type": "show",
    "year": 2022
  }
]
```

## Debugging

For development and debugging, you can use the included `watcher.py` script which monitors for changes and automatically restarts the server.

## License

[Include your license information here]
