# Plex MCP Server

A powerful Model-Context-Protocol (MCP) server for interacting with Plex Media Server. It provides a standardized JSON-based interface for automation, AI agents (like Claude), and custom integrations.

## Features

- **Standardized API**: Unified JSON responses for all Plex operations.
- **Multiple Transports**: Supports both `stdio` and `SSE` (Server-Sent Events).
- **Comprehensive Control**: Manage libraries, media, collections, playlists, clients, and users.
- **Remote Ready**: Built-in OAuth 2.1 support for integration with remote AI platforms like Claude.ai.
- **Admin Tools**: Access logs, monitor bandwidth, and run Butler tasks.

## Installation

### Option 1: Using uv (Recommended)

Run directly without installation:
```bash
uvx plex-mcp-server --transport stdio --plex-url http://your-server:32400 --plex-token your-token
```

### Option 2: Install via pip

```bash
pip install plex-mcp-server
```

### Option 3: Development / Source

```bash
git clone https://github.com/vladimir-tutin/plex-mcp-server.git
cd plex-mcp-server
pip install -e .
```

## Configuration

Set your Plex server URL and Token using one of these methods:

### 1. Command Line Arguments
```bash
plex-mcp-server --plex-url "http://192.168.1.10:32400" --plex-token "ABC123XYZ"
```

### 2. Environment Variables (.env)
Create a `.env` file in the current directory or `~/.config/plex-mcp-server/.env`:
```env
PLEX_URL=http://localhost:32400
PLEX_TOKEN=your-authentication-token
MCP_OAUTH_ENABLED=false
```

