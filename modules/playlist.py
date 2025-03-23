from modules import mcp, connect_to_plex
from typing import List, Optional, Dict, Any, Union
from plexapi.playlist import Playlist # type: ignore
from plexapi.exceptions import NotFound # type: ignore

# Functions for playlists and collections
@mcp.tool()
async def list_playlists(library_name: str = None, content_type: str = None) -> str:
    """List all playlists on the Plex server.
    
    Args:
        library_name: Optional library name to filter playlists from
        content_type: Optional content type to filter playlists (audio, video, photo)
    """
    try:
        plex = connect_to_plex()
        
        # Get all playlists or filter by content type
        if content_type:
            # Normalize content type
            content_map = {
                'audio': 'audio', 
                'music': 'audio',
                'video': 'video', 
                'movie': 'video', 
                'show': 'video',
                'photo': 'photo', 
                'image': 'photo'
            }
            normalized_type = content_map.get(content_type.lower(), content_type.lower())
            playlists = plex.playlists(playlistType=normalized_type)
        else:
            playlists = plex.playlists()
        
        # Filter by library if specified
        if library_name:
            try:
                # Get the library section
                library = plex.library.section(library_name)
                
                # Get playlists specific to this library
                if hasattr(library, 'playlists') and callable(library.playlists):
                    # If the library has a playlists method, use it
                    library_playlists = library.playlists()
                    
                    # Filter the main playlists list to only include those from this library
                    playlist_ids = set(p.ratingKey for p in library_playlists)
                    playlists = [p for p in playlists if p.ratingKey in playlist_ids]
                else:
                    # Fallback: filter by checking each playlist's items
                    filtered_playlists = []
                    for playlist in playlists:
                        try:
                            # Check if any item in the playlist is from this library
                            items = playlist.items()
                            for item in items:
                                if hasattr(item, 'librarySectionID') and str(item.librarySectionID) == str(library.key):
                                    filtered_playlists.append(playlist)
                                    break
                        except:
                            pass  # Skip playlists with errors
                    playlists = filtered_playlists
            except Exception as library_error:
                return f"Error filtering by library '{library_name}': {str(library_error)}"
        
        if not playlists:
            filter_msg = ""
            if library_name and content_type:
                filter_msg = f" matching library '{library_name}' and type '{content_type}'"
            elif library_name:
                filter_msg = f" in library '{library_name}'"
            elif content_type:
                filter_msg = f" of type '{content_type}'"
                
            return f"No playlists found{filter_msg}."
        
        # Format the output
        filter_msg = ""
        if library_name and content_type:
            filter_msg = f" matching library '{library_name}' and type '{content_type}'"
        elif library_name:
            filter_msg = f" in library '{library_name}'"
        elif content_type:
            filter_msg = f" of type '{content_type}'"
            
        result = f"Found {len(playlists)} playlists{filter_msg}:\n\n"
        
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

# Helper function to find a track by title
async def find_track_by_title(plex, item_title: str, sections: List) -> Optional[Any]:
    """Find a track by title, using various formats and search methods.
    
    Supported formats:
    - "Artist - Track"
    - "Artist - Album - Track"
    - Direct track title
    
    Args:
        plex: The PlexServer instance
        item_title: The title to search for
        sections: List of library sections to search in
    
    Returns:
        The found track object or None if not found
    """
    # Check if it's in Artist - Track format
    if " - " in item_title:
        parts = item_title.split(" - ")
        
        # Artist - Track format
        if len(parts) == 2:
            artist_name, track_title = parts[0], parts[1]
            
            # Search in each music library
            for section in sections:
                if section.type != 'artist':
                    continue
                
                # Find the artist
                artists = section.search(title=artist_name, libtype='artist')
                if not artists:
                    continue
                
                # Look through the artist's tracks
                for artist in artists:
                    for album in artist.albums():
                        for track in album.tracks():
                            if track_title.lower() == track.title.lower():
                                return track
        
        # Artist - Album - Track format
        elif len(parts) == 3:
            artist_name, album_title, track_title = parts[0], parts[1], parts[2]
            
            # Search in each music library
            for section in sections:
                if section.type != 'artist':
                    continue
                
                # Find the artist
                artists = section.search(title=artist_name, libtype='artist')
                if not artists:
                    continue
                
                # Look for the album
                for artist in artists:
                    for album in artist.albums():
                        if album_title.lower() == album.title.lower():
                            # Look for the track
                            for track in album.tracks():
                                if track_title.lower() == track.title.lower():
                                    return track
    
    # Direct track search (search all music libraries)
    for section in sections:
        if section.type != 'artist':
            continue
        
        # Generic track search across all artists
        for artist in section.all()[:10]:  # Limit to first 10 for performance
            for album in artist.albums()[:5]:  # Limit to first 5 albums
                for track in album.tracks():
                    if track.title.lower() == item_title.lower():
                        return track
    
    # Nothing found
    return None

