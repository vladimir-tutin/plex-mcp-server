from modules import mcp, connect_to_plex
from typing import List
from plexapi.playlist import Playlist # type: ignore

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