from modules import mcp, connect_to_plex
from modules.profiles import server_for_user
from typing import List, Optional
import asyncio
from plexapi import utils
from plexapi.playlist import Playlist # type: ignore
from plexapi.exceptions import NotFound, BadRequest  # type: ignore
import os
import requests
import base64
import json

def _playlist_by_id(plex, playlist_id):
    # Resolve only among the selected user's playlists, never arbitrary media IDs.
    return next((item for item in plex.playlists()
                 if str(item.ratingKey) == str(playlist_id)), None)


# Functions for playlists and collections
@mcp.tool()
async def playlist_list(library_name: str = None, content_type: str = None, username: str = None) -> str:
    """List all playlists on the Plex server.
    
    Args:
        username: Optional Plex username or profile title. Omit for the configured account. Failed access returns an error.
        library_name: Optional library name to filter playlists from
        content_type: Optional content type to filter playlists (audio, video, photo)
    """
    try:
        plex = server_for_user(connect_to_plex(), username=username)
        playlists = []
        
        # Filter by content type if specified
        if content_type:
            valid_types = ["audio", "video", "photo"]
            if content_type.lower() not in valid_types:
                return json.dumps({"error": f"Invalid content type. Valid types are: {', '.join(valid_types)}"}, indent=4)
            playlists = plex.playlists(playlistType=content_type.lower())
        else:
            playlists = plex.playlists()
        
        # Filter by library if specified
        if library_name:
            try:
                library = plex.library.section(library_name)
                # Use the section's playlists method directly
                if content_type:
                    playlists = library.playlists(playlistType=content_type.lower())
                else:
                    playlists = library.playlists()
            except NotFound:
                return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
        
        # Format playlist data (lightweight version - no items)
        playlist_data = []
        for playlist in playlists:
            try:
                playlist_data.append({
                    "title": playlist.title,
                    "key": playlist.key,
                    "ratingKey": playlist.ratingKey,
                    "type": playlist.playlistType,
                    "summary": playlist.summary if hasattr(playlist, 'summary') else "",
                    "duration": playlist.duration if hasattr(playlist, 'duration') else None,
                    "item_count": playlist.leafCount if hasattr(playlist, 'leafCount') else None
                })
            except Exception as item_error:
                # If there's an error with a specific playlist, include error info
                playlist_data.append({
                    "title": getattr(playlist, 'title', 'Unknown'),
                    "key": getattr(playlist, 'key', 'Unknown'),
                    "error": str(item_error)
                })
        
        return json.dumps(playlist_data, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def playlist_create(playlist_title: str, item_titles: List[str], library_name: str = None, summary: str = None, username: str = None) -> str:
    """Create a new playlist with specified items.
    
    Args:
        username: Optional Plex username or profile title. Omit for the configured account. Failed access returns an error.
        playlist_title: Title for the new playlist
        item_titles: List of media titles to include in the playlist
        library_name: Optional library name to limit search to
        summary: Optional summary description for the playlist
    """
    try:
        plex = server_for_user(connect_to_plex(), username=username)
        items = []
        
        # Search for items in all libraries or specific library
        for title in item_titles:
            found = False
            search_scope = plex.library.section(library_name) if library_name else plex.library
            
            # Search for the item
            search_results = search_scope.search(title=title)
            
            if search_results:
                items.append(search_results[0])
                found = True
            
            if not found:
                return json.dumps({"status": "error", "message": f"Item '{title}' not found"}, indent=4)
        
        if not items:
            return json.dumps({"status": "error", "message": "No items found for the playlist"}, indent=4)
        
        # Create the playlist
        playlist = plex.createPlaylist(title=playlist_title, items=items, summary=summary)
        
        return json.dumps({
            "status": "success", 
            "message": f"Playlist '{playlist_title}' created successfully",
            "data": {
                "title": playlist.title,
                "key": playlist.key,
                "ratingKey": playlist.ratingKey,
                "item_count": len(items)
            }
        }, indent=4)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=4)