@mcp.tool()
async def create_playlist(playlist_title: str, item_titles: List[str], 
                          library_name: str = None, summary: str = None) -> str:
    """Create a new playlist with specified items.
    
    Args:
        playlist_title: Title for the new playlist
        item_titles: List of media titles to include in the playlist
        library_name: Optional library name to limit search to
        summary: Optional summary description for the playlist
    """
    try:
        plex = connect_to_plex()
        
        # Check if playlist already exists
        existing_playlists = plex.playlists()
        for playlist in existing_playlists:
            if playlist.title.lower() == playlist_title.lower():
                return f"A playlist with the title '{playlist_title}' already exists. Please choose a different title."
        
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
            
            # Check if it looks like an Artist - Track format
            if " - " in item_title:
                found_item = await find_track_by_title(plex, item_title, sections)
                if found_item:
                    media_items.append(found_item)
                    continue
            
            # Regular search in each section
            for section in sections:
                # For TV Shows, search episodes
                if section.type == 'show':
                    search_results = section.searchEpisodes(title=item_title)
                    if search_results:
                        found_item = search_results[0]
                        media_items.append(found_item)
                        break
                # For Music libraries, try to find tracks
                elif section.type == 'artist':
                    # Try to find a track with this title
                    search_results = []
                    for artist in section.all()[:10]:  # Limit to avoid excessive searching
                        for album in artist.albums()[:5]:  # Limit albums to search
                            for track in album.tracks():
                                if item_title.lower() in track.title.lower():
                                    search_results.append(track)
                                    if len(search_results) >= 5:  # Limit results
                                        break
                            if len(search_results) >= 5:
                                break
                        if len(search_results) >= 5:
                            break
                    
                    if search_results:
                        found_item = search_results[0]
                        media_items.append(found_item)
                        break
                # For other library types, use standard search
                else:
                    search_results = section.search(title=item_title)
                    if search_results:
                        found_item = search_results[0]
                        media_items.append(found_item)
                        break
            
            if not found_item:
                not_found.append(item_title)
        
        if not media_items:
            return "No valid media items found for the playlist."
        
        # Now create the playlist with the actual media objects
        playlist = Playlist.create(plex, title=playlist_title, items=media_items)
        
        # Set the summary if provided
        if summary:
            playlist.edit(summary=summary)
        
        # Report results
        result = f"Successfully created playlist '{playlist_title}' with {len(media_items)} items."
        if summary:
            result += f"\nSummary: {summary}"
        if not_found:
            result += f"\nThe following items were not found: {', '.join(not_found)}"
        
        return result
    except Exception as e:
        return f"Error creating playlist: {str(e)}"

