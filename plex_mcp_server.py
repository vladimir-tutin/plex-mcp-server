import os
import io
import base64
import requests
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

from mcp.server.fastmcp import FastMCP
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import NotFound, Unauthorized, BadRequest
from plexapi.media import Media
from plexapi.playlist import Playlist
from plexapi.collection import Collection
from plexapi.photo import Photo
from plexapi.library import Library, LibrarySection
import traceback

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
    
    # Check if we have a valid connectiond
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

# Tool implementation
@mcp.tool()
async def list_libraries() -> str:
    """List all available libraries on the Plex server."""
    try:
        plex = connect_to_plex()
        libraries = plex.library.sections()
        
        if not libraries:
            return "No libraries found on your Plex server."
        
        result = "Available Plex libraries:\n"
        for lib in libraries:
            result += f"- {lib.title} ({lib.type}): {lib.totalSize} items\n"
        
        return result
    except Exception as e:
        return f"Error listing libraries: {str(e)}"

@mcp.tool()
async def search_media(query: str, library_name: Optional[str] = None) -> str:
    """Search for media across all libraries or in a specific library.
    
    Args:
        query: Search term to look for
        library_name: Optional library name to limit search to
    """
    try:
        plex = connect_to_plex()
        results = []
        
        # Special case for listing all movies
        if query.lower() in ["*all*", "*movies*", "*all movies*"] and library_name and library_name.lower() == "movies":
            try:
                library = plex.library.section(library_name)
                all_movies = library.all()
                if all_movies:
                    output = "All movies in your library:\n\n"
                    for movie in all_movies[:100]:  # Limit to first 100 movies
                        year = getattr(movie, 'year', '')
                        year_str = f" ({year})" if year else ""
                        output += f"- {movie.title}{year_str}\n"
                    
                    if len(all_movies) > 100:
                        output += f"\n... and {len(all_movies) - 100} more movies (total: {len(all_movies)})\n"
                    return output
            except Exception as e:
                return f"Error listing all movies: {str(e)}"
                
        if library_name:
            try:
                library = plex.library.section(library_name)
                
                # Different search approaches for specific media types
                if library.type == "movie":
                    # For movies, using title filter is often more accurate
                    title_matches = library.search(title=query)
                    # Also try the general query search
                    query_matches = library.search(query=query)
                    
                    # Combine unique results with title matches first
                    seen_ids = set()
                    for item in title_matches:
                        results.append(item)
                        seen_ids.add(item.ratingKey)
                    
                    for item in query_matches:
                        if item.ratingKey not in seen_ids:
                            results.append(item)
                
                elif library.type == "show":
                    # For TV shows, we need to search for shows, seasons, and episodes
                    # Start with show-level matches
                    show_matches = library.search(query=query)
                    results.extend(show_matches)
                    
                    # Try to find episode matches
                    try:
                        episode_matches = library.searchEpisodes(query=query)
                        if episode_matches:
                            results.extend(episode_matches)
                    except:
                        # searchEpisodes might not be supported in all PlexAPI versions
                        pass
                else:
                    # For other library types
                    results = library.search(query=query)
                
            except NotFound:
                return f"Library '{library_name}' not found."
            except Exception as e:
                return f"Error searching in library '{library_name}': {str(e)}"
        else:
            # Global search
            results = plex.search(query=query)
        
        if not results:
            return f"No results found for '{query}'."
        
        output = f"Search results for '{query}':\n\n"
        
        # Group results by type
        results_by_type = {}
        for item in results:
            item_type = getattr(item, 'type', 'unknown')
            if item_type not in results_by_type:
                results_by_type[item_type] = []
            results_by_type[item_type].append(item)
        
        # Output results organized by type
        for item_type, items in results_by_type.items():
            output += f"=== {item_type.upper()} ===\n"
            for item in items[:10]:  # Limit to 10 items per type to avoid huge outputs
                try:
                    # Basic info for all types
                    title = getattr(item, 'title', 'Unknown')
                    year = getattr(item, 'year', '')
                    
                    # Different formatting based on type
                    if item_type == 'movie':
                        output += f"- {title} ({year})\n"
                    elif item_type == 'show':
                        output += f"- {title} ({year})\n"
                    elif item_type == 'episode':
                        show_title = getattr(item, 'grandparentTitle', 'Unknown Show')
                        season_num = getattr(item, 'parentIndex', '')
                        episode_num = getattr(item, 'index', '')
                        season_ep = ""
                        if season_num and episode_num:
                            season_ep = f"S{season_num:02d}E{episode_num:02d} - "
                        output += f"- {show_title} - {season_ep}{title}\n"
                    elif item_type == 'album':
                        artist = getattr(item, 'parentTitle', 'Unknown Artist')
                        output += f"- {artist} - {title} ({year})\n" 
                    elif item_type == 'track':
                        artist = getattr(item, 'grandparentTitle', 'Unknown Artist')
                        album = getattr(item, 'parentTitle', 'Unknown Album')
                        output += f"- {artist} - {album} - {title}\n"
                    elif item_type == 'collection':
                        output += f"- {title}\n"
                    else:
                        output += f"- {title}\n"
                except Exception as e:
                    output += f"- <Error formatting {item_type} item: {str(e)}>\n"
            
            output += "\n"
        
        return output
        
    except Exception as e:
        return f"Error searching for media: {str(e)}"

@mcp.tool()
async def get_recently_added(count: int = 50, library_name: Optional[str] = None) -> str:
    """Get recently added media across all libraries or in a specific library.
    
    Args:
        count: Number of items to return (default: 50)
        library_name: Optional library name to limit results to
    """
    try:
        plex = connect_to_plex()
        
        if library_name:
            try:
                library = plex.library.section(library_name)
                # For TV libraries, we want to see individual episodes, not just shows
                if library.type in ['show', 'artist']:
                    # First get all recently added items from the library
                    all_items = []
                    
                    # Try to get episodes/tracks directly if the library supports it
                    if hasattr(library, 'searchEpisodes'):
                        all_items = library.searchEpisodes(sort="addedAt:desc", maxresults=count*5)
                    elif hasattr(library, 'episodes'):
                        all_items = library.episodes(sort="addedAt:desc", maxresults=count*5)
                    elif hasattr(library, 'all') and library.type == 'show':
                        # This is a fallback for TV libraries where we get episodes a different way
                        for show in library.all():
                            for episode in show.episodes():
                                all_items.append(episode)
                                if len(all_items) >= count*5:
                                    break
                            if len(all_items) >= count*5:
                                break
                                
                    # Sort all items by date added (newest first)
                    all_items.sort(key=lambda x: getattr(x, 'addedAt', datetime.min), reverse=True)
                    
                    # Get the most recent ones up to the count
                    recently_added = all_items[:count]
                else:
                    # For movies and other non-episodic libraries, just get the most recent items
                    recently_added = library.recentlyAdded(maxresults=count)
            except NotFound:
                return f"Library '{library_name}' not found."
            except Exception as e:
                return f"Error getting recently added items from library '{library_name}': {str(e)}"
        else:
            # Get recently added across all libraries
            recently_added = plex.library.recentlyAdded(maxresults=count)
        
        if not recently_added:
            return "No recently added items found."
        
        output = "Recently added:\n"
        for item in recently_added:
            try:
                # Get type and title
                item_type = getattr(item, 'type', 'unknown')
                title = getattr(item, 'title', 'Unknown')
                
                # Format date
                added_date = getattr(item, 'addedAt', None)
                date_str = ""
                if added_date:
                    date_str = f" [Added: {added_date.strftime('%Y-%m-%d')}]"
                
                # Format differently based on type
                if item_type == 'movie':
                    year = getattr(item, 'year', '')
                    year_str = f" ({year})" if year else ""
                    output += f"- {title}{year_str} [movie]{date_str}\n"
                elif item_type == 'show':
                    year = getattr(item, 'year', '')
                    year_str = f" ({year})" if year else ""
                    output += f"- {title}{year_str} [show]{date_str}\n"
                elif item_type == 'season':
                    show = getattr(item, 'parentTitle', 'Unknown Show')
                    output += f"- {show} - {title} [season]{date_str}\n"
                elif item_type == 'episode':
                    show = getattr(item, 'grandparentTitle', 'Unknown Show')
                    season_num = getattr(item, 'parentIndex', '')
                    episode_num = getattr(item, 'index', '')
                    season_ep = ""
                    if season_num and episode_num:
                        season_ep = f"S{season_num:02d}E{episode_num:02d} - "
                    output += f"- {show} - {season_ep}{title} [episode]{date_str}\n"
                elif item_type == 'track':
                    artist = getattr(item, 'grandparentTitle', 'Unknown Artist')
                    album = getattr(item, 'parentTitle', 'Unknown Album')
                    output += f"- {artist} - {album} - {title} [track]{date_str}\n"
                elif item_type == 'album':
                    artist = getattr(item, 'parentTitle', 'Unknown Artist')
                    output += f"- {artist} - {title} [album]{date_str}\n"
                else:
                    output += f"- {title} [{item_type}]{date_str}\n"
            except Exception as e:
                output += f"- <Error formatting item: {str(e)}>\n"
        
        return output
        
    except Exception as e:
        return f"Error getting recently added items: {str(e)}"

@mcp.tool()
async def get_on_deck() -> str:
    """Get on deck (in progress) media from Plex."""
    try:
        plex = connect_to_plex()
        on_deck = plex.library.onDeck()
        
        if not on_deck:
            return "No on deck items found."
        
        result = "On deck (in progress):\n"
        for item in on_deck:
            media_type = getattr(item, 'type', 'unknown')
            title = getattr(item, 'title', 'Unknown Title')
            
            if media_type == 'episode':
                show = getattr(item, 'grandparentTitle', 'Unknown Show')
                season = getattr(item, 'parentTitle', 'Unknown Season')
                result += f"- {show} - {season} - {title}\n"
            else:
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                result += f"- {title}{year_str} [{media_type}]\n"
            
            # Add progress information if available
            if hasattr(item, 'viewOffset') and hasattr(item, 'duration'):
                progress_pct = (item.viewOffset / item.duration) * 100
                result += f"  Progress: {progress_pct:.1f}%\n"
        
        return result
    except Exception as e:
        return f"Error getting on deck media: {str(e)}"

@mcp.tool()
async def get_library_stats(library_name: str) -> str:
    """Get statistics for a specific library.
    
    Args:
        library_name: Name of the library to get stats for
    """
    try:
        plex = connect_to_plex()
        
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        result = f"Statistics for '{library.title}' library:\n"
        result += f"Type: {library.type}\n"
        result += f"Total items: {library.totalSize}\n"
        
        if library.type == 'movie':
            result += f"Unwatched movies: {len(library.search(unwatched=True))}\n"
            
            # Get genres
            genres = {}
            for movie in library.all():
                for genre in getattr(movie, 'genres', []):
                    genres[genre.tag] = genres.get(genre.tag, 0) + 1
            
            # List top genres
            if genres:
                result += "\nTop genres:\n"
                sorted_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)
                for genre, count in sorted_genres[:5]:
                    result += f"- {genre}: {count} movies\n"
                
        elif library.type == 'show':
            shows = library.all()
            result += f"Number of shows: {len(shows)}\n"
            
            # Count episodes
            total_episodes = 0
            for show in shows:
                total_episodes += getattr(show, 'childCount', 0)
            result += f"Total episodes: {total_episodes}\n"
            
        return result
    except Exception as e:
        return f"Error getting library stats: {str(e)}"