@mcp.tool()
async def playlist_edit(playlist_title: str = None, playlist_id: int = None, new_title: str = None, new_summary: str = None, username: str = None) -> str:
    """Edit a playlist's details such as title and summary.
    
    Args:
        username: Optional Plex username or profile title. Omit for the configured account. Failed access returns an error.
        playlist_title: Title of the playlist to edit (optional if playlist_id is provided)
        playlist_id: ID of the playlist to edit (optional if playlist_title is provided)
        new_title: Optional new title for the playlist
        new_summary: Optional new summary for the playlist
    """
    try:
        plex = server_for_user(connect_to_plex(), username=username)
        
        # Validate that at least one identifier is provided
        if not playlist_id and not playlist_title:
            return json.dumps({"error": "Either playlist_id or playlist_title must be provided"}, indent=4)
        
        # Find the playlist
        playlist = None
        original_title = None
        
        # If playlist_id is provided, use it to directly fetch the playlist
        if playlist_id:
            try:
                # Try fetching by ratingKey first
                try:
                    playlist = _playlist_by_id(plex, playlist_id)
                except:
                    # If that fails, try finding by key in all playlists
                    all_playlists = plex.playlists()
                    playlist = next((p for p in all_playlists if str(p.ratingKey) == str(playlist_id)), None)
                
                if not playlist:
                    return json.dumps({"error": f"Playlist with ID '{playlist_id}' not found"}, indent=4)
                original_title = playlist.title
            except Exception as e:
                return json.dumps({"error": f"Error fetching playlist by ID: {str(e)}"}, indent=4)
        else:
            # Search by title
            playlists = plex.playlists()
            matching_playlists = [p for p in playlists if p.title.lower() == playlist_title.lower()]
            
            if not matching_playlists:
                return json.dumps({"error": f"No playlist found with title '{playlist_title}'"}, indent=4)
            
            # If multiple matching playlists, return list of matches with IDs
            if len(matching_playlists) > 1:
                matches = []
                for p in matching_playlists:
                    matches.append({
                        "title": p.title,
                        "id": p.ratingKey,
                        "type": p.playlistType,
                        "item_count": p.leafCount if hasattr(p, 'leafCount') else len(p.items())
                    })
                
                # Return as a direct array like playlist_list
                return json.dumps(matches, indent=4)
                
            playlist = matching_playlists[0]
            original_title = playlist.title
        
        # Track changes
        changes = []
        
        # Update title if provided
        if new_title and new_title != playlist.title:
            playlist.edit(title=new_title)
            changes.append(f"title from '{original_title}' to '{new_title}'")
        
        # Update summary if provided
        if new_summary is not None:  # Allow empty summaries
            current_summary = playlist.summary if hasattr(playlist, 'summary') else ""
            if new_summary != current_summary:
                playlist.edit(summary=new_summary)
                changes.append("summary")
        
        if not changes:
            return json.dumps({
                "updated": False,
                "title": playlist.title,
                "message": "No changes made to the playlist"
            }, indent=4)
            
        return json.dumps({
            "updated": True,
            "title": new_title or playlist.title,
            "changes": changes
        }, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def playlist_upload_poster(playlist_title: str = None, playlist_id: int = None, poster_url: str = None, poster_filepath: str = None, username: str = None) -> str:
    """Upload a poster image for a playlist.
    
    Args:
        username: Optional Plex username or profile title. Omit for the configured account. Failed access returns an error.
        playlist_title: Title of the playlist to set poster for (optional if playlist_id is provided)
        playlist_id: ID of the playlist to set poster for (optional if playlist_title is provided)
        poster_url: URL to an image to use as poster
        poster_filepath: Local file path to an image to use as poster
    """
    try:
        plex = server_for_user(connect_to_plex(), username=username)
        
        # Validate that at least one identifier is provided
        if not playlist_id and not playlist_title:
            return json.dumps({"error": "Either playlist_id or playlist_title must be provided"}, indent=4)
        
        # Check that at least one poster source is provided
        if not poster_url and not poster_filepath:
            return json.dumps({"error": "Either poster_url or poster_filepath must be provided"}, indent=4)
        
        # Find the playlist
        playlist = None
        
        # If playlist_id is provided, use it to directly fetch the playlist
        if playlist_id:
            try:
                # Try fetching by ratingKey first
                try:
                    playlist = _playlist_by_id(plex, playlist_id)
                except:
                    # If that fails, try finding by key in all playlists
                    all_playlists = plex.playlists()
                    playlist = next((p for p in all_playlists if str(p.ratingKey) == str(playlist_id)), None)
                
                if not playlist:
                    return json.dumps({"error": f"Playlist with ID '{playlist_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching playlist by ID: {str(e)}"}, indent=4)
        else:
            # Search by title
            playlists = plex.playlists()
            matching_playlists = [p for p in playlists if p.title.lower() == playlist_title.lower()]
            
            if not matching_playlists:
                return json.dumps({"error": f"No playlist found with title '{playlist_title}'"}, indent=4)
            
            # If multiple matching playlists, return list of matches with IDs
            if len(matching_playlists) > 1:
                matches = []
                for p in matching_playlists:
                    matches.append({
                        "title": p.title,
                        "id": p.ratingKey,
                        "type": p.playlistType,
                        "item_count": p.leafCount if hasattr(p, 'leafCount') else len(p.items())
                    })
                
                # Return as a direct array like playlist_list
                return json.dumps(matches, indent=4)
                
            playlist = matching_playlists[0]
        
        # Upload from URL
        if poster_url:
            try:
                response = requests.get(poster_url)
                if response.status_code != 200:
                    return json.dumps({"error": f"Failed to download image from URL: {response.status_code}"}, indent=4)
                
                # Upload the poster
                playlist.uploadPoster(url=poster_url)
                return json.dumps({
                    "updated": True,
                    "poster_source": "url",
                    "title": playlist.title
                }, indent=4)
            except Exception as url_error:
                return json.dumps({"error": f"Error uploading from URL: {str(url_error)}"}, indent=4)
        
        # Upload from file
        if poster_filepath:
            if not os.path.exists(poster_filepath):
                return json.dumps({"error": f"File not found: {poster_filepath}"}, indent=4)
            
            try:
                # Upload the poster
                playlist.uploadPoster(filepath=poster_filepath)
                return json.dumps({
                    "updated": True,
                    "poster_source": "file",
                    "title": playlist.title
                }, indent=4)
            except Exception as file_error:
                return json.dumps({"error": f"Error uploading from file: {str(file_error)}"}, indent=4)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def playlist_copy_to_user(playlist_title: str = None, playlist_id: int = None, username: str = None, source_username: str = None) -> str:
    """Copy a playlist to another user account.
    
    Args:
        playlist_title: Title of the playlist to copy (optional if playlist_id is provided)
        playlist_id: ID of the playlist to copy (optional if playlist_title is provided)
        username: Destination username or profile title.
        source_username: Optional source username or profile title; defaults to the configured account.
    """
    try:
        admin = connect_to_plex()
        plex = server_for_user(admin, username=source_username)
        
        # Validate that at least one identifier is provided
        if not playlist_id and not playlist_title:
            return json.dumps({"status": "error", "message": "Either playlist_id or playlist_title must be provided"}, indent=4)
        
        if not username:
            return json.dumps({"status": "error", "message": "Username must be provided"}, indent=4)
        
        # Find the playlist
        playlist = None
        
        # If playlist_id is provided, use it to directly fetch the playlist
        if playlist_id:
            try:
                # Try fetching by ratingKey first
                try:
                    playlist = _playlist_by_id(plex, playlist_id)
                except:
                    # If that fails, try finding by key in all playlists
                    all_playlists = plex.playlists()
                    playlist = next((p for p in all_playlists if str(p.ratingKey) == str(playlist_id)), None)
                
                if not playlist:
                    return json.dumps({"status": "error", "message": f"Playlist with ID '{playlist_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"status": "error", "message": f"Error fetching playlist by ID: {str(e)}"}, indent=4)
        else:
            # Search by title
            playlists = plex.playlists()
            matching_playlists = [p for p in playlists if p.title.lower() == playlist_title.lower()]
            
            if not matching_playlists:
                return json.dumps({"status": "error", "message": f"No playlist found with title '{playlist_title}'"}, indent=4)
            
            # If multiple matching playlists, return list of matches with IDs
            if len(matching_playlists) > 1:
                matches = []
                for p in matching_playlists:
                    matches.append({
                        "title": p.title,
                        "id": p.ratingKey,
                        "type": p.playlistType,
                        "item_count": p.leafCount if hasattr(p, 'leafCount') else len(p.items())
                    })
                
                return json.dumps({
                    "status": "multiple_matches",
                    "message": f"Found {len(matching_playlists)} playlists with title '{playlist_title}'. Please specify the playlist ID.",
                    "matches": matches
                }, indent=4)
                
            playlist = matching_playlists[0]
        
        destination = server_for_user(admin, username=username)
        items = [destination.fetchItem(item.ratingKey) for item in playlist.items()]
        destination.createPlaylist(title=playlist.title, items=items)

        return json.dumps({
            "status": "success", 
            "message": f"Playlist '{playlist.title}' copied to user '{username}'"
        }, indent=4)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=4)

@mcp.tool()
async def playlist_add_to(playlist_title: str = None, playlist_id: int = None, item_titles: List[str] = None, item_ids: List[int] = None, username: str = None) -> str:
    """Add items to a playlist.
    
    Args:
        username: Optional Plex username or profile title. Omit for the configured account. Failed access returns an error.
        playlist_title: Title of the playlist to add to (optional if playlist_id is provided)
        playlist_id: ID of the playlist to add to (optional if playlist_title is provided)
        item_titles: List of media titles to add to the playlist (optional if item_ids is provided)
        item_ids: List of media IDs to add to the playlist (optional if item_titles is provided)
    """
    try:
        plex = server_for_user(connect_to_plex(), username=username)
        
        # Validate that at least one identifier is provided
        if not playlist_id and not playlist_title:
            return json.dumps({"error": "Either playlist_id or playlist_title must be provided"}, indent=4)
        
        # Validate that at least one item source is provided
        if (not item_titles or len(item_titles) == 0) and (not item_ids or len(item_ids) == 0):
            return json.dumps({"error": "Either item_titles or item_ids must be provided"}, indent=4)
        
        # Find the playlist
        playlist = None
        
        # If playlist_id is provided, use it to directly fetch the playlist
        if playlist_id:
            try:
                # Try fetching by ratingKey first
                try:
                    playlist = _playlist_by_id(plex, playlist_id)
                except:
                    # If that fails, try finding by key in all playlists
                    all_playlists = plex.playlists()
                    playlist = next((p for p in all_playlists if str(p.ratingKey) == str(playlist_id)), None)
                
                if not playlist:
                    return json.dumps({"error": f"Playlist with ID '{playlist_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching playlist by ID: {str(e)}"}, indent=4)
        else:
            # Search by title
            playlists = plex.playlists()
            matching_playlists = [p for p in playlists if p.title.lower() == playlist_title.lower()]
            
            if not matching_playlists:
                return json.dumps({"error": f"No playlist found with title '{playlist_title}'"}, indent=4)
            
            # If multiple matching playlists, return list of matches with IDs
            if len(matching_playlists) > 1:
                matches = []
                for p in matching_playlists:
                    matches.append({
                        "title": p.title,
                        "id": p.ratingKey,
                        "type": p.playlistType,
                        "item_count": p.leafCount if hasattr(p, 'leafCount') else len(p.items())
                    })
                
                # Return as a direct array like playlist_list
                return json.dumps({"Multiple Matches":matches}, indent=4)
                
            playlist = matching_playlists[0]
        
        # Find items to add
        items_to_add = []
        not_found = []
        
        # If we have item IDs, try to add by ID first
        if item_ids and len(item_ids) > 0:
            for item_id in item_ids:
                try:
                    # Try to fetch the item by ID
                    item = plex.fetchItem(item_id)
                    if item:
                        items_to_add.append(item)
                    else:
                        not_found.append(str(item_id))
                except Exception as e:
                    not_found.append(str(item_id))
        
        # If we have item titles, search for them
        if item_titles and len(item_titles) > 0:
            # Search all library sections
            all_sections = plex.library.sections()
            
            for title in item_titles:
                found_item = None
                possible_matches = []
                
                # Try to find the item in each section
                for section in all_sections:
                    # Skip photo libraries
                    if section.type in ['photo']:
                        continue
                    
                    search_results = section.search(title)
                    if search_results:
                        # Check for exact title match (case insensitive)
                        exact_matches = [item for item in search_results if item.title.lower() == title.lower()]
                        if exact_matches:
                            found_item = exact_matches[0]
                            break
                        else:
                            # Add to possible matches if not an exact match
                            for item in search_results:
                                possible_matches.append({
                                    "title": item.title,
                                    "id": item.ratingKey,
                                    "type": item.type,
                                    "year": item.year if hasattr(item, 'year') and item.year else None
                                })
                
                if found_item:
                    items_to_add.append(found_item)
                elif possible_matches:
                    # If we have possible matches but no exact match, add title to not_found
                    # and store the possible matches to return later
                    not_found.append({
                        "title": title,
                        "possible_matches": possible_matches
                    })
                else:
                    not_found.append(title)
        
        if not items_to_add:
            # If we have possible matches, return them
            if any(isinstance(item, dict) for item in not_found):
                possible_matches_response = []
                for item in not_found:
                    if isinstance(item, dict) and "possible_matches" in item:
                        for match in item["possible_matches"]:
                            if match not in possible_matches_response:
                                possible_matches_response.append(match)
                    
                return json.dumps({"Multiple Possible Matches Use ID" : possible_matches_response}, indent=4)
            
            return json.dumps({"error": "No matching items found to add to the playlist"}, indent=4)
        
        # Add items to the playlist
        for item in items_to_add:
            playlist.addItems(item)
        
        return json.dumps({
            "added": True,
            "title": playlist.title,
            "items_added": [item.title for item in items_to_add],
            "items_not_found": not_found,
            "total_items": len(playlist.items())
        }, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def playlist_remove_from(playlist_title: str = None, playlist_id: int = None, item_titles: List[str] = None, username: str = None) -> str:
    """Remove items from a playlist.
    
    Args:
        username: Optional Plex username or profile title. Omit for the configured account. Failed access returns an error.
        playlist_title: Title of the playlist to remove from (optional if playlist_id is provided)
        playlist_id: ID of the playlist to remove from (optional if playlist_title is provided)
        item_titles: List of media titles to remove from the playlist
    """
    try:
        plex = server_for_user(connect_to_plex(), username=username)
        
        # Validate that at least one identifier is provided
        if not playlist_id and not playlist_title:
            return json.dumps({"error": "Either playlist_id or playlist_title must be provided"}, indent=4)
        
        if not item_titles or len(item_titles) == 0:
            return json.dumps({"error": "At least one item title must be provided to remove"}, indent=4)
        
        # Find the playlist
        playlist = None
        
        # If playlist_id is provided, use it to directly fetch the playlist
        if playlist_id:
            try:
                # Try fetching by ratingKey first
                try:
                    playlist = _playlist_by_id(plex, playlist_id)
                except:
                    # If that fails, try finding by key in all playlists
                    all_playlists = plex.playlists()
                    playlist = next((p for p in all_playlists if str(p.ratingKey) == str(playlist_id)), None)
                
                if not playlist:
                    return json.dumps({"error": f"Playlist with ID '{playlist_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching playlist by ID: {str(e)}"}, indent=4)
        else:
            # Search by title
            playlists = plex.playlists()
            matching_playlists = [p for p in playlists if p.title.lower() == playlist_title.lower()]
            
            if not matching_playlists:
                return json.dumps({"error": f"No playlist found with title '{playlist_title}'"}, indent=4)
            
            # If multiple matching playlists, return list of matches with IDs
            if len(matching_playlists) > 1:
                matches = []
                for p in matching_playlists:
                    matches.append({
                        "title": p.title,
                        "id": p.ratingKey,
                        "type": p.playlistType,
                        "item_count": p.leafCount if hasattr(p, 'leafCount') else len(p.items())
                    })
                
                # Return as a direct array like playlist_list
                return json.dumps({"Multiple Matches":matches}, indent=4)
                
            playlist = matching_playlists[0]
        
        # Get current items in the playlist
        playlist_items = playlist.items()
        
        # Find items to remove
        items_to_remove = []
        not_found = []
        
        for title in item_titles:
            found = False
            for item in playlist_items:
                if item.title.lower() == title.lower():
                    items_to_remove.append(item)
                    found = True
                    break
            if not found:
                not_found.append(title)
        
        if not items_to_remove:
            # No items found to remove, return the current playlist contents
            current_items = []
            for item in playlist_items:
                current_items.append({
                    "title": item.title,
                    "type": item.type,
                    "id": item.ratingKey
                })
            
            return json.dumps({
                "error": "No matching items found in the playlist to remove",
                "playlist_title": playlist.title,
                "playlist_id": playlist.ratingKey,
                "current_items": current_items
            }, indent=4)
        
        # Remove items from the playlist
        # Using removeItems (plural) since removeItem is deprecated
        playlist.removeItems(items_to_remove)
        
        return json.dumps({
            "removed": True,
            "title": playlist.title,
            "items_removed": [item.title for item in items_to_remove],
            "items_not_found": not_found,
            "remaining_items": len(playlist.items())
        }, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def playlist_delete(playlist_title: str = None, playlist_id: int = None, username: str = None) -> str:
    """Delete a playlist.
    
    Args:
        username: Optional Plex username or profile title. Omit for the configured account. Failed access returns an error.
        playlist_title: Title of the playlist to delete (optional if playlist_id is provided)
        playlist_id: ID of the playlist to delete (optional if playlist_title is provided)
    """
    try:
        plex = server_for_user(connect_to_plex(), username=username)
        
        # Validate that at least one identifier is provided
        if not playlist_id and not playlist_title:
            return json.dumps({"error": "Either playlist_id or playlist_title must be provided"}, indent=4)
        
        # Find the playlist
        playlist = None
        
        # If playlist_id is provided, use it to directly fetch the playlist
        if playlist_id:
            try:
                # Try fetching by ratingKey first
                try:
                    playlist = _playlist_by_id(plex, playlist_id)
                except:
                    # If that fails, try finding by key in all playlists
                    all_playlists = plex.playlists()
                    playlist = next((p for p in all_playlists if str(p.ratingKey) == str(playlist_id)), None)
                
                if not playlist:
                    return json.dumps({"error": f"Playlist with ID '{playlist_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching playlist by ID: {str(e)}"}, indent=4)
        else:
            # Search by title
            playlists = plex.playlists()
            matching_playlists = [p for p in playlists if p.title.lower() == playlist_title.lower()]
            
            if not matching_playlists:
                return json.dumps({"error": f"No playlist found with title '{playlist_title}'"}, indent=4)
            
            # If multiple matching playlists, return list of matches with IDs
            if len(matching_playlists) > 1:
                matches = []
                for p in matching_playlists:
                    matches.append({
                        "title": p.title,
                        "id": p.ratingKey,
                        "type": p.playlistType,
                        "item_count": p.leafCount if hasattr(p, 'leafCount') else len(p.items())
                    })
                
                # Return as a direct array like playlist_list
                return json.dumps(matches, indent=4)
                
            playlist = matching_playlists[0]
        
        # Get the playlist title to return in the message
        playlist_title_to_return = playlist.title
        
        # Delete the playlist
        playlist.delete()
        
        # Return a simple object with the result
        return json.dumps({
            "deleted": True,
            "title": playlist_title_to_return
        }, indent=4)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def playlist_get_contents(playlist_title: str = None, playlist_id: int = None, username: str = None) -> str:
    """Get the contents of a playlist.
    
    Args:
        username: Optional Plex username or profile title. Omit for the configured account. Failed access returns an error.
        playlist_title: Title of the playlist to get contents of (optional if playlist_id is provided)
        playlist_id: ID of the playlist to get contents of (optional if playlist_title is provided)
        
    Returns:
        JSON object containing the playlist contents
    """
    try:
        plex = server_for_user(connect_to_plex(), username=username)
        
        # Validate that at least one identifier is provided
        if not playlist_id and not playlist_title:
            return json.dumps({"error": "Either playlist_id or playlist_title must be provided"}, indent=4)
        
        # If playlist_id is provided, use it to directly fetch the playlist
        if playlist_id:
            try:
                playlist = None
                # Try fetching by ratingKey first
                try:
                    playlist = _playlist_by_id(plex, playlist_id)

                except:
                    # If that fails, try finding by key in all playlists
                    all_playlists = plex.playlists()
                    playlist = next((p for p in all_playlists if str(p.ratingKey) == str(playlist_id)), None)
                
                if not playlist:
                    return json.dumps({"error": f"Playlist with ID '{playlist_id}' not found"}, indent=4)
                
                # Get playlist contents

                return get_playlist_contents(playlist)
            except Exception as e:
                if "500" in str(e):
                    return json.dumps({"error": "Empty playlist"}, indent=4)
                else:
                    return json.dumps({"error": f"Error fetching playlist by ID: {str(e)}"}, indent=4)
        
        # If we get here, we're searching by title
        all_playlists = plex.playlists()
        matching_playlists = [p for p in all_playlists if p.title.lower() == playlist_title.lower()]
        
        # If no matching playlists
        if not matching_playlists:
            return json.dumps({"error": f"No playlist found with title '{playlist_title}'"}, indent=4)
        
        # If multiple matching playlists, return list of matches with IDs
        if len(matching_playlists) > 1:
            matches = []
            for p in matching_playlists:
                matches.append({
                    "title": p.title,
                    "id": p.ratingKey,
                    "type": p.playlistType,
                    "item_count": p.leafCount if hasattr(p, 'leafCount') else len(p.items())
                })
            
            # Return as a direct array like playlist_list
            return json.dumps(matches, indent=4)
        
        # Single match - get contents
        return get_playlist_contents(matching_playlists[0])
    
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Error getting playlist contents: {str(e)}"}, indent=4)

def get_playlist_contents(playlist):
    """Helper function to get formatted playlist contents."""

    try:
        items = playlist.items()
        playlist_items = []
        
        for item in items:
            item_data = {
                "title": item.title,
                "type": item.type,
                "ratingKey": item.ratingKey,
                "addedAt": item.addedAt.strftime("%Y-%m-%d %H:%M:%S") if hasattr(item, 'addedAt') else None,
                "duration": item.duration if hasattr(item, 'duration') else None,
                "thumb": item.thumb if hasattr(item, 'thumb') else None
            }
            
            # Add media-type specific fields
            if item.type == 'movie':
                item_data["year"] = item.year if hasattr(item, 'year') else None
            elif item.type == 'episode':
                item_data["show"] = item.grandparentTitle if hasattr(item, 'grandparentTitle') else None
                item_data["season"] = item.parentTitle if hasattr(item, 'parentTitle') else None
                item_data["seasonNumber"] = item.parentIndex if hasattr(item, 'parentIndex') else None
                item_data["episodeNumber"] = item.index if hasattr(item, 'index') else None
            elif item.type == 'track':
                item_data["artist"] = item.grandparentTitle if hasattr(item, 'grandparentTitle') else None
                item_data["album"] = item.parentTitle if hasattr(item, 'parentTitle') else None
                item_data["albumArtist"] = item.originalTitle if hasattr(item, 'originalTitle') else None
            
            playlist_items.append(item_data)
        
        playlist_info = {
            "title": playlist.title,
            "id": playlist.ratingKey,
            "key": playlist.key,
            "type": playlist.playlistType,
            "summary": playlist.summary if hasattr(playlist, 'summary') else None,
            "duration": playlist.duration if hasattr(playlist, 'duration') else None,
            "itemCount": len(playlist_items),
            "items": playlist_items
        }
        
        if getattr(playlist, "smart", False):
            playlist_info["smart"] = True
            playlist_info["definition"] = playlist.filters()

        # Return just the playlist info without status wrappers
        return json.dumps(playlist_info, indent=4)
    except Exception as e:
        return json.dumps({"error": f"Error formatting playlist contents: {str(e)}"}, indent=4)


def _smart_playlist(plex, playlist_title, playlist_id):
    if playlist_id is not None:
        result = _playlist_by_id(plex, playlist_id)
        if result is None:
            raise ValueError("Playlist not found for the selected user")
        return result
    if not playlist_title:
        raise ValueError("Provide playlist_id or playlist_title")
    matches = [p for p in plex.playlists() if p.title.casefold() == playlist_title.casefold()]
    if len(matches) != 1:
        raise ValueError("Playlist title must match exactly one playlist; use playlist_list and supply playlist_id")
    return matches[0]


def _smart_result(playlist):
    playlist.reload()
    items = playlist.fetchItems(playlist.key + "/items", maxresults=20, container_size=20)
    return {
        "status": "success", "title": playlist.title, "playlist_id": playlist.ratingKey,
        "smart": True, "definition": playlist.filters(), "item_count": playlist.leafCount,
        "items": [{"title": i.title, "media_id": i.ratingKey, "type": i.type,
                   "show": getattr(i, "grandparentTitle", None)} for i in items],
        "preview_limit": 20,
    }


def _smart_error(exc):
    message = str(exc) if isinstance(exc, (ValueError, BadRequest)) else "Plex smart playlist request failed"
    return json.dumps({"status": "error", "message": message})


@mcp.tool()
async def playlist_get_smart_filter_options(library_name: str, field: Optional[str] = None,
                                          libtype: Optional[str] = None, username: Optional[str] = None) -> str:
    """Discover fields, operators, sort options or field choices for smart playlists.

    Args:
        library_name: Library to search.
        field: Optional field whose available values should be listed, such as genre.
        libtype: Search type; defaults to movie, episode or track for the library.
            Use show to match show titles, or episode to match episode titles.
        username: Optional Plex username or profile title; omit for the configured account.
    """
    def run():
        plex = server_for_user(connect_to_plex(), username=username)
        section = plex.library.section(library_name)
        selected_type = libtype or section.METADATA_TYPE
        section.getFilterType(selected_type)
        if field:
            choices = section.listFilterChoices(field, libtype=selected_type)
            return {"library": section.title, "libtype": selected_type, "field": field,
                    "choices": [{"title": c.title, "value": c.key} for c in choices]}
        fields = [{"field": f.key, "title": f.title, "type": f.type,
                   "operators": [o.key for o in section.listOperators(f.type)]}
                  for f in section.listFields(libtype=selected_type)]
        return {"library": section.title, "libtype": selected_type, "fields": fields,
                "sorts": [{"field": f.key, "title": f.title, "defaultDirection": f.defaultDirection}
                          for f in section.listSorts(libtype=selected_type)]}
    try:
        return json.dumps(await asyncio.to_thread(run))
    except Exception as exc:
        return _smart_error(exc)


@mcp.tool()
async def playlist_create_smart(playlist_title: str, library_name: str, filters: Optional[dict] = None,
                                sort: Optional[str] = None, limit: Optional[int] = None,
                                libtype: Optional[str] = None, summary: Optional[str] = None,
                                username: Optional[str] = None) -> str:
    """Create a saved library search that Plex keeps populated automatically.

    Args:
        playlist_title: New playlist title.
        library_name: Library to search.
        filters: Plex filters, e.g. {"year>>": 2000}, or {"title": "Band of Brothers"} with libtype show.
        sort: Sort fields, e.g. year:desc. Discover valid fields with playlist_get_smart_filter_options.
        limit: Positive maximum result count; omit for no limit.
        libtype: Search type, defaulting to movie, episode or track. Show/artist searches produce playable episodes/tracks.
        summary: Optional description.
        username: Optional Plex username or profile title; omit for the configured account.

    Returns the saved definition and up to 20 current items. Use playlist_get_contents for all items.
    """
    def run():
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        if not playlist_title.strip():
            raise ValueError("playlist_title must not be empty")
        plex = server_for_user(connect_to_plex(), username=username)
        section = plex.library.section(library_name)
        playlist = plex.createPlaylist(title=playlist_title, section=section, smart=True,
                                       filters=filters, sort=sort, limit=limit,
                                       libtype=libtype or section.METADATA_TYPE)
        if summary is not None:
            try:
                playlist.editSummary(summary)
            except Exception:
                return {"status": "error", "message": "Playlist was created, but its summary could not be saved",
                        "playlist_id": playlist.ratingKey, "created": True}
        return _smart_result(playlist)
    try:
        return json.dumps(await asyncio.to_thread(run))
    except Exception as exc:
        return _smart_error(exc)


@mcp.tool()
async def playlist_edit_smart_filters(playlist_title: Optional[str] = None, playlist_id: Optional[int] = None,
                                      filters: Optional[dict] = None, sort: Optional[str] = None,
                                      limit: Optional[int] = None, libtype: Optional[str] = None,
                                      username: Optional[str] = None) -> str:
    """Edit a smart playlist while preserving settings you omit, including its search type.

    Args:
        playlist_title: Existing title, optional when playlist_id is supplied.
        playlist_id: ID from playlist_list or playlist_create_smart.
        filters: Replace filters; omit to preserve, or use {} to clear them.
        sort: Replace sort order; omit to preserve, or use an empty string to clear it.
        limit: Replace result limit; omit to preserve, or use 0 to remove it.
        libtype: Change search type explicitly; omit to preserve show/episode/artist/track matching.
        username: Optional Plex username or profile title; omit for the configured account.

    Returns the saved definition and up to 20 current items. playlist_get_contents also returns the definition.
    """
    def run():
        if limit is not None and limit < 0:
            raise ValueError("limit must be nonnegative")
        plex = server_for_user(connect_to_plex(), username=username)
        playlist = _smart_playlist(plex, playlist_title, playlist_id)
        if not playlist.smart:
            raise ValueError("This playlist is not smart")
        definition = playlist.filters()
        section = playlist.section()
        selected_type = libtype or definition.get("libtype")
        if not selected_type:
            raise ValueError("Cannot determine the saved search type; supply libtype explicitly")
        # PlexAPI.updateFilters always uses section.METADATA_TYPE, losing show/artist semantics.
        search_key = section._buildSearchKey(
            libtype=selected_type,
            filters=definition.get("filters") if filters is None else filters,
            sort=definition.get("sort") if sort is None else (sort or None),
            limit=definition.get("limit") if limit is None else (limit or None),
        )
        uri = plex._uriRoot() + search_key
        plex.query(playlist.key + "/items" + utils.joinArgs({"uri": uri}), method=plex._session.put)
        return _smart_result(playlist)
    try:
        return json.dumps(await asyncio.to_thread(run))
    except Exception as exc:
        return _smart_error(exc)