@mcp.tool()
async def edit_playlist(playlist_title: str, new_title: str = None, 
                        new_summary: str = None) -> str:
    """Edit a playlist's details such as title and summary.
    
    Args:
        playlist_title: Title of the playlist to edit
        new_title: Optional new title for the playlist
        new_summary: Optional new summary for the playlist
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
        
        # Check if a new title would conflict with existing playlists
        if new_title and new_title.lower() != playlist_title.lower():
            for playlist in playlists:
                if playlist.title.lower() == new_title.lower():
                    return f"A playlist with the title '{new_title}' already exists. Please choose a different title."
        
        # Perform the edits
        if new_title or new_summary:
            target_playlist.edit(title=new_title, summary=new_summary)
            
            changes = []
            if new_title:
                changes.append(f"title to '{new_title}'")
            if new_summary:
                changes.append(f"summary to '{new_summary}'")
            
            return f"Successfully updated playlist '{playlist_title}': {', '.join(changes)}."
        else:
            return "No changes specified for the playlist."
    
    except Exception as e:
        return f"Error editing playlist: {str(e)}"

@mcp.tool()
async def upload_playlist_poster(playlist_title: str, poster_url: str = None, 
                                poster_filepath: str = None) -> str:
    """Upload a poster image for a playlist.
    
    Args:
        playlist_title: Title of the playlist to set poster for
        poster_url: URL to an image to use as poster
        poster_filepath: Local file path to an image to use as poster
    """
    try:
        if not poster_url and not poster_filepath:
            return "You must provide either a poster URL or a poster file path."
        
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
        
        # Upload the poster
        if poster_url:
            target_playlist.uploadPoster(url=poster_url)
            return f"Successfully uploaded poster for playlist '{playlist_title}' from URL."
        elif poster_filepath:
            target_playlist.uploadPoster(filepath=poster_filepath)
            return f"Successfully uploaded poster for playlist '{playlist_title}' from file."
    
    except Exception as e:
        return f"Error uploading playlist poster: {str(e)}"

@mcp.tool()
async def copy_playlist_to_user(playlist_title: str, username: str) -> str:
    """Copy a playlist to another user account.
    
    Args:
        playlist_title: Title of the playlist to copy
        username: Username of the user to copy the playlist to
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
        
        # Find the user
        users = plex.myPlexAccount().users()
        target_user = None
        
        for user in users:
            if user.username.lower() == username.lower() or user.email.lower() == username.lower() or user.title.lower() == username.lower():
                target_user = user
                break
        
        if not target_user:
            return f"User '{username}' not found."
        
        # Copy the playlist to the user
        target_playlist.copyToUser(target_user)
        
        return f"Successfully copied playlist '{playlist_title}' to user '{username}'."
    
    except Exception as e:
        return f"Error copying playlist to user: {str(e)}"

@mcp.tool()
async def add_to_playlist(playlist_title: str, item_titles: List[str], 
                          library_name: str = None) -> str:
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
        sections = []
        if library_name:
            try:
                section = plex.library.section(library_name)
                sections = [section]
            except Exception as e:
                return f"Error with library '{library_name}': {str(e)}"
        else:
            sections = plex.library.sections()
            
        # Look for media items
        media_items = []
        not_found = []
        
        for item_title in item_titles:
            found_item = None
            
            # Try to find track by title with Artist - Track format
            if " - " in item_title:
                found_item = await find_track_by_title(plex, item_title, sections)
                if found_item:
                    media_items.append(found_item)
                    continue
            
            # Regular search in sections
            for section in sections:
                # Use different search methods based on section type
                if section.type == 'show':
                    # For TV Shows, search episodes
                    search_results = section.searchEpisodes(title=item_title)
                elif section.type == 'artist':
                    # For Music libraries, search tracks
                    search_results = []
                    for artist in section.all()[:10]:  # Limit for performance
                        for album in artist.albums()[:5]:
                            for track in album.tracks():
                                if item_title.lower() in track.title.lower():
                                    search_results.append(track)
                                    if len(search_results) >= 3:  # Limit results
                                        break
                            if len(search_results) >= 3:
                                break
                        if len(search_results) >= 3:
                            break
                else:
                    # For other library types, use standard search
                    search_results = section.search(title=item_title)
                
                if search_results:
                    found_item = search_results[0]
                    media_items.append(found_item)
                    break
            
            if not found_item:
                not_found.append(item_title)
        
        if not media_items:
            return f"No valid media items found matching: {', '.join(item_titles)}"
        
        # Add items to the playlist
        for item in media_items:
            target_playlist.addItems([item])
        
        # Prepare result message
        result = f"Successfully added {len(media_items)} items to playlist '{playlist_title}'."
        if not_found:
            result += f"\nThe following items were not found: {', '.join(not_found)}"
        
        return result
    except Exception as e:
        return f"Error adding to playlist: {str(e)}"

