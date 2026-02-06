# Plex MCP Server

A powerful Model-Controller-Protocol server for interacting with Plex Media Server, providing a standardized JSON-based interface for automation, scripting, and integration with other tools.

## Overview

Plex MCP Server creates a unified API layer on top of the Plex Media Server API, offering:

- **Standardized JSON responses** for compatibility with automation tools, AI systems, and other integrations
- **Multiple transport methods** (stdio and SSE) for flexible integration options
- **Rich command set** for managing libraries, collections, playlists, media, users, and more
- **Error handling** with consistent response formats
- **Easy integration** with automation platforms (like n8n) and custom scripts

## Requirements

- Python 3.8+
- Plex Media Server with valid authentication token
- Access to the Plex server (locally or remotely)

## Installation

### Option 1: Install from PyPI (Recommended)

```bash
pip install plex-mcp-server
```

Or with uv:
```bash
uv pip install plex-mcp-server
```

This installs the `plex-mcp-server` command globally.

### Option 2: Run with uvx (No Installation Required)

Run directly without installing:
```bash
uvx plex-mcp-server --transport stdio --plex-url http://your-server:32400 --plex-token your-token
```

### Option 3: Install from source

```bash
git clone https://github.com/vladimir-tutin/plex-mcp-server.git
cd plex-mcp-server
pip install .
```

## Configuration

You can configure your Plex credentials in several ways:

### Option A: Command Line Arguments (Recommended for Claude Desktop)

Pass credentials directly when running:
```bash
plex-mcp-server --transport stdio --plex-url http://your-server:32400 --plex-token your-token
```

### Option B: Environment File (.env)

Create a `.env` file in one of these locations:
- Your current working directory
- `~/.config/plex-mcp-server/.env` (recommended for installed version)

```bash
# Copy example and edit
cp .env.example .env
```

Contents:
```
PLEX_URL=http://your-plex-server:32400
PLEX_TOKEN=your-plex-token
```

### Option C: Environment Variables in Config

Set credentials via the `env` block in your client configuration (see examples below).

## Usage

The server can be run in two transport modes: stdio (Standard Input/Output) or SSE (Server-Sent Events). Each mode is suitable for different integration scenarios.

### Running with stdio Transport

The stdio transport is ideal for direct integration with applications like Claude Desktop or Cursor.

**If installed via pip:**
```bash
plex-mcp-server --transport stdio
```

**If running from source:**
```bash
python plex_mcp_server.py --transport stdio
```

#### Claude Desktop / Cursor Configuration

**Option 1: Using uvx (Recommended - No Installation Required)**
```json
{
  "plex": {
    "command": "uvx",
    "args": [
      "plex-mcp-server",
      "--transport",
      "stdio",
      "--plex-url",
      "http://your-server:32400",
      "--plex-token",
      "your-plex-token"
    ]
  }
}
```

**Option 2: Using CLI arguments (Requires pip install)**
```json
{
  "plex": {
    "command": "plex-mcp-server",
    "args": [
      "--transport",
      "stdio",
      "--plex-url",
      "http://your-server:32400",
      "--plex-token",
      "your-plex-token"
    ]
  }
}
```

**Option 3: Using environment variables**
```json
{
  "plex": {
    "command": "plex-mcp-server",
    "args": [
      "--transport",
      "stdio"
    ],
    "env": {
      "PLEX_URL": "http://your-server:32400",
      "PLEX_TOKEN": "your-plex-token"
    }
  }
}
```

**Option 4: Running from source**
```json
{
  "plex": {
    "command": "python",
    "args": [
      "C:/path/to/plex-mcp-server/plex_mcp_server.py",
      "--transport",
      "stdio"
    ],
    "env": {
      "PLEX_URL": "http://localhost:32400",
      "PLEX_TOKEN": "your-plex-token"
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
