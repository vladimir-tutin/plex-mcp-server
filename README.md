# Plex MCP Server

A comprehensive Multi-Chat-Provider (MCP) integration for Plex Media Server that enables AI assistants to interact with your Plex libraries, manage content, and control playback.

## Features

- **Library Management**: Browse, search, and get detailed information about your Plex libraries
- **Media Playback**: Start playback on Plex clients or external players
- **Content Discovery**: Search for media, view recently added content, and browse on-deck items
- **Metadata Management**: Edit media metadata including titles, summaries, and poster images
- **User Management**: View user information and activity
- **Collection & Playlist Management**: Create, edit, and manage collections and playlists
- **Server Monitoring**: View active sessions, logs, and server status

## Prerequisites

- Plex Media Server (latest version recommended)
- Plex account with admin privileges
- Python 3.8+
- An AI assistant that supports the MCP protocol

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/vladimir-tutin/plex-mcp-server.git
   cd plex-mcp-server
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Configure environment variables (see Configuration section)

4. Run the server:
   ```
   python plex_mcp_server.py
   ```

## Configuration

Configure the server using environment variables:

### Required Variables
- `PLEX_URL`: URL of your Plex server (e.g., `http://192.168.1.100:32400`)
- `PLEX_TOKEN`: Your Plex authentication token

### Alternative Authentication (if token not provided)
- `PLEX_USERNAME`: Your Plex username
- `PLEX_PASSWORD`: Your Plex password
- `PLEX_SERVER_NAME`: Name of your Plex server

## Usage

### Library Management

- `list_libraries`: List all available libraries on your Plex server
- `search_media`: Search for media across libraries or in a specific library
- `get_recently_added`: View recently added content
- `get_on_deck`: View in-progress content
- `get_library_stats`: Get statistics for a specific library
- `refresh_library`: Refresh a specific library or all libraries
- `scan_library`: Scan a specific library or path

### Media Playback

- `start_playback`: Start playback of media on a specified client
- `control_playback`: Control active playback sessions (play, pause, stop)
- `get_active_sessions`: View information about current playback sessions

### Metadata Management

- `edit_metadata`: Edit metadata for media items
- `get_media_poster`: Retrieve a media item's poster image
- `set_media_poster`: Set a new poster image for a media item
- `extract_media_images`: Extract all images associated with a media item
- `delete_media`: Remove items from your Plex library

### Playlists & Collections

- `list_playlists`: List all playlists
- `create_playlist`: Create a new playlist
- `add_to_playlist`: Add items to an existing playlist
- `remove_from_playlist`: Remove items from a playlist
- `delete_playlist`: Delete a playlist
- `list_collections`: List all collections
- `create_collection`: Create a new collection
- `add_to_collection`: Add items to an existing collection
- `remove_from_collection`: Remove items from a collection
- `delete_collection`: Delete a collection

### User Management

- `get_user_info`: Get detailed information about a specific Plex user
- `get_user_on_deck`: View on-deck items for a specific user
- `get_user_watch_history`: View watch history for a specific user
- `list_all_users`: List all users with access to the Plex server

### Server Monitoring

- `get_plex_logs`: Retrieve Plex server logs
- `get_library_details`: Get detailed information about a specific library

## Examples

### List all libraries
```python
await list_libraries()
```

### Search for media
```python
await search_media(query="The Matrix", library_name="Movies")
```

### Get recently added content
```python
await get_recently_added(count=10, library_name="TV Shows")
```

### Start playback
```python
await start_playback(media_title="Inception", client_name="Living Room TV")
```

### Edit metadata
```python
await edit_metadata(
    media_title="Star Wars", 
    library_name="Movies", 
    new_title="Star Wars: Episode IV - A New Hope",
    new_year=1977
)
```

### Create a collection
```python
await create_collection(
    collection_title="Marvel Movies",
    library_name="Movies",
    item_titles=["Iron Man", "Thor", "Captain America"]
)
```

## Troubleshooting

### Common Issues

1. **Connection Problems**:
   - Verify your Plex server is running
   - Ensure your PLEX_URL is correct and accessible
   - Check that your authentication credentials are valid

2. **Permission Issues**:
   - Ensure your Plex account has admin privileges
   - Verify you're using the correct Plex token

3. **Media Not Found**:
   - Use exact media titles when possible
   - Try searching with partial titles if exact matches fail

### Debug Mode

For detailed logs, set the environment variable:
```
DEBUG=true
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Acknowledgements

- [PlexAPI](https://github.com/pkkid/python-plexapi) - Python bindings for the Plex API
- [FastMCP](https://github.com/microsoft/mcp) - Multi-Chat-Provider protocol