@mcp.tool()
async def start_playback(media_title: str, client_name: Optional[str] = None, use_external_player: bool = False) -> str:
    """Start playback of a media item on a specified client or in the default video player.
    
    Args:
        media_title: Title of the media to play
        client_name: Name of the client to play on (optional)
        use_external_player: If True, open in system's default video player instead of Plex
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        results = plex.search(query=media_title)
        if not results:
            return f"No media found matching '{media_title}'."
        
        media = results[0]
        
        # If using external player, find the file path and open it
        if use_external_player:
            # Get the file path
            file_path = None
            
            # For movies and episodes, we need to access the media parts
            try:
                if hasattr(media, 'media') and media.media:
                    for media_item in media.media:
                        if hasattr(media_item, 'parts') and media_item.parts:
                            for part in media_item.parts:
                                if hasattr(part, 'file') and part.file:
                                    file_path = part.file
                                    break
                            if file_path:
                                break
                        if file_path:
                            break
            except Exception as e:
                return f"Error finding file path: {str(e)}"
            
            if not file_path:
                return f"Could not find file path for '{media_title}'."
            
            # Check if the file is accessible
            import os
            if not os.path.exists(file_path):
                # Try to get a direct play URL
                try:
                    # Get server connection info
                    server_url = plex._baseurl
                    token = plex._token
                    
                    # Find the direct play part ID
                    part_id = None
                    if hasattr(media, 'media') and media.media:
                        for media_item in media.media:
                            if hasattr(media_item, 'parts') and media_item.parts:
                                for part in media_item.parts:
                                    if hasattr(part, 'id'):
                                        part_id = part.id
                                        break
                                if part_id:
                                    break
                            if part_id:
                                break
                    
                    if part_id:
                        # Construct a direct streaming URL
                        stream_url = f"{server_url}/library/parts/{part_id}/file.mp4?X-Plex-Token={token}"
                        
                        # Try to detect VLC or launch the default video player
                        import subprocess
                        import shutil
                        
                        if os.name == 'nt':  # Windows
                            # Try to find VLC in common install locations
                            vlc_paths = [
                                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
                            ]
                            
                            vlc_path = None
                            for path in vlc_paths:
                                if os.path.exists(path):
                                    vlc_path = path
                                    break
                            
                            if vlc_path:
                                # Launch VLC with the URL
                                subprocess.Popen([vlc_path, stream_url])
                                return f"Opening '{media_title}' in VLC Player."
                            else:
                                # Try to check if VLC is in PATH
                                vlc_in_path = shutil.which("vlc")
                                if vlc_in_path:
                                    subprocess.Popen([vlc_in_path, stream_url])
                                    return f"Opening '{media_title}' in VLC Player."
                                else:
                                    # If VLC is not found, try launching with the system's default URL handler
                                    # but add a parameter that hints this is a media file
                                    import webbrowser
                                    webbrowser.open(stream_url)
                                    return f"Opening '{media_title}' streaming URL. If it opens in a browser, you may need to copy the URL and open it in your media player manually."
                        else:  # macOS/Linux
                            # Try to find VLC
                            vlc_in_path = shutil.which("vlc")
                            if vlc_in_path:
                                subprocess.Popen([vlc_in_path, stream_url])
                                return f"Opening '{media_title}' in VLC Player."
                            else:
                                # Fallback to the system's default open command
                                if os.name == 'posix':  # macOS/Linux
                                    subprocess.call(('open', stream_url))
                                
                                return f"Opening '{media_title}' streaming URL."
                    else:
                        return f"Could not find a direct URL for '{media_title}'."
                except Exception as url_error:
                    return f"Error getting direct URL: {str(url_error)}"
            
            # Open the file in the default video player if it exists
            import subprocess
            
            try:
                if os.name == 'nt':  # Windows
                    os.startfile(file_path)
                else:  # macOS and Linux
                    subprocess.call(('open', file_path))
                
                return f"Opening '{media_title}' in your default video player. File: {file_path}"
            except Exception as e:
                return f"Error opening file in external player: {str(e)}"
        
        else:
            # Original functionality: play on Plex client
            # Get available clients
            clients = plex.clients()
            if not clients:
                return "No Plex clients available for playback. If you want to play this media on your local device, try setting use_external_player=True."
            
            # Find the requested client or use the first available one
            target_client = None
            if client_name:
                for client in clients:
                    if client.title.lower() == client_name.lower():
                        target_client = client
                        break
                
                if target_client is None:
                    client_list = ", ".join([c.title for c in clients])
                    return f"Client '{client_name}' not found. Available clients: {client_list}"
            else:
                target_client = clients[0]
            
            # Start playback
            target_client.playMedia(media)
            return f"Started playback of '{media.title}' on '{target_client.title}'."
    except Exception as e:
        return f"Error starting playback: {str(e)}"

# New functions for metadata management
@mcp.tool()
async def edit_metadata(media_title: str, library_name: Optional[str] = None, 
                        new_title: Optional[str] = None, new_summary: Optional[str] = None, 
                        new_year: Optional[int] = None, new_rating: Optional[float] = None,
                        new_genre: Optional[str] = None, remove_genre: Optional[str] = None,
                        new_director: Optional[str] = None, new_studio: Optional[str] = None,
                        new_tags: Optional[List[str]] = None) -> str:
    """Edit metadata for a specific media item.
    
    Args:
        media_title: Title of the media to edit
        library_name: Optional library name to limit search to
        new_title: New title for the item
        new_summary: New summary/description
        new_year: New year
        new_rating: New rating (0-10)
        new_genre: New genre to add
        remove_genre: Genre to remove
        new_director: New director to add (movies only)
        new_studio: New studio to set
        new_tags: List of tags to add
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(query=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            results = plex.search(query=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."
        
        media = results[0]
        changes_made = []
        
        # Create edits dictionary
        edits = {}
        if new_title:
            edits['title'] = new_title
            changes_made.append(f"title changed to '{new_title}'")
        if new_summary:
            edits['summary'] = new_summary
            changes_made.append("summary updated")
        if new_year:
            edits['year'] = new_year
            changes_made.append(f"year changed to {new_year}")
        if new_rating is not None:
            edits['userRating'] = new_rating
            changes_made.append(f"rating changed to {new_rating}")
        if new_studio:
            edits['studio'] = new_studio
            changes_made.append(f"studio changed to '{new_studio}'")
        
        # Apply the basic edits
        if edits:
            try:
                media.edit(**edits)
            except Exception as e:
                return f"Error applying basic edits: {str(e)}"
        
        # Handle genres (add/remove)
        if new_genre:
            try:
                # Check if genre already exists
                existing_genres = [g.tag.lower() for g in media.genres]
                if new_genre.lower() not in existing_genres:
                    media.addGenre(new_genre)
                    changes_made.append(f"added genre '{new_genre}'")
            except Exception as e:
                return f"Error adding genre: {str(e)}"
                
        if remove_genre:
            try:
                # Find the genre object by tag name
                matching_genres = [g for g in media.genres if g.tag.lower() == remove_genre.lower()]
                if matching_genres:
                    media.removeGenre(matching_genres[0])
                    changes_made.append(f"removed genre '{remove_genre}'")
            except Exception as e:
                return f"Error removing genre: {str(e)}"
        
        # Handle directors (movies only)
        if new_director and hasattr(media, 'addDirector'):
            try:
                # Check if director already exists
                existing_directors = [d.tag.lower() for d in getattr(media, 'directors', [])]
                if new_director.lower() not in existing_directors:
                    media.addDirector(new_director)
                    changes_made.append(f"added director '{new_director}'")
            except Exception as e:
                return f"Error adding director: {str(e)}"
        
        # Handle tags
        if new_tags:
            for tag in new_tags:
                try:
                    # Check if tag already exists
                    existing_labels = [l.tag.lower() for l in getattr(media, 'labels', [])]
                    if tag.lower() not in existing_labels:
                        media.addLabel(tag)
                        changes_made.append(f"added tag '{tag}'")
                except Exception as e:
                    return f"Error adding tag '{tag}': {str(e)}"
        
        # Refresh to apply changes
        try:
            media.refresh()
        except Exception as e:
            return f"Changes were made but error occurred during refresh: {str(e)}"
        
        if not changes_made:
            return f"No changes were made to '{media.title}'."
            
        return f"Successfully updated metadata for '{media.title}'. Changes: {', '.join(changes_made)}."
    except Exception as e:
        return f"Error editing metadata: {str(e)}"

@mcp.tool()
async def get_media_poster(media_title: str, library_name: Optional[str] = None, 
                           output_path: Optional[str] = None, output_format: str = "base64") -> str:
    """Get the poster image for a specific media item.
    
    Args:
        media_title: Title of the media to get the poster for
        library_name: Optional library name to limit search to
        output_path: Optional path to save the poster to a file 
        output_format: Format to return image data in (base64, url, or file)
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        results = []
        if library_name:
            # Get all library sections
            all_sections = plex.library.sections()
            target_section = None
            
            # Find the section with the matching name (case-insensitive)
            for section in all_sections:
                if section.title.lower() == library_name.lower():
                    target_section = section
                    break
            
            if not target_section:
                return f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"
                
            # Use the found section
            try:
                # Use the appropriate parameter based on library type
                if target_section.type == 'show':
                    results = target_section.search(title=media_title)
                else:
                    results = target_section.search(query=media_title)
            except Exception as search_err:
                return f"Error searching in library: {str(search_err)}"
        else:
            # Search all libraries
            try:
                results = plex.search(query=media_title)
            except Exception as search_err:
                return f"Error searching all libraries: {str(search_err)}"
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            # Create a list of found items with more details to help user identify the correct one
            items_list = "\nFound items:\n"
            for idx, item in enumerate(results[:10], 1):  # Limit to first 10 for clarity
                item_type = getattr(item, 'type', 'unknown')
                title = getattr(item, 'title', 'Unknown Title')
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                
                if hasattr(item, 'librarySectionTitle'):
                    section_title = item.librarySectionTitle
                    items_list += f"{idx}. {title}{year_str} [{item_type}] - Library: {section_title}\n"
                else:
                    items_list += f"{idx}. {title}{year_str} [{item_type}]\n"
            
            if len(results) > 10:
                items_list += f"...and {len(results) - 10} more.\n"
                
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title.{items_list}"
        
        media = results[0]
        
        # Get the poster
        if not hasattr(media, 'thumb') or not media.thumb:
            return f"No poster found for '{media_title}'."
        
        # If we want to return a URL
        if output_format == "url":
            if hasattr(media, 'thumbUrl'):
                return f"Poster URL for '{media_title}':\n{media.thumbUrl}"
            else:
                return f"Poster URL not available for '{media_title}'."
        
        # Download the poster using the correct method
        try:
            # Use requests to download the poster using the thumbUrl
            if hasattr(media, 'thumbUrl') and media.thumbUrl:
                import requests
                response = requests.get(media.thumbUrl, timeout=10)
                response.raise_for_status()  # Raise exception for bad responses
                poster_data = response.content
            else:
                # Alternative method using the downloadPhoto method if available
                if hasattr(media, 'download') and callable(media.download):
                    poster_data = media.download(media.thumb)
                else:
                    # Fallback to using downloadUrl from the server
                    poster_data = plex.downloadPhoto(media.thumb)
        except Exception as download_error:
            return f"Error downloading poster: {str(download_error)}"
        
        # If we want to save the poster to a file
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(poster_data)
            return f"Poster for '{media_title}' saved to {output_path}."
        
        # New option to open in external viewer
        if output_format == "open":
            import tempfile
            import os
            import subprocess
            
            # Create a temp file with the right extension
            fd, temp_file_path = tempfile.mkstemp(suffix='.jpg')
            try:
                # Write the image data to the temp file
                with os.fdopen(fd, 'wb') as tmp:
                    tmp.write(poster_data)
                
                # Open with system default application
                if os.name == 'nt':  # Windows
                    os.startfile(temp_file_path)
                    return f"Opening poster for '{media_title}' in default image viewer. Temp file: {temp_file_path}"
                else:  # macOS and Linux
                    subprocess.call(('open', temp_file_path))
                    return f"Opening poster for '{media_title}' in default image viewer. Temp file: {temp_file_path}"
            except Exception as e:
                return f"Error opening image in external viewer: {str(e)}"
        
        # Otherwise return as base64
        if output_format == "base64":
            try:
                poster_base64 = base64.b64encode(poster_data).decode('utf-8')
                # Return as HTML img tag that Claude can render
                mime_type = "image/jpeg"  # Most Plex posters are JPEGs
                return f"Poster for '{media_title}':\n<img src=\"data:{mime_type};base64,{poster_base64}\" alt=\"{media_title} poster\" />"
            except Exception as base64_error:
                return f"Error converting poster to base64: {str(base64_error)}"
        
        return f"Unsupported output format: {output_format}"
    except Exception as e:
        return f"Error getting poster: {str(e)}"

@mcp.tool()
async def set_media_poster(media_title: str, poster_path: str, 
                           library_name: Optional[str] = None) -> str:
    """Set a new poster image for a specific media item.
    
    Args:
        media_title: Title of the media to set the poster for
        poster_path: Path to the image file to use as poster
        library_name: Optional library name to limit search to
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(query=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            results = plex.search(query=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."
        
        media = results[0]
        
        # Check if the poster file exists
        if not os.path.isfile(poster_path):
            return f"Poster file not found: {poster_path}"
        
        # Upload the new poster
        with open(poster_path, 'rb') as f:
            media.uploadPoster(f)
        
        return f"Successfully set new poster for '{media_title}'."
    except Exception as e:
        return f"Error setting poster: {str(e)}"

@mcp.tool()
async def extract_media_images(media_title: str, library_name: Optional[str] = None, 
                              output_dir: str = "./", image_types: List[str] = ["poster", "art"]) -> str:
    """Extract all images associated with a media item.
    
    Args:
        media_title: Title of the media to extract images from
        library_name: Optional library name to limit search to
        output_dir: Directory to save images to (default: current directory)
        image_types: Types of images to extract (e.g., poster, art, thumb, banner)
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(query=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            results = plex.search(query=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."
        
        media = results[0]
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Define image attributes to check
        image_attributes = {
            "poster": "thumb",
            "art": "art",
            "banner": "banner",
            "theme": "theme",
            "thumbnail": "thumb"
        }
        
        # Extract requested images
        extracted_images = []
        
        for img_type in image_types:
            attr = image_attributes.get(img_type.lower())
            if not attr:
                continue
                
            img_url = getattr(media, attr, None)
            if img_url:
                # Download the image
                try:
                    img_data = media._server.urlopen(img_url)
                    
                    # Create a filename based on media title and image type
                    safe_title = "".join(c if c.isalnum() else "_" for c in media.title)
                    img_path = os.path.join(output_dir, f"{safe_title}_{img_type}.jpg")
                    
                    # Save to file
                    with open(img_path, 'wb') as f:
                        f.write(img_data)
                    
                    extracted_images.append((img_type, img_path))
                except Exception as img_err:
                    return f"Error extracting {img_type} image: {str(img_err)}"
        
        if not extracted_images:
            return f"No images found for '{media_title}' with the requested types."
        
        # Prepare result message
        result = f"Extracted images for '{media_title}':\n"
        for img_type, img_path in extracted_images:
            result += f"- {img_type}: {img_path}\n"
        
        return result
    except Exception as e:
        return f"Error extracting images: {str(e)}"

# Functions for content management
@mcp.tool()
async def delete_media(media_title: str, library_name: Optional[str] = None, 
                       delete_files: bool = False) -> str:
    """Delete a media item from the Plex library.
    
    Args:
        media_title: Title of the media to delete
        library_name: Optional library name to limit search to
        delete_files: Whether to delete the actual media files from disk
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(query=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            results = plex.search(query=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."
        
        media = results[0]
        
        # Delete the media
        media.delete(delete_files=delete_files)
        
        if delete_files:
            return f"Successfully deleted '{media_title}' including media files."
        else:
            return f"Successfully removed '{media_title}' from Plex library (files not deleted)."
    except Exception as e:
        return f"Error deleting media: {str(e)}"

@mcp.tool()
async def refresh_library(library_name: str = None) -> str:
    """Refresh a specific library or all libraries.
    
    Args:
        library_name: Optional name of the library to refresh (refreshes all if None)
    """
    try:
        plex = connect_to_plex()
        
        if library_name:
            try:
                library = plex.library.section(library_name)
                library.refresh()
                return f"Successfully started refresh of library '{library_name}'."
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            # Refresh all libraries
            for library in plex.library.sections():
                library.refresh()
            return "Successfully started refresh of all libraries."
    except Exception as e:
        return f"Error refreshing library: {str(e)}"

@mcp.tool()
async def scan_library(library_name: str, path: Optional[str] = None) -> str:
    """Scan a specific library or part of a library.
    
    Args:
        library_name: Name of the library to scan
        path: Optional specific path to scan within the library
    """
    try:
        plex = connect_to_plex()
        
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        if path:
            library.update(path)
            return f"Successfully started scan of path '{path}' in library '{library_name}'."
        else:
            library.update()
            return f"Successfully started scan of library '{library_name}'."
    except Exception as e:
        return f"Error scanning library: {str(e)}"

# Functions for sessions and playback
@mcp.tool()
async def get_active_sessions() -> str:
    """Get information about current playback sessions, including IP addresses."""
    try:
        plex = connect_to_plex()
        sessions = plex.sessions()
        
        if not sessions:
            return "No active playback sessions."
        
        result = f"Active sessions ({len(sessions)}):\n"
        
        for session in sessions:
            # Get player/device info for IP
            player = getattr(session, 'player', None)
            ip_address = getattr(player, 'address', 'Unknown IP') if player else 'Unknown IP'
            player_title = getattr(player, 'title', 'Unknown Device') if player else 'Unknown Device'
            player_state = getattr(player, 'state', 'Unknown State') if player else 'Unknown State'
            player_platform = getattr(player, 'platform', 'Unknown Platform') if player else 'Unknown Platform'
            player_product = getattr(player, 'product', '') if player else ''
            player_version = getattr(player, 'version', '') if player else ''
            
            # Get user info
            user = getattr(session, 'usernames', None) or getattr(session, 'username', 'Unknown User')
            
            # Get media info
            title = getattr(session, 'title', 'Unknown Title')
            media_type = getattr(session, 'type', 'unknown')
            
            # Get more detailed media info
            year = getattr(session, 'year', '')
            duration = getattr(session, 'duration', 0)
            
            # Format media info based on type
            if media_type == 'episode':
                show = getattr(session, 'grandparentTitle', 'Unknown Show')
                season = getattr(session, 'parentTitle', 'Unknown Season')
                episode_num = getattr(session, 'index', 0)
                season_num = getattr(session, 'parentIndex', 0)
                media_info = f"{show} - S{season_num:02d}E{episode_num:02d} - {title}"
            elif media_type == 'movie':
                year_str = f" ({year})" if year else ""
                media_info = f"{title}{year_str}"
            else:
                media_info = title
            
            # Get session technical details
            session_id = getattr(session, 'sessionKey', 'Unknown ID')
            
            # Get progress information
            if hasattr(session, 'viewOffset') and hasattr(session, 'duration'):
                progress_pct = (session.viewOffset / session.duration) * 100
                current_mins = session.viewOffset // 60000
                current_secs = (session.viewOffset % 60000) // 1000
                total_mins = session.duration // 60000
                total_secs = (session.duration % 60000) // 1000
                progress_info = f"{current_mins:02d}:{current_secs:02d}/{total_mins:02d}:{total_secs:02d} ({progress_pct:.1f}%)"
            else:
                progress_info = "Unknown progress"
            
            # Get transcoding info - first check if there are media info objects
            stream_info = []
            transcode_info = "Unknown"
            video_info = "Unknown"
            audio_info = "Unknown"
            bandwidth = "Unknown"
            
            # Get Media objects for detailed technical info
            media_list = getattr(session, 'media', [])
            if media_list and len(media_list) > 0:
                # Take the active Media object
                media_obj = media_list[0]
                
                # Get container, bitrate, etc.
                container = getattr(media_obj, 'container', 'Unknown')
                bitrate = getattr(media_obj, 'bitrate', 'Unknown')
                if isinstance(bitrate, int):
                    bitrate = f"{bitrate/1000:.1f} Mbps" if bitrate > 1000000 else f"{bitrate/1000:.0f} kbps"
                
                # Check for transcoding vs direct play/stream
                if hasattr(media_obj, 'transcodeSession') and media_obj.transcodeSession:
                    transcode_session = media_obj.transcodeSession
                    transcode_info = "Transcoding"
                    transcode_progress = getattr(transcode_session, 'progress', 0)
                    transcode_speed = getattr(transcode_session, 'speed', 0)
                    transcode_throttled = getattr(transcode_session, 'throttled', False)
                    
                    if transcode_throttled:
                        transcode_info += f" (Throttled, {transcode_speed}x speed, {transcode_progress}% complete)"
                    else:
                        transcode_info += f" ({transcode_speed}x speed, {transcode_progress}% complete)"
                    
                    # Get transcoder video details
                    transcode_hw = getattr(transcode_session, 'videoDecision', 'Unknown')
                    if transcode_hw == 'transcode':
                        hw_decode = getattr(transcode_session, 'transcodeHwRequested', False)
                        if hw_decode:
                            transcode_info += ", Hardware transcoding"
                    
                    # Add bandwidth information
                    bandwidth = getattr(transcode_session, 'bandwidth', 0)
                    if isinstance(bandwidth, int) and bandwidth > 0:
                        bandwidth = f"{bandwidth/1000:.1f} Mbps" if bandwidth > 1000000 else f"{bandwidth/1000:.0f} kbps"
                    
                else:
                    # Check individual streams
                    direct_play = True
                    direct_stream = False
                    
                    # Look at part streams for conversion info
                    parts = getattr(media_obj, 'parts', [])
                    if parts and len(parts) > 0:
                        part = parts[0]
                        streams = getattr(part, 'streams', [])
                        
                        # Check each stream to see if any are being converted
                        for stream in streams:
                            stream_type = getattr(stream, 'streamType', 0)
                            decision = getattr(stream, 'decision', 'direct play')
                            
                            # StreamType 1 = Video, 2 = Audio, 3 = Subtitle
                            if stream_type == 1:  # Video stream
                                codec = getattr(stream, 'codec', 'unknown')
                                width = getattr(stream, 'width', 0)
                                height = getattr(stream, 'height', 0)
                                framerate = getattr(stream, 'frameRate', '0')
                                
                                # Video details
                                if width and height:
                                    video_info = f"{width}x{height}"
                                    if framerate:
                                        video_info += f" {framerate}fps"
                                    video_info += f" ({codec})"
                                else:
                                    video_info = f"{codec}"
                                
                                if decision != 'direct play':
                                    direct_play = False
                                    if decision == 'copy':
                                        direct_stream = True
                            
                            elif stream_type == 2:  # Audio stream
                                codec = getattr(stream, 'codec', 'unknown')
                                channels = getattr(stream, 'channels', 0)
                                language = getattr(stream, 'language', '')
                                
                                # Audio details
                                audio_info = f"{codec}"
                                if channels:
                                    if channels == 1:
                                        audio_info += " Mono"
                                    elif channels == 2:
                                        audio_info += " Stereo"
                                    elif channels == 6:
                                        audio_info += " 5.1"
                                    elif channels == 8:
                                        audio_info += " 7.1"
                                    else:
                                        audio_info += f" {channels} channels"
                                
                                if language:
                                    audio_info += f" ({language})"
                                
                                if decision != 'direct play':
                                    direct_play = False
                                    if decision == 'copy':
                                        direct_stream = True
                    
                    # Determine overall playback mode
                    if direct_play:
                        transcode_info = "Direct Play"
                    elif direct_stream:
                        transcode_info = "Direct Stream"
                    else:
                        transcode_info = "Transcoding"
            
            # Add information to result
            result += f"Session {session_id} - {media_info} [{media_type}]\n"
            result += f"  User: {user} | Device: {player_title} ({player_platform} {player_product} {player_version})\n"
            result += f"  IP: {ip_address} | State: {player_state} | Progress: {progress_info}\n"
            result += f"  Quality: {video_info} | Audio: {audio_info}\n"
            result += f"  Playback Mode: {transcode_info} | Bandwidth: {bandwidth}\n\n"
        
        return result
    except Exception as e:
        return f"Error getting active sessions: {str(e)}"

# Functions for user management
@mcp.tool()
async def get_user_info(username: str) -> str:
    """Get detailed information about a specific Plex user.
    
    Args:
        username: Name of the user to get information for
    """
    try:
        plex = connect_to_plex()
        
        # Try to find active sessions for this user
        active_sessions = []
        
        try:
            for session in plex.sessions():
                session_username = getattr(session, 'usernames', None) or getattr(session, 'username', '')
                if isinstance(session_username, list):
                    if username in session_username:
                        media_type = getattr(session, 'type', 'unknown')
                        title = getattr(session, 'title', 'Unknown')
                        
                        if media_type == 'episode':
                            show = getattr(session, 'grandparentTitle', '')
                            if show:
                                title = f"{show} - {title}"
                                
                        # Add progress information if available
                        if hasattr(session, 'viewOffset') and hasattr(session, 'duration'):
                            progress_pct = (session.viewOffset / session.duration) * 100
                            title += f" ({progress_pct:.1f}%)"
                        
                        active_sessions.append(title)
                else:
                    if username == session_username:
                        media_type = getattr(session, 'type', 'unknown')
                        title = getattr(session, 'title', 'Unknown')
                        
                        if media_type == 'episode':
                            show = getattr(session, 'grandparentTitle', '')
                            if show:
                                title = f"{show} - {title}"
                        
                        # Add progress information if available
                        if hasattr(session, 'viewOffset') and hasattr(session, 'duration'):
                            progress_pct = (session.viewOffset / session.duration) * 100
                            title += f" ({progress_pct:.1f}%)"
                        
                        active_sessions.append(title)
        except Exception as session_error:
            pass
        
        # Try to get detailed user information
        # This will only work if MyPlex functionality is available
        if hasattr(plex, 'myPlexAccount') and callable(plex.myPlexAccount):
            try:
                account = plex.myPlexAccount()
                
                # Get all users (friends) from the account
                try:
                    users = account.users()
                    users.append(account)  # Add the main account as well
                except Exception:
                    users = []
                
                # Find the user by username
                target_user = None
                for user in users:
                    user_username = getattr(user, 'username', '')
                    user_title = getattr(user, 'title', '')
                    user_email = getattr(user, 'email', '')
                    
                    if username == user_username or username == user_title or username == user_email:
                        target_user = user
                        break
                
                if target_user:
                    result = f"User information for {username}:\n"
                    result += f"Username: {getattr(target_user, 'username', 'N/A')}\n"
                    result += f"Title: {getattr(target_user, 'title', 'N/A')}\n"
                    result += f"Email: {getattr(target_user, 'email', 'N/A')}\n"
                    result += f"ID: {getattr(target_user, 'id', 'N/A')}\n"
                    
                    if hasattr(target_user, 'home') and target_user.home:
                        result += "Home User: Yes\n"
                    else:
                        result += "Home User: No\n"
                    
                    if hasattr(target_user, 'protected') and target_user.protected:
                        result += "Protected: Yes\n"
                    else:
                        result += "Protected: No\n"
                    
                    # List any active sessions
                    if active_sessions:
                        result += f"\nCurrently watching ({len(active_sessions)}):\n"
                        for session in active_sessions:
                            result += f"- {session}\n"
                    else:
                        result += "\nNot currently watching anything.\n"
                    
                    return result
                else:
                    # If we can't get detailed info, just return what we know
                    result = f"Limited information for user {username}:\n"
                    
                    if active_sessions:
                        result += f"Currently watching ({len(active_sessions)}):\n"
                        for session in active_sessions:
                            result += f"- {session}\n"
                    else:
                        result += "Not currently watching anything or user not found.\n"
                    
                    return result
            except Exception as myplex_error:
                # Basic info if MyPlex account not available
                result = f"Basic information for user {username}:\n"
                
                if active_sessions:
                    result += f"Currently watching ({len(active_sessions)}):\n"
                    for session in active_sessions:
                        result += f"- {session}\n"
                else:
                    result += "Not currently watching anything or user not found.\n"
                
                return result
        else:
            # Basic info if MyPlex account not available
            result = f"Basic information for user {username}:\n"
            
            if active_sessions:
                result += f"Currently watching ({len(active_sessions)}):\n"
                for session in active_sessions:
                    result += f"- {session}\n"
            else:
                result += "Not currently watching anything or user not found.\n"
            
            return result
    except Exception as e:
        return f"Error getting user information: {str(e)}"

# Functions for logs
@mcp.tool()
async def get_plex_logs(num_lines: int = 100, log_type: str = "server") -> str:
    """Get Plex server logs.
    
    Args:
        num_lines: Number of log lines to retrieve
        log_type: Type of log to retrieve (server, scanner, etc.)
    """
    try:
        import zipfile
        import io
        import tempfile
        import os
        import shutil
        
        plex = connect_to_plex()
        
        # Download logs as a zip file using the PlexAPI method
        logs_path_or_data = plex.downloadLogs()
        
        # Create a temp directory to extract files
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = ""
            
            # Check if we received a path to the zip file or the actual data
            if isinstance(logs_path_or_data, str) and (os.path.exists(logs_path_or_data) and logs_path_or_data.endswith('.zip')):
                # We got a path to the zip file
                zip_path = logs_path_or_data
            else:
                # We got the actual data
                if isinstance(logs_path_or_data, str):
                    logs_path_or_data = logs_path_or_data.encode('utf-8')
                
                # Save the zip file
                zip_path = os.path.join(temp_dir, "plex_logs.zip")
                with open(zip_path, 'wb') as f:
                    f.write(logs_path_or_data)
            
            if not os.path.exists(zip_path):
                return f"Could not find or create zip file: {zip_path}"
                
            # Extract the zip file
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
            except zipfile.BadZipFile:
                # If it's not a valid zip, return the content for debugging
                if zip_path != logs_path_or_data:  # If we created the zip
                    with open(zip_path, 'rb') as f:
                        first_bytes = f.read(100)
                    return f"Downloaded data is not a valid zip file. First 100 bytes: {first_bytes}"
                else:
                    return f"The file at {zip_path} is not a valid zip file."
            
            # Map common log type names to the actual file names
            log_type_map = {
                'server': 'Plex Media Server.log',
                'scanner': 'Plex Media Scanner.log',
                'transcoder': 'Plex Transcoder.log',
                'updater': 'Plex Update Service.log'
            }
            
            log_file_name = log_type_map.get(log_type.lower(), log_type)
            
            # Find the requested log file
            log_file_path = None
            all_files = []
            
            # Look for the log file in the extracted directory
            for root, dirs, files in os.walk(temp_dir):
                all_files.extend(files)
                for file in files:
                    if log_file_name.lower() in file.lower():
                        log_file_path = os.path.join(root, file)
                        break
                if log_file_path:
                    break
            
            if not log_file_path:
                return f"Could not find log file for type: {log_type}. Available files: {', '.join(all_files)}"
            
            # Read the log file and extract the requested number of lines
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                log_lines = f.readlines()
            
            # Get the last num_lines
            log_lines = log_lines[-num_lines:] if len(log_lines) > num_lines else log_lines
            
            result = f"Last {len(log_lines)} lines of {os.path.basename(log_file_path)}:\n\n"
            result += ''.join(log_lines)
            
            return result
    except Exception as e:
        return f"Error getting Plex logs: {str(e)}\n{traceback.format_exc()}"

# Functions for playlists and collections
@mcp.tool()
async def list_playlists() -> str:
    """List all playlists on the Plex server."""
    try:
        plex = connect_to_plex()
        playlists = plex.playlists()
        
        if not playlists:
            return "No playlists found on the Plex server."
        
        result = f"Found {len(playlists)} playlists:\n\n"
        
        for playlist in playlists:
            try:
                # Get basic information about the playlist
                title = getattr(playlist, 'title', 'Unknown')
                playlist_type = getattr(playlist, 'playlistType', 'Unknown')
                
                # Get item count safely
                item_count = 0
                try:
                    if hasattr(playlist, 'items') and callable(playlist.items):
                        items = playlist.items()
                        item_count = len(items) if items else 0
                except:
                    pass
                
                # Get duration safely
                duration_str = "Unknown duration"
                try:
                    if hasattr(playlist, 'duration') and playlist.duration:
                        duration_mins = playlist.duration // 60000
                        duration_secs = (playlist.duration % 60000) // 1000
                        duration_str = f"{duration_mins}:{duration_secs:02d}"
                except:
                    pass
                
                # Add playlist to result
                result += f"- {title} ({playlist_type})\n"
                result += f"  Items: {item_count} | Duration: {duration_str}\n"
            except Exception as item_error:
                # If there's an error with a specific playlist, still include it with minimal info
                title = getattr(playlist, 'title', 'Unknown')
                result += f"- {title} (Error retrieving details)\n"
        
        return result
    except Exception as e:
        return f"Error listing playlists: {str(e)}"

@mcp.tool()
async def create_playlist(title: str, item_titles: List[str], 
                          library_name: Optional[str] = None) -> str:
    """Create a new playlist with specified items.
    
    Args:
        title: Title for the new playlist
        item_titles: List of media titles to include in the playlist
        library_name: Optional library name to limit search to
    """
    try:
        plex = connect_to_plex()
        
        # Check if playlist already exists
        existing_playlists = plex.playlists()
        for playlist in existing_playlists:
            if playlist.title.lower() == title.lower():
                return f"A playlist with the title '{title}' already exists. Please choose a different title."
        
        # First get the actual media objects
        media_items = []
        not_found = []
        
        sections = []
        if library_name:
            try:
                section = plex.library.section(library_name)
                sections = [section]
            except Exception as e:
                return f"Error with library '{library_name}': {str(e)}"
        else:
            sections = plex.library.sections()
        
        # For each title, search for the media item
        for item_title in item_titles:
            found_item = None
            
            # Search in each section
            for section in sections:
                search_results = section.searchEpisodes(title=item_title) if section.type == 'show' else section.search(title=item_title)
                
                if search_results:
                    found_item = search_results[0]
                    media_items.append(found_item)
                    break
            
            if not found_item:
                not_found.append(item_title)
        
        if not media_items:
            return "No valid media items found for the playlist."
        
        # Now create the playlist with the actual media objects
        playlist = Playlist.create(plex, title=title, items=media_items)
        
        # Report results
        result = f"Successfully created playlist '{title}' with {len(media_items)} items."
        if not_found:
            result += f"\nThe following items were not found: {', '.join(not_found)}"
        
        return result
    except Exception as e:
        return f"Error creating playlist: {str(e)}"

@mcp.tool()
async def add_to_playlist(playlist_title: str, item_titles: List[str], 
                          library_name: Optional[str] = None) -> str:
    """Add items to an existing playlist.
    
    Args:
        playlist_title: Title of the playlist to add to
        item_titles: List of media titles to add to the playlist
        library_name: Optional library name to limit search to
    """
    try:
        plex = connect_to_plex()
        
        # Find the playlist
        playlists = plex.playlists()
        target_playlist = None
        
        for playlist in playlists:
            if playlist.title.lower() == playlist_title.lower():
                target_playlist = playlist
                break
        
        if not target_playlist:
            return f"Playlist '{playlist_title}' not found."
        
        # Find the media items
        items = []
        
        for item_title in item_titles:
            # Search for the media
            if library_name:
                try:
                    library = plex.library.section(library_name)
                    results = library.search(query=item_title)
                except NotFound:
                    return f"Library '{library_name}' not found."
            else:
                results = plex.search(query=item_title)
            
            if not results:
                return f"No media found matching '{item_title}'."
            
            # Add the first matching item
            items.append(results[0])
        
        if not items:
            return "No valid media items found to add to the playlist."
        
        # Add items to the playlist
        for item in items:
            target_playlist.addItems([item])
        
        return f"Successfully added {len(items)} items to playlist '{playlist_title}'."
    except Exception as e:
        return f"Error adding to playlist: {str(e)}"

@mcp.tool()
async def remove_from_playlist(playlist_title: str, item_titles: List[str]) -> str:
    """Remove items from a playlist.
    
    Args:
        playlist_title: Title of the playlist to remove from
        item_titles: List of media titles to remove from the playlist
    """
    try:
        plex = connect_to_plex()
        
        # Find the playlist
        playlists = plex.playlists()
        target_playlist = None
        
        for playlist in playlists:
            if playlist.title.lower() == playlist_title.lower():
                target_playlist = playlist
                break
        
        if not target_playlist:
            return f"Playlist '{playlist_title}' not found."
        
        # Get the items in the playlist
        playlist_items = target_playlist.items()
        
        # Find and remove the specified items
        items_removed = 0
        
        for item in playlist_items:
            if getattr(item, 'title', 'Unknown Title') in item_titles:
                target_playlist.removeItems([item])
                items_removed += 1
        
        if items_removed == 0:
            return f"No matching items found in playlist '{playlist_title}'."
        
        return f"Successfully removed {items_removed} items from playlist '{playlist_title}'."
    except Exception as e:
        return f"Error removing from playlist: {str(e)}"

@mcp.tool()
async def delete_playlist(playlist_title: str) -> str:
    """Delete a playlist.
    
    Args:
        playlist_title: Title of the playlist to delete
    """
    try:
        plex = connect_to_plex()
        
        # Find the playlist
        playlists = plex.playlists()
        target_playlist = None
        
        for playlist in playlists:
            if playlist.title.lower() == playlist_title.lower():
                target_playlist = playlist
                break
        
        if not target_playlist:
            return f"Playlist '{playlist_title}' not found."
        
        # Delete the playlist
        target_playlist.delete()
        
        return f"Successfully deleted playlist '{playlist_title}'."
    except Exception as e:
        return f"Error deleting playlist: {str(e)}"

@mcp.tool()
async def list_collections(library_name: Optional[str] = None) -> str:
    """List all collections on the Plex server or in a specific library.
    
    Args:
        library_name: Optional name of the library to list collections from
    """
    try:
        plex = connect_to_plex()
        
        if library_name and library_name != "null":
            try:
                library = plex.library.section(library_name)
                collections = library.collections()
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            # Get collections from all libraries
            collections = []
            for section in plex.library.sections():
                if hasattr(section, 'collections'):
                    collections.extend(section.collections())
        
        if not collections:
            return "No collections found."
        
        result = f"Collections ({len(collections)}):\n"
        
        for collection in collections:
            title = getattr(collection, 'title', 'Unknown Title')
            item_count = getattr(collection, 'childCount', 0)
            
            # Get the library this collection belongs to
            section_title = getattr(collection, 'librarySectionTitle', 'Unknown Library')
            
            result += f"- {title} - {item_count} items [{section_title}]\n"
        
        return result
    except Exception as e:
        return f"Error listing collections: {str(e)}"

@mcp.tool()
async def create_collection(collection_title: str, library_name: str, 
                           item_titles: List[str]) -> str:
    """Create a new collection with specified items.
    
    Args:
        collection_title: Title for the new collection
        library_name: Name of the library to create the collection in
        item_titles: List of media titles to include in the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
            
        # Check if collection already exists
        existing_collections = library.collections()
        for collection in existing_collections:
            if collection.title.lower() == collection_title.lower():
                return f"A collection with the title '{collection_title}' already exists in library '{library_name}'. Please choose a different title or use 'add_to_collection' to add items to the existing collection."
        
        # Find the media items
        items = []
        not_found = []
        
        for item_title in item_titles:
            found = False
            
            # Search for the item in the library based on its type
            if library.type == 'show':
                # For TV Shows
                results = library.searchShows(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
                else:
                    # Try searching for episodes
                    results = library.searchEpisodes(title=item_title)
                    if results:
                        items.append(results[0])
                        found = True
            elif library.type == 'movie':
                # For Movies
                results = library.search(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
            elif library.type == 'artist':
                # For Music
                results = library.search(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
            
            if not found:
                not_found.append(item_title)
        
        if not items:
            return "No valid media items found for the collection."
        
        # Create the collection
        try:
            from plexapi.collection import Collection
            collection = Collection.create(plex, collection_title, library, items)
            
            # Report results
            result = f"Successfully created collection '{collection_title}' with {len(items)} items in library '{library_name}'."
            if not_found:
                result += f"\nThe following items were not found: {', '.join(not_found)}"
            return result
        except Exception as e:
            return f"Error creating collection: {str(e)}"
    except Exception as e:
        return f"Error creating collection: {str(e)}"

@mcp.tool()
async def add_to_collection(collection_title: str, library_name: str, 
                           item_titles: List[str]) -> str:
    """Add items to an existing collection.
    
    Args:
        collection_title: Title of the collection to add to
        library_name: Name of the library containing the collection
        item_titles: List of media titles to add to the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        # Find the collection
        collections = library.collections()
        target_collection = None
        
        for collection in collections:
            if collection.title.lower() == collection_title.lower():
                target_collection = collection
                break
        
        if not target_collection:
            return f"Collection '{collection_title}' not found in library '{library_name}'."
        
        # Find the media items
        items = []
        not_found = []
        
        for item_title in item_titles:
            found = False
            
            # Search for the item in the library
            if library.type == 'show':
                # Try to find episodes
                results = library.searchEpisodes(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
                else:
                    # Try to find shows
                    results = library.search(title=item_title)
                    if results:
                        items.append(results[0])
                        found = True
            else:
                # For movies, music, etc.
                results = library.search(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
            
            if not found:
                not_found.append(item_title)
        
        if not items:
            return "No valid media items found to add to the collection."
        
        # Add items to the collection
        target_collection.addItems(items)
        
        result = f"Successfully added {len(items)} items to collection '{collection_title}'."
        if not_found:
            result += f"\nThe following items were not found: {', '.join(not_found)}"
        
        return result
    except Exception as e:
        return f"Error adding to collection: {str(e)}"

@mcp.tool()
async def remove_from_collection(collection_title: str, library_name: str, 
                                item_titles: List[str]) -> str:
    """Remove items from a collection.
    
    Args:
        collection_title: Title of the collection to remove from
        library_name: Name of the library containing the collection
        item_titles: List of media titles to remove from the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        # Find the collection
        collections = library.collections()
        target_collection = None
        
        for collection in collections:
            if collection.title.lower() == collection_title.lower():
                target_collection = collection
                break
        
        if not target_collection:
            return f"Collection '{collection_title}' not found in library '{library_name}'."
        
        # Get the items in the collection
        collection_items = target_collection.items()
        
        # Find and remove the specified items
        items_to_remove = []
        not_found = []
        
        for search_title in item_titles:
            found = False
            
            # Search for exact title matches first
            for item in collection_items:
                if getattr(item, 'title', '').lower() == search_title.lower():
                    items_to_remove.append(item)
                    found = True
                    break
            
            # If no exact match, try partial title matching
            if not found:
                for item in collection_items:
                    title = getattr(item, 'title', '')
                    if search_title.lower() in title.lower():
                        items_to_remove.append(item)
                        found = True
                        break
            
            if not found:
                not_found.append(search_title)
        
        if not items_to_remove:
            return f"No matching items found in collection '{collection_title}'."
        
        # Remove the items
        target_collection.removeItems(items_to_remove)
        
        result = f"Successfully removed {len(items_to_remove)} items from collection '{collection_title}'."
        if not_found:
            result += f"\nThe following items were not found: {', '.join(not_found)}"
        
        return result
    except Exception as e:
        return f"Error removing from collection: {str(e)}"

@mcp.tool()
async def delete_collection(collection_title: str, library_name: str) -> str:
    """Delete a collection.
    
    Args:
        collection_title: Title of the collection to delete
        library_name: Name of the library containing the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        # Find the collection
        collections = library.collections()
        target_collection = None
        
        for collection in collections:
            if collection.title.lower() == collection_title.lower():
                target_collection = collection
                break
        
        if not target_collection:
            return f"Collection '{collection_title}' not found in library '{library_name}'."
        
        # Delete the collection
        target_collection.delete()
        
        return f"Successfully deleted collection '{collection_title}'."
    except Exception as e:
        return f"Error deleting collection: {str(e)}"

@mcp.tool()
async def edit_collection_summary(collection_title: str, library_name: str, summary: str) -> str:
    """Edit a collection's summary.
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        summary: New summary to set for the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Edit the summary
        collection.edit(summary=summary)
        
        return f"Successfully updated summary for collection '{collection_title}'."
    except Exception as e:
        return f"Error editing collection summary: {str(e)}"

@mcp.tool()
async def edit_collection(
    collection_title: str, 
    library_name: str,
    new_title: Optional[str] = None,
    new_sort_title: Optional[str] = None,
    new_content_rating: Optional[str] = None,
    new_labels: Optional[List[str]] = None,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    poster_path: Optional[str] = None,
    background_path: Optional[str] = None,
    new_advanced_settings: Optional[Dict[str, Any]] = None
) -> str:
    """Comprehensively edit a collection's attributes.
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        new_title: New title for the collection
        new_sort_title: New sort title for the collection
        new_content_rating: New content rating (e.g., PG-13, R, etc.)
        new_labels: Set completely new labels (replaces existing)
        add_labels: Labels to add to existing ones
        remove_labels: Labels to remove from existing ones
        poster_path: Path to a new poster image file
        background_path: Path to a new background/art image file
        new_advanced_settings: Dictionary of advanced settings to apply
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Prepare edit parameters
        edit_kwargs = {}
        
        if new_title:
            edit_kwargs['title'] = new_title
        
        if new_sort_title:
            edit_kwargs['titleSort'] = new_sort_title
        
        if new_content_rating:
            edit_kwargs['contentRating'] = new_content_rating
        
        # Apply the edits to fields that can be edited directly
        if edit_kwargs:
            collection.edit(**edit_kwargs)
        
        # Handle labels separately since they require special handling
        if new_labels is not None:
            # Replace all labels
            current_labels = collection.labels
            for label in current_labels:
                collection.removeLabel(label)
            for label in new_labels:
                collection.addLabel(label)
        else:
            # Add specified labels
            if add_labels:
                for label in add_labels:
                    collection.addLabel(label)
            
            # Remove specified labels
            if remove_labels:
                for label in remove_labels:
                    collection.removeLabel(label)
        
        # Handle poster upload if provided
        if poster_path:
            if os.path.isfile(poster_path):
                collection.uploadPoster(filepath=poster_path)
            else:
                return f"Error: Poster file not found at '{poster_path}'"
        
        # Handle background/art upload if provided
        if background_path:
            if os.path.isfile(background_path):
                collection.uploadArt(filepath=background_path)
            else:
                return f"Error: Background file not found at '{background_path}'"
        
        # Handle advanced settings (these vary by media type and may require specific PlexAPI methods)
        if new_advanced_settings:
            for setting_name, setting_value in new_advanced_settings.items():
                # This is a placeholder - the actual implementation would depend on
                # which advanced settings are supported by PlexAPI for collections
                try:
                    setattr(collection, setting_name, setting_value)
                except Exception as setting_err:
                    return f"Error setting advanced property '{setting_name}': {str(setting_err)}"
        
        # Refresh to apply changes
        collection.reload()
        
        return f"Successfully updated collection '{collection_title}'."
    except Exception as e:
        return f"Error editing collection: {str(e)}"

@mcp.tool()
async def get_user_on_deck(username: str) -> str:
    """Get on deck (in progress) media for a specific user.
    
    Args:
        username: Name of the user to get on-deck items for
    """
    try:
        plex = connect_to_plex()
        
        # Try to switch to the user account to get their specific on-deck items
        if username.lower() == plex.myPlexAccount().username.lower():
            # This is the main account, use server directly
            on_deck_items = plex.library.onDeck()
        else:
            # For a different user, we need to get access to their account
            try:
                account = plex.myPlexAccount()
                
                # Find the user in the shared users
                target_user = None
                for user in account.users():
                    if user.username.lower() == username.lower() or user.title.lower() == username.lower():
                        target_user = user
                        break
                
                if not target_user:
                    return f"User '{username}' not found."
                
                # For a shared user, try to switch to that user and get their on-deck items
                # This requires admin privileges and may be limited by Plex server's capabilities
                user_token = target_user.get_token(plex.machineIdentifier)
                if not user_token:
                    return f"Unable to access on-deck items for user '{username}'. Token not available."
                
                user_plex = PlexServer(plex._baseurl, user_token)
                on_deck_items = user_plex.library.onDeck()
            except Exception as user_err:
                return f"Error accessing user '{username}': {str(user_err)}"
        
        if not on_deck_items:
            return f"No on-deck items found for user '{username}'."
        
        result = f"On deck for {username} ({len(on_deck_items)} items):\n"
        
        for item in on_deck_items:
            media_type = getattr(item, 'type', 'unknown')
            title = getattr(item, 'title', 'Unknown Title')
            
            if media_type == 'episode':
                show = getattr(item, 'grandparentTitle', 'Unknown Show')
                season = getattr(item, 'parentTitle', 'Unknown Season')
                result += f"- {show} - {season} - {title}"
            else:
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                result += f"- {title}{year_str} [{media_type}]"
            
            # Add progress information
            if hasattr(item, 'viewOffset') and hasattr(item, 'duration'):
                progress_pct = (item.viewOffset / item.duration) * 100
                
                # Format as minutes:seconds
                total_mins = item.duration // 60000
                current_mins = item.viewOffset // 60000
                total_secs = (item.duration % 60000) // 1000
                current_secs = (item.viewOffset % 60000) // 1000
                
                result += f" - {current_mins:02d}:{current_secs:02d}/{total_mins:02d}:{total_secs:02d} ({progress_pct:.1f}%)"
            
            result += "\n"
        
        return result
    except Exception as e:
        return f"Error getting on-deck items: {str(e)}"

@mcp.tool()
async def get_user_watch_history(username: str, limit: int = 10) -> str:
    """Get recent watch history for a specific user.
    
    Args:
        username: Name of the user to get watch history for
        limit: Maximum number of recently watched items to show
    """
    try:
        plex = connect_to_plex()
        
        # For the main account owner
        if username.lower() == plex.myPlexAccount().username.lower():
            history_items = plex.history(maxresults=limit)
        else:
            # For a different user, we need to get access to their account
            try:
                account = plex.myPlexAccount()
                
                # Find the user in the shared users
                target_user = None
                for user in account.users():
                    if user.username.lower() == username.lower() or user.title.lower() == username.lower():
                        target_user = user
                        break
                
                if not target_user:
                    return f"User '{username}' not found."
                
                # For a shared user, use accountID to filter history
                history_items = plex.history(maxresults=limit, accountID=target_user.id)
            except Exception as user_err:
                return f"Error accessing history for user '{username}': {str(user_err)}"
        
        if not history_items:
            return f"No watch history found for user '{username}'."
        
        result = f"Recent watch history for {username} ({len(history_items)} items):\n"
        
        for item in history_items:
            media_type = getattr(item, 'type', 'unknown')
            title = getattr(item, 'title', 'Unknown Title')
            
            # Format based on media type
            if media_type == 'episode':
                show = getattr(item, 'grandparentTitle', 'Unknown Show')
                season = getattr(item, 'parentTitle', 'Unknown Season')
                result += f"- {show} - {season} - {title}"
            else:
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                result += f"- {title}{year_str} [{media_type}]"
            
            # Add viewed date if available
            if hasattr(item, 'viewedAt') and item.viewedAt:
                viewed_at = item.viewedAt.strftime("%Y-%m-%d %H:%M")
                result += f" (Viewed: {viewed_at})"
            
            result += "\n"
        
        return result
    except Exception as e:
        return f"Error getting watch history: {str(e)}"
        
@mcp.tool()
async def get_media_playback_history(media_title: str, library_name: str = None) -> str:
    """Get playback history for a specific media item.
    
    Args:
        media_title: Title of the media to get history for
        library_name: Optional library name to limit search to
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        results = []
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(query=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            results = plex.search(query=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."
        
        media = results[0]
        media_type = getattr(media, 'type', 'unknown')
        
        # Format title differently based on media type
        if media_type == 'episode':
            show = getattr(media, 'grandparentTitle', 'Unknown Show')
            season = getattr(media, 'parentTitle', 'Unknown Season')
            formatted_title = f"{show} - {season} - {media.title}"
        else:
            year = getattr(media, 'year', '')
            year_str = f" ({year})" if year else ""
            formatted_title = f"{media.title}{year_str}"
        
        # Get the history using the history() method 
        try:
            history_items = media.history()
            
            if not history_items:
                return f"No playback history found for '{formatted_title}'."
            
            result = f"Playback history for '{formatted_title}' [{media_type}]:\n"
            result += f"Total plays: {len(history_items)}\n\n"
            
            for item in history_items:
                # Get the username if available
                account_id = getattr(item, 'accountID', None)
                account_name = "Unknown User"
                
                # Try to get the account name from the accountID
                if account_id:
                    try:
                        # This may not work unless we have admin privileges
                        account = plex.myPlexAccount()
                        if account.id == account_id:
                            account_name = account.title
                        else:
                            for user in account.users():
                                if user.id == account_id:
                                    account_name = user.title
                                    break
                    except:
                        # If we can't get the account name, just use the ID
                        account_name = f"User ID: {account_id}"
                
                # Get the timestamp when it was viewed
                viewed_at = getattr(item, 'viewedAt', None)
                viewed_at_str = viewed_at.strftime("%Y-%m-%d %H:%M") if viewed_at else "Unknown time"
                
                # Device information if available
                device_id = getattr(item, 'deviceID', None)
                device_name = "Unknown Device"
                
                # You'd need to implement a way to get device names from IDs
                # This would require additional API calls not covered here
                
                result += f"- {account_name} on {viewed_at_str} [{device_name}]\n"
            
            return result
            
        except AttributeError:
            # Fallback if history() method is not available
            # Get basic view information
            view_count = getattr(media, 'viewCount', 0) or 0
            last_viewed_at = getattr(media, 'lastViewedAt', None)
            
            if view_count == 0:
                return f"No one has watched '{formatted_title}' yet."
            
            # Format the basic results
            result = f"Playback history for '{formatted_title}' [{media_type}]:\n"
            result += f"View count: {view_count}\n"
            
            if last_viewed_at:
                last_viewed_str = last_viewed_at.strftime("%Y-%m-%d %H:%M") if hasattr(last_viewed_at, 'strftime') else str(last_viewed_at)
                result += f"Last viewed: {last_viewed_str}\n"
                
            # Add any additional account info if available
            account_info = getattr(media, 'viewedBy', [])
            if account_info:
                result += "\nWatched by:"
                for account in account_info:
                    result += f"\n- {account.title}"
            
            return result
        
    except Exception as e:
        return f"Error getting media playback history: {str(e)}"

@mcp.tool()
async def get_media_details(media_title: str, library_name: str = None) -> str:
    """Get detailed information about a specific media item, including when it was added.
    
    Args:
        media_title: Title of the media to get details for
        library_name: Optional library name to limit search to
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        results = []
        if library_name:
            # Get all library sections
            all_sections = plex.library.sections()
            target_section = None
            
            # Find the section with the matching name (case-insensitive)
            for section in all_sections:
                if section.title.lower() == library_name.lower():
                    target_section = section
                    break
            
            if not target_section:
                return f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"
                
            # Use the found section
            try:
                # Use the appropriate parameter based on library type
                if target_section.type == 'show':
                    results = target_section.search(title=media_title)
                else:
                    results = target_section.search(query=media_title)
            except Exception as search_err:
                return f"Error searching in library: {str(search_err)}"
        else:
            # Search all libraries
            try:
                results = plex.search(query=media_title)
            except Exception as search_err:
                return f"Error searching all libraries: {str(search_err)}"
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            # Create a list of found items with more details to help user identify the correct one
            items_list = "\nFound items:\n"
            for idx, item in enumerate(results[:10], 1):  # Limit to first 10 for clarity
                item_type = getattr(item, 'type', 'unknown')
                title = getattr(item, 'title', 'Unknown Title')
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                
                if hasattr(item, 'librarySectionTitle'):
                    section_title = item.librarySectionTitle
                    items_list += f"{idx}. {title}{year_str} [{item_type}] - Library: {section_title}\n"
                else:
                    items_list += f"{idx}. {title}{year_str} [{item_type}]\n"
            
            if len(results) > 10:
                items_list += f"...and {len(results) - 10} more.\n"
                
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title.{items_list}"
        
        media = results[0]
        media_type = getattr(media, 'type', 'unknown')
        
        # Format title differently based on media type
        if media_type == 'episode':
            show = getattr(media, 'grandparentTitle', 'Unknown Show')
            season = getattr(media, 'parentTitle', 'Unknown Season')
            formatted_title = f"{show} - {season} - {media.title}"
        else:
            year = getattr(media, 'year', '')
            year_str = f" ({year})" if year else ""
            formatted_title = f"{media.title}{year_str}"
        
        # Start building the result
        result = f"Details for '{formatted_title}' [{media_type}]:\n\n"
        
        # Get the library section
        if hasattr(media, 'librarySectionTitle'):
            result += f"Library: {media.librarySectionTitle}\n"
        
        # Get the added date
        added_at = getattr(media, 'addedAt', None)
        if added_at:
            added_at_str = added_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(added_at, 'strftime') else str(added_at)
            result += f"Added to Plex: {added_at_str}\n"
        
        # Basic information
        summary = getattr(media, 'summary', None)
        if summary:
            result += f"Summary: {summary}\n\n"
        
        # More details based on media type
        if media_type == 'movie':
            # Movie-specific details
            duration = getattr(media, 'duration', 0)
            if duration:
                hours = duration // 3600000
                minutes = (duration % 3600000) // 60000
                result += f"Duration: {hours}h {minutes}m\n"
            
            studio = getattr(media, 'studio', None)
            if studio:
                result += f"Studio: {studio}\n"
            
            content_rating = getattr(media, 'contentRating', None)
            if content_rating:
                result += f"Content Rating: {content_rating}\n"
            
            # Crew information
            directors = getattr(media, 'directors', [])
            if directors:
                result += "Directors: " + ", ".join([d.tag for d in directors]) + "\n"
            
            writers = getattr(media, 'writers', [])
            if writers:
                result += "Writers: " + ", ".join([w.tag for w in writers]) + "\n"
            
            # File information
            try:
                media_parts = []
                for m in media.media:
                    for p in m.parts:
                        media_parts.append(p)
                
                if media_parts:
                    result += "\nFile Information:\n"
                    for part in media_parts:
                        result += f"File: {getattr(part, 'file', 'Unknown')}\n"
                        result += f"Size: {getattr(part, 'size', 0) // (1024*1024)} MB\n"
            except:
                pass
        elif media_type == 'show':
            # TV Show specific details
            result += f"Year: {getattr(media, 'year', 'Unknown')}\n"
            
            # Get seasons
            try:
                seasons = media.seasons()
                result += f"\nSeasons: {len(seasons)}\n"
                
                for season in seasons:
                    season_title = getattr(season, 'title', f"Season {getattr(season, 'index', '?')}")
                    episode_count = getattr(season, 'leafCount', 0)
                    result += f"- {season_title}: {episode_count} episodes\n"
                    
                    # Get episodes for this season
                    try:
                        episodes = season.episodes()
                        for episode in episodes[:5]:  # Limit to first 5 episodes per season
                            ep_title = getattr(episode, 'title', 'Unknown')
                            ep_index = getattr(episode, 'index', '?')
                            result += f"  • Episode {ep_index}: {ep_title}\n"
                        
                        if len(episodes) > 5:
                            result += f"  • ... and {len(episodes) - 5} more episodes\n"
                    except:
                        pass
                    
            except Exception as e:
                result += f"\nError retrieving seasons: {str(e)}\n"
        
        return result
    except Exception as e:
        return f"Error getting media details: {str(e)}"

@mcp.tool()
async def list_all_users() -> str:
    """List all users with access to the Plex server, including their usernames, emails, and titles."""
    try:
        plex = connect_to_plex()
        
        # Get the main account
        try:
            account = plex.myPlexAccount()
            all_users = [account]  # Start with the main account
            
            # Add all shared users
            try:
                shared_users = account.users()
                all_users.extend(shared_users)
            except Exception as e:
                return f"Error getting shared users: {str(e)}"
            
            if not all_users:
                return "No users found for this Plex server."
            
            result = f"All Plex users ({len(all_users)}):\n\n"
            
            for user in all_users:
                username = getattr(user, 'username', 'N/A')
                title = getattr(user, 'title', 'N/A')
                email = getattr(user, 'email', 'N/A')
                user_id = getattr(user, 'id', 'N/A')
                
                is_home = getattr(user, 'home', False)
                is_admin = getattr(user, 'admin', False)
                
                result += f"User: {title}\n"
                result += f"  Username: {username}\n"
                result += f"  Email: {email}\n"
                result += f"  ID: {user_id}\n"
                result += f"  Home User: {'Yes' if is_home else 'No'}\n"
                result += f"  Admin: {'Yes' if is_admin else 'No'}\n\n"
            
            return result
        except Exception as acct_err:
            return f"Error accessing Plex account: {str(acct_err)}"
    except Exception as e:
        return f"Error listing users: {str(e)}"

@mcp.tool()
async def search_users(search_term: str) -> str:
    """Search for users with names, usernames, or emails containing the search term.
    
    Args:
        search_term: Term to search for in user information
    """
    try:
        plex = connect_to_plex()
        
        # Get the main account
        try:
            account = plex.myPlexAccount()
            all_users = [account]  # Start with the main account
            
            # Add all shared users
            try:
                shared_users = account.users()
                all_users.extend(shared_users)
            except Exception as e:
                return f"Error getting shared users: {str(e)}"
            
            if not all_users:
                return "No users found for this Plex server."
            
            # Fuzzy search for the term in various user fields
            matching_users = []
            search_term_lower = search_term.lower()
            
            for user in all_users:
                username = getattr(user, 'username', '').lower()
                title = getattr(user, 'title', '').lower()
                email = getattr(user, 'email', '').lower()
                
                if (search_term_lower in username or 
                    search_term_lower in title or 
                    search_term_lower in email):
                    matching_users.append(user)
            
            if not matching_users:
                return f"No users found containing '{search_term}' in their name, username, or email."
            
            result = f"Users matching '{search_term}' ({len(matching_users)}):\n\n"
            
            for user in matching_users:
                username = getattr(user, 'username', 'N/A')
                title = getattr(user, 'title', 'N/A')
                email = getattr(user, 'email', 'N/A')
                user_id = getattr(user, 'id', 'N/A')
                
                is_home = getattr(user, 'home', False)
                is_admin = getattr(user, 'admin', False)
                
                result += f"User: {title}\n"
                result += f"  Username: {username}\n"
                result += f"  Email: {email}\n"
                result += f"  ID: {user_id}\n"
                result += f"  Home User: {'Yes' if is_home else 'No'}\n"
                result += f"  Admin: {'Yes' if is_admin else 'No'}\n\n"
            
            return result
        except Exception as acct_err:
            return f"Error accessing Plex account: {str(acct_err)}"
    except Exception as e:
        return f"Error searching users: {str(e)}"

@mcp.tool()
async def get_library_details(library_name: str) -> str:
    """Get detailed information about a specific library, including folder paths and settings.
    
    Args:
        library_name: Name of the library to get details for
    """
    try:
        plex = connect_to_plex()
        
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        result = f"Detailed information for '{library.title}' library:\n\n"
        result += f"Type: {library.type}\n"
        result += f"Total items: {library.totalSize}\n"
        
        # Safe attributes that should be available in most cases
        safe_attributes = [
            'uuid', 'key', 'type', 'title', 'agent', 'scanner',
            'language', 'allowSync', 'content', 'refreshing',
            'thumb', 'art', 'composite', 'hidden', 'filters'
        ]
        
        for attr in safe_attributes:
            if hasattr(library, attr):
                value = getattr(library, attr)
                if value is not None and value != '':
                    result += f"{attr}: {value}\n"
        
        # Get folder locations
        if hasattr(library, 'locations') and library.locations:
            result += "\nFolder Locations:\n"
            for location in library.locations:
                result += f"{location}\n"
        
        # Try to get advanced library settings
        try:
            if hasattr(library, '_data') and isinstance(library._data, dict):
                result += "\nAdvanced Settings:\n"
                
                # Include some common advanced settings
                advanced_settings = [
                    'agent', 'scanner', 'enableAutoPhotoTags', 'enableBIFGeneration',
                    'episodeSortingMode', 'includeInGlobal', 'language', 'scannerIdentifier',
                    'enableAutoCinematrailers', 'enableCollectionAutoUpdates'
                ]
                
                for setting in advanced_settings:
                    if setting in library._data:
                        result += f"- {setting}: {library._data[setting]}\n"
        except:
            # Silently fail if we can't access _data
            pass
        
        return result
    except Exception as e:
        return f"Error getting library details: {str(e)}"

@mcp.tool()
async def refresh_item(media_title: str, media_type: str = None) -> str:
    """Refresh a specific item in the Plex library.
    
    Args:
        media_title: Title of the item to refresh
        media_type: Type of media (movie, show, artist, album, etc.)
    """
    try:
        plex = connect_to_plex()
        
        # Search for the item
        search_results = plex.search(media_title, mediatype=media_type)
        
        if not search_results:
            return f"No items found matching '{media_title}'."
        
        # Refresh each matching item
        refreshed_items = []
        for item in search_results:
            try:
                # Check if the item has a refresh method
                if hasattr(item, 'refresh'):
                    item.refresh()
                    item_title = getattr(item, 'title', 'Unknown')
                    item_type = getattr(item, 'type', 'Unknown')
                    refreshed_items.append(f"{item_title} ({item_type})")
            except Exception as item_error:
                pass  # Skip items that can't be refreshed
        
        if refreshed_items:
            return f"Successfully refreshed the following items: {', '.join(refreshed_items)}"
        else:
            return f"Found items matching '{media_title}', but none could be refreshed."
    except Exception as e:
        return f"Error refreshing item: {str(e)}"

@mcp.tool()
async def get_playlist_items(playlist_title: str, limit: int = 50) -> str:
    """Get the contents of a specific playlist.
    
    Args:
        playlist_title: Title of the playlist to view
        limit: Maximum number of items to show (default: 50)
    """
    try:
        plex = connect_to_plex()
        playlists = plex.playlists()
        
        # Find the requested playlist
        target_playlist = None
        for playlist in playlists:
            if playlist.title.lower() == playlist_title.lower():
                target_playlist = playlist
                break
        
        if not target_playlist:
            # Try partial matching if exact match not found
            for playlist in playlists:
                if playlist_title.lower() in playlist.title.lower():
                    target_playlist = playlist
                    break
        
        if not target_playlist:
            return f"No playlist found with title '{playlist_title}'."
        
        # Get playlist items
        try:
            items = target_playlist.items()
        except Exception as items_error:
            return f"Error retrieving items for playlist '{target_playlist.title}': {str(items_error)}"
        
        if not items:
            return f"Playlist '{target_playlist.title}' is empty."
        
        # Format results
        result = f"Contents of playlist '{target_playlist.title}' ({len(items)} items):\n\n"
        
        # Apply limit
        items_to_show = items[:limit]
        
        # Format based on item type
        for i, item in enumerate(items_to_show, 1):
            try:
                item_type = getattr(item, 'type', 'unknown')
                
                if item_type == 'track':
                    # For music tracks
                    title = getattr(item, 'title', 'Unknown Track')
                    artist = getattr(item, 'grandparentTitle', 'Unknown Artist')
                    album = getattr(item, 'parentTitle', 'Unknown Album')
                    
                    # Get duration
                    duration_str = ""
                    if hasattr(item, 'duration') and item.duration:
                        mins = item.duration // 60000
                        secs = (item.duration % 60000) // 1000
                        duration_str = f" ({mins}:{secs:02d})"
                    
                    result += f"{i}. {artist} - {title}{duration_str}\n   Album: {album}\n"
                
                elif item_type == 'movie':
                    # For movies
                    title = getattr(item, 'title', 'Unknown Movie')
                    year = getattr(item, 'year', '')
                    year_str = f" ({year})" if year else ""
                    
                    duration_str = ""
                    if hasattr(item, 'duration') and item.duration:
                        hours = item.duration // 3600000
                        mins = (item.duration % 3600000) // 60000
                        duration_str = f" - {hours}h {mins}m"
                    
                    result += f"{i}. {title}{year_str}{duration_str}\n"
                
                elif item_type == 'episode':
                    # For TV episodes
                    title = getattr(item, 'title', 'Unknown Episode')
                    show = getattr(item, 'grandparentTitle', 'Unknown Show')
                    season_num = getattr(item, 'parentIndex', 0)
                    episode_num = getattr(item, 'index', 0)
                    
                    result += f"{i}. {show} - S{season_num:02d}E{episode_num:02d} - {title}\n"
                
                else:
                    # Generic item
                    title = getattr(item, 'title', 'Unknown Item')
                    result += f"{i}. {title} ({item_type})\n"
            
            except Exception as item_error:
                result += f"{i}. Error retrieving item details\n"
        
        # Add message if there are more items
        if len(items) > limit:
            result += f"\n... and {len(items) - limit} more items (showing first {limit} of {len(items)} total)"
        
        return result
    except Exception as e:
        return f"Error getting playlist items: {str(e)}"

@mcp.tool()
async def edit_collection_mode(collection_title: str, library_name: str, mode: str) -> str:
    """Set the collection mode (how it displays in Plex).
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        mode: Collection mode ('default', 'hide', 'hideItems', or 'showItems')
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Map the mode string to the appropriate integer value
        # According to PlexAPI:
        # 0: Library default
        # 1: Hide Collection
        # 2: Hide Items in this Collection
        # 3: Show this Collection and its Items
        mode_map = {
            'default': 0,
            'hide': 1,
            'hideItems': 2,
            'showItems': 3
        }
        
        if mode not in mode_map:
            return f"Error: Invalid mode '{mode}'. Valid modes are: {', '.join(mode_map.keys())}"
        
        mode_value = mode_map[mode]
        
        # Set the collection mode using the collectionMode parameter
        collection.edit(collectionMode=mode_value)
        
        return f"Successfully set mode to '{mode}' for collection '{collection_title}'."
    except Exception as e:
        return f"Error setting collection mode: {str(e)}"

@mcp.tool()
async def edit_collection_content_rating(collection_title: str, library_name: str, content_rating: str) -> str:
    """Set the content rating for a collection.
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        content_rating: Content rating to set (e.g., 'G', 'PG', 'PG-13', 'R', 'X', etc.)
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Set the content rating
        collection.edit(contentRating=content_rating)
        
        return f"Successfully set content rating to '{content_rating}' for collection '{collection_title}'."
    except Exception as e:
        return f"Error setting content rating: {str(e)}"

@mcp.tool()
async def add_collection_labels(collection_title: str, library_name: str, labels: List[str]) -> str:
    """Add labels to a collection.
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        labels: List of labels to add to the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Add labels
        for label in labels:
            collection.addLabel(label)
        
        return f"Successfully added labels {labels} to collection '{collection_title}'."
    except Exception as e:
        return f"Error adding labels: {str(e)}"

@mcp.tool()
async def remove_collection_labels(collection_title: str, library_name: str, labels: Union[List[str], str]) -> str:
    """Remove labels from a collection.
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        labels: List of labels to remove from the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Ensure labels is a list
        if isinstance(labels, str):
            labels = [labels]
        
        # Remove labels
        for label in labels:
            collection.removeLabel(label)
        
        return f"Successfully removed labels {labels} from collection '{collection_title}'."
    except Exception as e:
        return f"Error removing labels: {str(e)}"

@mcp.tool()
async def remove_collection_label(collection_title: str, library_name: str, label: str) -> str:
    """Remove a single label from a collection.
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        label: Label to remove from the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Remove the label
        collection.removeLabel(label)
        
        return f"Successfully removed label '{label}' from collection '{collection_title}'."
    except Exception as e:
        return f"Error removing label: {str(e)}"

@mcp.tool()
async def remove_label_from_collection(collection_title: str, library_name: str, label_name: str) -> str:
    """Remove a label from a collection with special handling for numeric labels.
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        label_name: Label to remove from the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Get current labels for debugging
        current_labels = [label for label in collection.labels]
        print(f"Before removal - Current labels: {current_labels}")
        
        # Remove the label
        collection.removeLabel(label_name)
        
        # Get updated labels
        collection.reload()
        updated_labels = [label for label in collection.labels]
        print(f"After removal - Updated labels: {updated_labels}")
        
        return f"Successfully removed label '{label_name}' from collection '{collection_title}'."
    except Exception as e:
        return f"Error removing label: {str(e)}"

@mcp.tool()
async def get_collection_labels(collection_title: str, library_name: str) -> str:
    """Get all labels for a collection.
    
    Args:
        collection_title: Title of the collection
        library_name: Name of the library containing the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Get and return labels
        labels = [label for label in collection.labels]
        if labels:
            result = f"Labels for collection '{collection_title}':\n"
            for label in labels:
                result += f"- {label}\n"
            return result
        else:
            return f"Collection '{collection_title}' has no labels."
    except Exception as e:
        return f"Error getting collection labels: {str(e)}"

@mcp.tool()
async def remove_numeric_label(numeric_label: str) -> str:
    """Remove a numeric label from the ClaudeTest collection.
    
    Args:
        numeric_label: Numeric label to remove (MUST be passed as a string, e.g., "123" not 123)
    """
    try:
        plex = connect_to_plex()
        
        # Find the Movies library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == "movies":
                library = section
                break
        
        if not library:
            return "Error: Movies library not found."
        
        # Find the ClaudeTest collection
        collection = None
        for c in library.collections():
            if c.title.lower() == "claudetest":
                collection = c
                break
        
        if not collection:
            return "Error: ClaudeTest collection not found."
        
        # Get current labels
        current_labels = [label for label in collection.labels]
        print(f"Current labels: {current_labels}")
        
        # Strip any quotes if present
        label_to_remove = str(numeric_label).strip('"\'')
        collection.removeLabel(label_to_remove)
        
        # Check if it worked
        collection.reload()
        updated_labels = [label for label in collection.labels]
        print(f"Updated labels: {updated_labels}")
        
        if label_to_remove in updated_labels:
            return f"Failed to remove label '{label_to_remove}' from collection 'ClaudeTest'."
        else:
            return f"Successfully removed label '{label_to_remove}' from collection 'ClaudeTest'."
    except Exception as e:
        return f"Error removing label: {str(e)}"

# Keep the old function for backward compatibility
@mcp.tool()
async def remove_123_label() -> str:
    """Remove the '123' label from the ClaudeTest collection."""
    return await remove_numeric_label("123")

if __name__ == "__main__":
    # Initialize and run the server
    print("Starting Plex MCP Server...")
    print("Set PLEX_URL and PLEX_TOKEN environment variables for connection")
    mcp.run(transport='stdio')