@mcp.tool()
async def add_track_by_key(playlist_title: str, rating_keys: List[str]) -> str:
    """Add tracks to a playlist by their rating keys.
    
    Args:
        playlist_title: Title of the playlist
        rating_keys: List of rating keys for the tracks to add
    """
    try:
        plex = connect_to_plex()
        
        # Find the playlist
        playlist = next((p for p in plex.playlists() 
                        if p.title.lower() == playlist_title.lower()), None)
        
        if not playlist:
            return f"Playlist '{playlist_title}' not found."
        
        # Find items by rating key
        items = []
        not_found = []
        
        for key in rating_keys:
            try:
                item = plex.fetchItem(key)
                items.append(item)
            except:
                not_found.append(key)
        
        if not items:
            return f"No valid media items found with the provided rating keys."
        
        # Add items to playlist
        for item in items:
            playlist.addItems([item])
        
        # Prepare result message
        result = f"Added {len(items)} items to playlist '{playlist_title}'."
        if not_found:
            result += f"\nThe following rating keys were not found: {', '.join(not_found)}"
        
        return result
    except Exception as e:
        return f"Error adding tracks: {str(e)}"

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
        not_found = []
        
        for item_title in item_titles:
            found = False
            for item in playlist_items:
                # Match by title
                if item_title.lower() == item.title.lower():
                    target_playlist.removeItems([item])
                    items_removed += 1
                    found = True
                    break
                # Also try to match Artist - Track format
                elif " - " in item_title:
                    parts = item_title.split(" - ")
                    if len(parts) == 2:
                        # Check if this is a track with the right artist
                        if (hasattr(item, 'grandparentTitle') and 
                            parts[0].lower() == item.grandparentTitle.lower() and
                            parts[1].lower() == item.title.lower()):
                            target_playlist.removeItems([item])
                            items_removed += 1
                            found = True
                            break
            
            if not found:
                not_found.append(item_title)
        
        if items_removed == 0:
            return f"No matching items found in playlist '{playlist_title}'."
        
        # Prepare result message
        result = f"Successfully removed {items_removed} items from playlist '{playlist_title}'."
        if not_found:
            result += f"\nThe following items were not found: {', '.join(not_found)}"
        
        return result
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
async def browse_tracks(library_name: str, artist_name: str = None, 
                       album_name: str = None, limit: int = 100) -> str:
    """Browse tracks in a music library.
    
    Args:
        library_name: Name of the music library
        artist_name: Optional artist name to filter by
        album_name: Optional album name to filter by
        limit: Maximum number of tracks to return
    """
    try:
        plex = connect_to_plex()
        library = plex.library.section(library_name)
        
        if library.type != 'artist':
            return f"Library '{library_name}' is not a music library."
        
        result = []
        
        if artist_name and album_name:
            # Find specific album tracks
            artists = library.search(title=artist_name, libtype='artist')
            if artists:
                albums = artists[0].albums()
                for album in albums:
                    if album_name.lower() in album.title.lower():
                        for track in album.tracks()[:limit]:
                            result.append({
                                'title': track.title,
                                'rating_key': track.ratingKey,
                                'album': album.title,
                                'artist': artists[0].title
                            })
        elif artist_name:
            # List all tracks for artist
            artists = library.search(title=artist_name, libtype='artist')
            if artists:
                for album in artists[0].albums():
                    for track in album.tracks():
                        result.append({
                            'title': track.title,
                            'rating_key': track.ratingKey,
                            'album': album.title,
                            'artist': artists[0].title
                        })
                        if len(result) >= limit:
                            break
                    if len(result) >= limit:
                        break
        else:
            # List random tracks from library
            count = 0
            for artist in library.all()[:10]:  # Limit to 10 artists for performance
                for album in artist.albums()[:3]:  # Limit to 3 albums per artist
                    for track in album.tracks()[:5]:  # Limit to 5 tracks per album
                        result.append({
                            'title': track.title,
                            'rating_key': track.ratingKey,
                            'album': album.title,
                            'artist': artist.title
                        })
                        count += 1
                        if count >= limit:
                            break
                    if count >= limit:
                        break
                if count >= limit:
                    break
        
        # Format response
        output = f"Found {len(result)} tracks in '{library_name}':\n\n"
        for i, track in enumerate(result, 1):
            output += f"{i}. {track['artist']} - {track['album']} - {track['title']} (ID: {track['rating_key']})\n"
        
        return output
    except Exception as e:
        return f"Error browsing tracks: {str(e)}"