### 3. MCP Client Config
Example for Claude Desktop (`%APPDATA%/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "plex": {
      "command": "uvx",
      "args": [
        "plex-mcp-server",
        "--transport",
        "stdio",
        "--plex-url",
        "http://your-server:32400",
        "--plex-token",
        "your-token"
      ]
    }
  }
}
```

## Command Reference

### Library Module
Tools for exploring and managing your Plex libraries.

| Command | Description | Parameters |
|---------|-------------|------------|
| `library_list` | Lists all available libraries. | None |
| `library_get_stats` | Gets statistics (count, size, types) for a library. | `library_name` |
| `library_refresh` | Triggers a metadata refresh for a library. | `library_name` |
| `library_scan` | Scans a library for new files. | `library_name` |
| `library_get_details` | Gets detailed information about a library. | `library_name` |
| `library_get_recently_added` | Lists recently added items in a library. | `library_name`, `limit: int` |
| `library_get_contents` | Lists all items in a library. | `library_name`, `limit: int` |

### Media Module
Tools for searching, inspecting, and editing specific media items.

| Command | Description | Parameters |
|---------|-------------|------------|
| `media_search` | Search for media across all libraries. | `query`, `library_name`, `content_type` |
| `media_get_details` | Get comprehensive details for an item. | `media_title`, `library_name`, `media_id` |
| `media_edit_metadata` | Update tags, genres, summary, or title. | `media_title`, `library_name`, `new_title`, `new_summary`, `new_rating`, `new_release_date`, `new_genre`, `remove_genre`, `new_director`, `new_studio`, `new_tags` |
| `media_delete` | Remove an item from Plex. | `media_title`, `library_name`, `media_id` |
| `media_get_artwork` | Retrieve posters or background artwork. | `media_title`, `library_name`, `art_type: str` |
| `media_set_artwork` | Set artwork from a local path or URL. | `media_title`, `library_name`, `poster_path`, `poster_url`, `background_path`, `background_url` |
| `media_list_available_artwork` | List alternative artwork available for selection. | `media_title`, `library_name`, `art_type` |

### Playlist Module
Manage your personal and shared playlists.

| Command | Description | Parameters |
|---------|-------------|------------|
| `playlist_list` | List all available playlists. | None |
| `playlist_get_contents` | List items contained in a playlist. | `playlist_title`, `playlist_id` |
| `playlist_create` | Create a new playlist from items. | `title`, `items: List[str]` |
| `playlist_delete` | Delete a playlist. | `playlist_title`, `playlist_id` |
| `playlist_add_to` | Add media items to a playlist. | `playlist_title`, `items: List[str]`, `playlist_id` |
| `playlist_remove_from` | Remove specific items from a playlist. | `playlist_title`, `items: List[str]`, `playlist_id` |
| `playlist_edit` | Change playlist title or summary. | `playlist_title`, `new_title`, `new_summary`, `playlist_id` |
| `playlist_upload_poster` | Upload a custom poster image. | `playlist_title`, `image_path`, `playlist_id` |
| `playlist_copy_to_user` | Share/Copy a playlist to another user. | `playlist_title`, `username`, `playlist_id` |

### Collection Module
Organize movies and shows into collections.

| Command | Description | Parameters |
|---------|-------------|------------|
| `collection_list` | List collections in a specific library. | `library_name` |
| `collection_create` | Create a new collection. | `library_name`, `title`, `items: List[str]` |
| `collection_add_to` | Add items to an existing collection. | `library_name`, `collection_title`, `items: List[str]`, `collection_id` |
| `collection_remove_from` | Remove items from a collection. | `library_name`, `collection_title`, `items: List[str]`, `collection_id` |
| `collection_edit` | Edit collection metadata and settings. | `collection_title`, `collection_id`, `library_name`, `new_title`, `new_sort_title`, `new_summary`, `new_content_rating`, `new_labels`, `add_labels`, `remove_labels`, `poster_path`, `poster_url`, `background_path`, `background_url`, `new_advanced_settings` |
| `collection_delete` | Delete a collection. | `collection_title`, `collection_id`, `library_name` |

### User Module
Information about the server owner and shared users.

| Command | Description | Parameters |
|---------|-------------|------------|
| `user_search_users` | Search for shared users. | `search_term` |
| `user_list_all_users` | List all users with types and IDs. | None |
| `user_get_info` | Detailed info for a specific user. | `username` |
| `user_get_on_deck` | Get "On Deck" items for a user. | `username` |
| `user_get_watch_history` | Retrieve personal watch history. | `username`, `limit`, `content_type`, `user_id` |
| `user_get_statistics` | Watch progress and usage statistics. | `time_period`, `username` |

### Sessions Module
Monitor real-time server activity.

| Command | Description | Parameters |
|---------|-------------|------------|
| `sessions_get_active` | Get currently playing items and clients. | None |
| `sessions_get_media_playback_history` | History for a specific media item. | `media_title`, `library_name`, `media_id` |

### Server Module
Maintenance and administrative tools.

| Command | Description | Parameters |
|---------|-------------|------------|
| `server_get_plex_logs` | Retrieve lines from Plex logs. | `num_lines`, `log_type`, `start_line`, `list_files`, `search_term` |
| `server_get_info` | Basic server health and version info. | None |
| `server_get_bandwidth`| Bandwidth usage statistics. | `timespan`, `lan` |
| `server_get_current_resources` | CPU/Memory usage of the host/process. | None |
| `server_get_butler_tasks` | List scheduled maintenance tasks. | None |
| `server_get_alerts` | Listen for server notifications/alerts. | `timeout` |
| `server_run_butler_task` | Manually trigger a Butler task. | `task_name` |
| `server_empty_trash` | Empty trash for libraries. | `library_name` |
| `server_optimize_database` | Run database optimization. | None |
| `server_clean_bundles` | Clean up unused media bundles. | None |

### Client Module
Control playback and navigation on Plex clients.

| Command | Description | Parameters |
|---------|-------------|------------|
| `client_list` | List all available playback clients. | None |
| `client_get_details` | Detailed info for a client. | `client_name`, `client_id` |
| `client_get_timelines` | Current playback state/trackers. | `client_name`, `client_id` |
| `client_get_active` | Find currently reachable/active clients. | None |
| `client_start_playback` | Start playing a media item on a client. | `client_name`, `media_title`, `client_id`, `media_id` |
| `client_control_playback` | Play, Pause, Stop, Seek, Skip. | `client_name`, `action`, `offset`, `client_id` |
| `client_navigate` | Send remote control navigation commands. | `client_name`, `command`, `client_id` |
| `client_set_streams` | Changes audio or subtitle tracks. | `client_name`, `audio_stream_id`, `subtitle_stream_id`, `client_id` |

## Remote Access & OAuth

The Plex MCP Server can be integrated with remote platforms like **Claude.ai** via SSE and OAuth 2.1. This allows you to talk to your Plex server directly from the Claude interface.

### Enabling OAuth (Remote Mode)
1. Set `MCP_OAUTH_ENABLED=true` in your environment.
2. Configure `MCP_OAUTH_ISSUER` (e.g., your Authentik/Keycloak provider URL).
3. Set `MCP_SERVER_URL` to your public-facing URL.

### Discovery Endpoints
When OAuth is active, the following standard endpoints are exposed:
- `/.well-known/oauth-protected-resource`
- `/.well-known/oauth-authorization-server`

## Response Formats

All tools return information in JSON format for consistent parsing.

### Success Example
```json
{
  "status": "success",
  "data": {
    "title": "Inception",
    "year": 2010,
    "rating": 8.8
  }
}
```

### Error Example
```json
{
  "status": "error",
  "message": "Library 'Missing' not found."
}
```

### Multiple Matches
If an operation finds multiple items with the same name, it returns a list of specific identifiers:
```json
[
  {
    "title": "The Office",
    "id": 123,
    "type": "show",
    "year": 2005
  },
  {
    "title": "The Office",
    "id": 456,
    "type": "show",
    "year": 1995
  }
]
```

## Troubleshooting OAuth

- **401 Unauthorized**: Ensure your `MCP_OAUTH_ISSUER` exactly matches the issuer URL in your identity provider (including trailing slashes).
- **Public URL**: `MCP_SERVER_URL` must be reachable by the client (e.g., Claude.ai) and should use HTTPS.
- **Redirect URIs**: For Claude.ai, the redirect URI in your provider must be `https://claude.ai/api/mcp/auth_callback`.

## License

MIT License. See `LICENSE` for details.