@mcp.tool()
async def get_playlist_tracks(playlist_title: str) -> str:
    """Get detailed information about tracks in a playlist.
    
    Args:
        playlist_title: Title of the playlist to get tracks from
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
        try:
            playlist_items = target_playlist.items()
        except Exception as e:
            return f"Error retrieving items from playlist: {str(e)}"
        
        if not playlist_items:
            return f"Playlist '{playlist_title}' is empty."
        
        # Format the output
        result = f"Tracks in playlist '{playlist_title}':\n\n"
        
        for i, item in enumerate(playlist_items, 1):
            try:
                # Format based on item type
                if hasattr(item, 'TYPE') and item.TYPE == 'track':
                    # Music track
                    artist = getattr(item, 'grandparentTitle', 'Unknown Artist')
                    album = getattr(item, 'parentTitle', 'Unknown Album')
                    track = getattr(item, 'title', 'Unknown Track')
                    duration = getattr(item, 'duration', 0)
                    duration_str = f"{duration // 60000}:{(duration % 60000) // 1000:02d}"
                    rating_key = getattr(item, 'ratingKey', 'Unknown')
                    
                    result += f"{i}. {artist} - {album} - {track} ({duration_str}) [ID: {rating_key}]\n"
                elif hasattr(item, 'TYPE') and item.TYPE == 'episode':
                    # TV Show episode
                    show = getattr(item, 'grandparentTitle', 'Unknown Show')
                    season = getattr(item, 'parentTitle', 'Unknown Season')
                    episode = getattr(item, 'title', 'Unknown Episode')
                    episode_num = getattr(item, 'index', '?')
                    season_num = getattr(item, 'parentIndex', '?')
                    rating_key = getattr(item, 'ratingKey', 'Unknown')
                    
                    result += f"{i}. {show} - {season} (S{season_num}E{episode_num}) - {episode} [ID: {rating_key}]\n"
                elif hasattr(item, 'TYPE') and item.TYPE == 'movie':
                    # Movie
                    title = getattr(item, 'title', 'Unknown Movie')
                    year = getattr(item, 'year', '')
                    rating_key = getattr(item, 'ratingKey', 'Unknown')
                    
                    result += f"{i}. {title} ({year}) [ID: {rating_key}]\n"
                else:
                    # Generic item
                    title = getattr(item, 'title', 'Unknown Item')
                    rating_key = getattr(item, 'ratingKey', 'Unknown')
                    
                    result += f"{i}. {title} [ID: {rating_key}]\n"
            except Exception as item_error:
                # If there's an error with a specific item, add minimal info
                result += f"{i}. Error retrieving item details\n"
        
        return result
    except Exception as e:
        return f"Error listing playlist tracks: {str(e)}"