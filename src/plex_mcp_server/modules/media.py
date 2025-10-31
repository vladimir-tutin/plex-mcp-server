from . import mcp, connect_to_plex
from typing import List
from plexapi.exceptions import NotFound # type: ignore
import base64
import os
import json

@mcp.tool()
async def media_search(query: str, content_type: str = None) -> str:
    """Search for media across all libraries.
    
    Args:
        query: Search term to look for
        content_type: Optional content type to limit search to (movie, show, episode, track, album, artist or use comma-separated values for HTTP API like movies,music,tv)
    """
    try:
        import requests
        from urllib.parse import quote, urlencode

        # Get Plex URL and token from environment
        plex_url = os.environ.get("PLEX_URL", "").rstrip('/')
        plex_token = os.environ.get("PLEX_TOKEN", "")
        
        if not plex_url or not plex_token:
            return json.dumps({
                "status": "error",
                "message": "PLEX_URL or PLEX_TOKEN environment variables not set"
            })
        
        # Prepare the search query parameters
        params = {
            "query": query,
            "X-Plex-Token": plex_token,
            "limit": 100,  # Ensure we get a good number of results
            "includeCollections": 1,
            "includeExternalMedia": 1
        }
        
        # Add content type filter depending on the value provided
        if content_type:
            # Map content_type to searchTypes parameter if needed
            content_type_map = {
                "movie": "movies",
                "show": "tv",
                "episode": "tv",
                "track": "music",
                "album": "music",
                "artist": "music"
            }
            
            # If it contains a comma, it's already in searchTypes format
            if ',' in content_type:
                params["searchTypes"] = content_type
            elif content_type in content_type_map:
                # Use searchTypes for better results
                params["searchTypes"] = content_type_map[content_type]
                # Also add the specific type filter for more precise filtering
                params["type"] = content_type
            else:
                # Just use the provided type directly
                params["type"] = content_type
                
        # Add headers for JSON response
        headers = {
            'Accept': 'application/json'
        }
        
        # Construct the URL
        search_url = f"{plex_url}/library/search?{urlencode(params)}"
        
        # Make the request
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # For consistency, return in the same format as before but using the direct HTTP response
        if 'MediaContainer' not in data or 'SearchResult' not in data.get('MediaContainer', {}):
            return json.dumps({
                "status": "success",
                "message": f"No results found for '{query}'.",
                "count": 0,
                "results": []
            })
        
        # Format and organize search results
        results_by_type = {}
        total_count = 0
        
        for search_result in data['MediaContainer']['SearchResult']:
            if 'Metadata' not in search_result:
                continue
                
            item = search_result['Metadata']
            item_type = item.get('type', 'unknown')
            
            # Apply additional filter only when content_type is specified and not comma-separated
            # This is to ensure we only return the exact type the user asked for
            if content_type and ',' not in content_type and content_type not in content_type_map:
                if item_type != content_type:
                    continue
            
            # When specific content_type is requested but internal mapping is used,
            # ensure we only return that specific type
            if content_type and content_type in content_type_map and ',' not in content_type:
                if content_type != item_type:
                    continue
            
            if item_type not in results_by_type:
                results_by_type[item_type] = []
            
            # Extract relevant information based on item type
            formatted_item = {
                "title": item.get('title', 'Unknown'),
                "type": item_type,
                "rating_key": item.get('ratingKey')
            }
            
            if item_type == 'movie':
                formatted_item["year"] = item.get('year')
                formatted_item["rating"] = item.get('rating')
                formatted_item["summary"] = item.get('summary')
                
            elif item_type == 'show':
                formatted_item["year"] = item.get('year')
                formatted_item["summary"] = item.get('summary')
                
            elif item_type == 'season':
                formatted_item["show_title"] = item.get('parentTitle', 'Unknown Show')
                formatted_item["season_number"] = item.get('index')
                
            elif item_type == 'episode':
                formatted_item["show_title"] = item.get('grandparentTitle', 'Unknown Show')
                formatted_item["season_number"] = item.get('parentIndex')
                formatted_item["episode_number"] = item.get('index')
                
            elif item_type == 'track':
                formatted_item["artist"] = item.get('grandparentTitle', 'Unknown Artist')
                formatted_item["album"] = item.get('parentTitle', 'Unknown Album')
                formatted_item["track_number"] = item.get('index')
                formatted_item["duration"] = item.get('duration')
                formatted_item["library"] = item.get('librarySectionTitle')
                
            elif item_type == 'album':
                formatted_item["artist"] = item.get('parentTitle', 'Unknown Artist')
                formatted_item["year"] = item.get('parentYear')
                formatted_item["library"] = item.get('librarySectionTitle')
                
            elif item_type == 'artist':
                formatted_item["art"] = item.get('art')
                formatted_item["thumb"] = item.get('thumb')
                formatted_item["library"] = item.get('librarySectionTitle')
            
            # Add any media info if available
            if 'Media' in item:
                media_info = item['Media'][0] if isinstance(item['Media'], list) and item['Media'] else item['Media']
                if isinstance(media_info, dict):
                    if item_type in ['movie', 'show', 'episode']:
                        formatted_item["resolution"] = media_info.get('videoResolution')
                        formatted_item["container"] = media_info.get('container')
                        formatted_item["codec"] = media_info.get('videoCodec')
                    elif item_type in ['track']:
                        formatted_item["audio_codec"] = media_info.get('audioCodec')
                        formatted_item["bitrate"] = media_info.get('bitrate')
                        formatted_item["container"] = media_info.get('container')
            
            # Add thumbnail/artwork info
            if item_type == 'track':
                if 'thumb' in item:
                    formatted_item["thumb"] = item.get('thumb')
                if 'parentThumb' in item:
                    formatted_item["album_thumb"] = item.get('parentThumb')
                if 'grandparentThumb' in item:
                    formatted_item["artist_thumb"] = item.get('grandparentThumb')
                if 'art' in item:
                    formatted_item["art"] = item.get('art')
            
            results_by_type[item_type].append(formatted_item)
            total_count += 1
        
        # For cleaner display, organize by type
        type_order = ['track', 'album', 'artist', 'movie', 'show', 'season', 'episode']
        ordered_results = {}
        for type_name in type_order:
            if type_name in results_by_type:
                ordered_results[type_name] = results_by_type[type_name]
        
        # Add any remaining types
        for type_name in results_by_type:
            if type_name not in ordered_results:
                ordered_results[type_name] = results_by_type[type_name]
        
        return json.dumps({
            "status": "success",
            "message": f"Found {total_count} results for '{query}'",
            "query": query,
            "content_type": content_type,
            "total_count": total_count,
            "results_by_type": ordered_results
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error searching: {str(e)}"
        })

@mcp.tool()
async def media_get_details(media_title: str = None, media_id: int = None, library_name: str = None) -> str:
    """Get detailed information about a specific media item using PlexAPI's Media and Mixin functions.
    
    Args:
        media_title: Title of the media to get details for (optional if media_id is provided)
        media_id: Plex media ID/rating key to directly fetch the item (optional if media_title is provided)
        library_name: Optional library name to limit search to when using media_title
    """
    try:
        plex = connect_to_plex()
        
        # Validate that at least one identifier is provided
        if media_id is None and not media_title:
            return json.dumps({"error": "Either media_id or media_title must be provided."}, indent=4)
        
        # Search for the media
        if media_id is not None:
            # If media_id is provided, use it to directly fetch the item
            try:
                media = plex.fetchItem(media_id)
                # Get details for the single item
                details = get_media_details(media)
                return json.dumps(details, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Could not find media with ID {media_id}. Error: {str(e)}"}, indent=4)
        else:
            # Otherwise search by title
            results = []
            if library_name:
                try:
                    target_section = plex.library.section(library_name)
                    results = target_section.search(query=media_title)
                except Exception as e:
                    return json.dumps({"status": "error", "message": f"Error searching library '{library_name}': {str(e)}"}, indent=4)
            else:
                # Search in all libraries, including specific searches for music content
                results = plex.search(query=media_title)
                
                # If no results or we want to specifically check music libraries
                if not results or any(word in media_title.lower() for word in ['song', 'track', 'album', 'artist', 'music']):
                    # Get all music libraries
                    music_libraries = [section for section in plex.library.sections() if section.type == 'artist']
                    
                    # Search in each music library
                    for library in music_libraries:
                        # Try searching for tracks
                        track_results = library.search(query=media_title, libtype='track')
                        results.extend(track_results)
                        
                        # Try searching for albums
                        album_results = library.search(query=media_title, libtype='album')
                        results.extend(album_results)
                        
                        # Try searching for artists
                        artist_results = library.search(query=media_title, libtype='artist')
                        results.extend(artist_results)
            
            if not results:
                return json.dumps({"error": f"No media found matching '{media_title}'."}, indent=4)
            
            # Multiple results handling - return all matches
            if len(results) > 1:
                simplified_results = []
                for item in results:
                    try:
                        simplified_results.append({
                            'title': getattr(item, 'title', 'Unknown'),
                            'type': getattr(item, 'type', 'unknown'),
                            'id': getattr(item, 'ratingKey', None)
                        })
                    except Exception as item_error:
                        # Skip items that cause errors
                        continue
                
                # Only return results that have valid data
                simplified_results = [item for item in simplified_results if item['id'] is not None]
                
                if simplified_results:
                    return json.dumps(simplified_results, indent=4)
                else:
                    return json.dumps({"error": f"Found results for '{media_title}' but couldn't process them properly."}, indent=4)
            else:
                # Single result
                details = get_media_details(results[0])
                return json.dumps(details, indent=4)
    
    except Exception as e:
        return json.dumps({"error": f"Error getting media details: {str(e)}"}, indent=4)

# Helper function to extract media details
def get_media_details(media):
    """Extract details from a media object and return as a dictionary."""
    # Format duration as HH:MM:SS
    def format_duration(ms):
        if not ms:
            return None
        # Convert milliseconds to seconds
        seconds = ms // 1000
        # Calculate hours, minutes, seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        # Format as HH:MM:SS
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    details = {
        'title': getattr(media, 'title', 'Unknown'),
        'type': getattr(media, 'type', 'unknown'),
        'id': getattr(media, 'ratingKey', None),
        'added_at': getattr(media, 'addedAt', None).strftime("%Y-%m-%d %H:%M:%S") if hasattr(media, 'addedAt') and media.addedAt else None,
        'rating': getattr(media, 'rating', None),
        'content_rating': getattr(media, 'contentRating', None),
        'duration': format_duration(getattr(media, 'duration', None)) if hasattr(media, 'duration') and media.duration else None,
        'studio': getattr(media, 'studio', None),
        'year': getattr(media, 'year', None),
    }
    
    # Add type-specific fields
    if media.type == 'movie':
        details['summary'] = getattr(media, 'summary', None) if hasattr(media, 'summary') else None
        details['rating'] = getattr(media, 'userRating', None) if hasattr(media, 'userRating') else getattr(media, 'rating', None)
    elif media.type == 'show':
        try:
            details['summary'] = getattr(media, 'summary', None) if hasattr(media, 'summary') else None
            
            # Fix rating display - check for userRating first, then regular rating
            user_rating = getattr(media, 'userRating', None)
            if user_rating is not None:
                details['rating'] = user_rating
            # Make sure to keep the content rating
            details['content_rating'] = getattr(media, 'contentRating', None)
            
            details['seasons_count'] = len(media.seasons()) if hasattr(media, 'seasons') and callable(media.seasons) else 0
            details['episodes_count'] = len(media.episodes()) if hasattr(media, 'episodes') and callable(media.episodes) else 0
            
            # Add list of seasons with episodes
            if hasattr(media, 'seasons') and callable(media.seasons):
                seasons = media.seasons()
                seasons_list = []
                
                for season in seasons:
                    season_data = {
                        'title': getattr(season, 'title', f"Season {getattr(season, 'index', 'Unknown')}"),
                        'id': getattr(season, 'ratingKey', None),
                        'season_number': getattr(season, 'index', None),
                        'episodes_count': 0,
                        'episodes': []
                    }
                    
                    # Add episodes for this season
                    if hasattr(season, 'episodes') and callable(season.episodes):
                        try:
                            episodes = season.episodes()
                            season_data['episodes_count'] = len(episodes)
                            
                            for episode in episodes:
                                episode_data = {
                                    'title': getattr(episode, 'title', 'Unknown'),
                                    'id': getattr(episode, 'ratingKey', None),
                                    'episode_number': getattr(episode, 'index', None),
                                    'duration': format_duration(getattr(episode, 'duration', None)) if hasattr(episode, 'duration') and episode.duration else None
                                }
                                season_data['episodes'].append(episode_data)
                        except Exception as e:
                            season_data['error'] = str(e)
                    
                    seasons_list.append(season_data)
                
                details['seasons'] = seasons_list
        except Exception as e:
            details['summary'] = None
            details['seasons_count'] = 0
            details['episodes_count'] = 0
            details['error_details'] = str(e)
    elif media.type == 'episode':
        details['show_title'] = getattr(media, 'grandparentTitle', None)
        details['season_number'] = getattr(media, 'parentIndex', None)
        details['episode_number'] = getattr(media, 'index', None)
        details['summary'] = getattr(media, 'summary', None) if hasattr(media, 'summary') else None
        details['rating'] = getattr(media, 'userRating', None) if hasattr(media, 'userRating') else getattr(media, 'rating', None)
        
        # Remove studio field for episodes
        if 'studio' in details:
            del details['studio']
    elif media.type == 'artist':
        try:   
            details['summary'] = getattr(media, 'summary', None) if hasattr(media, 'summary') else None
            details['albums_count'] = len(media.albums()) if hasattr(media, 'albums') and callable(media.albums) else 0
            details['tracks_count'] = len(media.tracks()) if hasattr(media, 'tracks') and callable(media.tracks) else 0
            details['rating'] = getattr(media, 'userRating', None) if hasattr(media, 'userRating') else getattr(media, 'rating', None)
            
            # Remove fields not needed for artists
            if 'content_rating' in details:
                del details['content_rating']
            if 'duration' in details:
                del details['duration']
            if 'studio' in details:
                del details['studio']
            if 'year' in details:
                del details['year']
            
            # Add list of albums
            if hasattr(media, 'albums') and callable(media.albums):
                albums = media.albums()
                albums_list = []
                for album in albums:
                    albums_list.append({
                        'title': getattr(album, 'title', 'Unknown'),
                        'id': getattr(album, 'ratingKey', None),
                        'year': getattr(album, 'year', None),
                        'tracks_count': len(album.tracks()) if hasattr(album, 'tracks') and callable(album.tracks) else 0
                    })
                details['albums'] = albums_list
        except Exception as e:
            details['summary'] = None
            details['albums_count'] = 0
            details['tracks_count'] = 0
            details['error_details'] = str(e)
    elif media.type == 'album':
        details['summary'] = getattr(media, 'summary', None) if hasattr(media, 'summary') else None
        details['artist'] = getattr(media, 'parentTitle', 'Unknown Artist')
        details['artist_id'] = getattr(media, 'parentRatingKey', None)
        details['rating'] = getattr(media, 'userRating', None) if hasattr(media, 'userRating') else getattr(media, 'rating', None)
        
        # Remove content_rating field for albums
        if 'content_rating' in details:
            del details['content_rating']
        
        try:
            # Calculate total duration of all tracks
            total_duration_ms = 0
            if hasattr(media, 'tracks') and callable(media.tracks):
                tracks = media.tracks()
                details['tracks_count'] = len(tracks)
                
                # Add list of tracks and calculate total duration
                tracks_list = []
                for track in tracks:
                    track_duration = getattr(track, 'duration', 0) or 0
                    total_duration_ms += track_duration
                    
                    tracks_list.append({
                        'title': getattr(track, 'title', 'Unknown'),
                        'id': getattr(track, 'ratingKey', None),
                        'track_number': getattr(track, 'index', None),
                        'duration': format_duration(track_duration) if track_duration else None
                    })
                details['tracks'] = tracks_list
                
                # Format total duration
                if total_duration_ms > 0:
                    # Convert milliseconds to seconds
                    seconds = total_duration_ms // 1000
                    
                    # Calculate days, hours, minutes, seconds
                    days = seconds // 86400
                    seconds %= 86400
                    hours = seconds // 3600
                    seconds %= 3600
                    minutes = seconds // 60
                    seconds %= 60
                    
                    # Format as [DDD:]HH:MM:SS, omitting days if 0
                    if days > 0:
                        details['duration'] = f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        details['duration'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                details['tracks_count'] = 0
                
        except Exception as e:
            details['summary'] = None
            details['tracks_count'] = 0
            details['error_details'] = str(e)
    elif media.type == 'track':
        details['artist'] = getattr(media, 'grandparentTitle', 'Unknown Artist')
        details['artist_id'] = getattr(media, 'grandparentRatingKey', None)
        details['album'] = getattr(media, 'parentTitle', 'Unknown Album')
        details['album_id'] = getattr(media, 'parentRatingKey', None)
        details['track_number'] = getattr(media, 'index', None)
        details['disc_number'] = getattr(media, 'parentIndex', None)
        details['year'] = getattr(media, 'year', None)
        details['rating'] = getattr(media, 'userRating', None) if hasattr(media, 'userRating') else getattr(media, 'rating', None)
        details['view_count'] = getattr(media, 'viewCount', 0)
        details['skip_count'] = getattr(media, 'skipCount', 0)
        
        # Remove fields not needed for tracks
        if 'studio' in details:
            del details['studio']
        if 'content_rating' in details:
            del details['content_rating']
        if 'summary' in details:
            del details['summary']
        
        # If track doesn't have year, try to get it from the album
        if details['year'] is None and hasattr(media, 'album') and callable(getattr(media, 'album', None)):
            try:
                album = media.album()
                details['year'] = getattr(album, 'year', None)
            except:
                pass
    
    # Add collections
    if hasattr(media, 'genres') and media.genres:
        details['genres'] = [genre.tag for genre in media.genres]
    
    if hasattr(media, 'directors') and media.directors:
        details['directors'] = [director.tag for director in media.directors]
    
    if hasattr(media, 'writers') and media.writers:
        details['writers'] = [writer.tag for writer in media.writers]
    
    if hasattr(media, 'actors') and media.actors:
        details['actors'] = [actor.tag for actor in media.actors]
    
    return details

@mcp.tool()
async def media_edit_metadata(media_title: str, library_name: str = None, 
                        new_title: str = None, new_summary: str = None, new_rating: float = None,
                        new_release_date: str = None,  # Add this parameter
                        new_genre: str = None, remove_genre: str = None,
                        new_director: str = None, new_studio: str = None,
                        new_tags: List[str] = None) -> str:
    """Edit metadata for a specific media item.
    
    Args:
        media_title: Title of the media to edit
        library_name: Optional library name to limit search to
        new_title: New title for the item
        new_summary: New summary/description
        new_rating: New rating (0-10)
        new_release_date: New release date (YYYY-MM-DD)
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
        
        # Use the appropriate mixin methods based on metadata field
        if new_title:
            try:
                media.editTitle(new_title)
                changes_made.append(f"title changed to '{new_title}'")
            except Exception as e:
                return f"Error setting title: {str(e)}"
                
        if new_summary:
            try:
                media.editSummary(new_summary)
                changes_made.append("summary updated")
            except Exception as e:
                return f"Error setting summary: {str(e)}"

        if new_rating is not None:
            try:
                media.rate(new_rating)
                changes_made.append(f"rating changed to {new_rating}")
            except Exception as e:
                return f"Error setting rating: {str(e)}"
                
        if new_studio:
            try:
                if hasattr(media, 'editStudio'):
                    media.editStudio(new_studio)
                    changes_made.append(f"studio changed to '{new_studio}'")
                else:
                    return f"This media type doesn't support changing the studio"
            except Exception as e:
                return f"Error setting studio: {str(e)}"
        
        # Handle genres using the appropriate mixin methods
        if new_genre:
            try:
                if hasattr(media, 'addGenre'):
                    # Check if genre already exists
                    existing_genres = [g.tag.lower() for g in getattr(media, 'genres', [])]
                    if new_genre.lower() not in existing_genres:
                        media.addGenre(new_genre)
                        changes_made.append(f"added genre '{new_genre}'")
                else:
                    return f"This media type doesn't support adding genres"
            except Exception as e:
                return f"Error adding genre: {str(e)}"
                
        if remove_genre:
            try:
                if hasattr(media, 'removeGenre'):
                    # Find the genre object by tag name
                    matching_genres = [g for g in media.genres if g.tag.lower() == remove_genre.lower()]
                    if matching_genres:
                        media.removeGenre(matching_genres[0])
                        changes_made.append(f"removed genre '{remove_genre}'")
                else:
                    return f"This media type doesn't support removing genres"
            except Exception as e:
                return f"Error removing genre: {str(e)}"
        
        # Handle directors using the appropriate mixin methods
        if new_director and hasattr(media, 'addDirector'):
            try:
                # Check if director already exists
                existing_directors = [d.tag.lower() for d in getattr(media, 'directors', [])]
                if new_director.lower() not in existing_directors:
                    media.addDirector(new_director)
                    changes_made.append(f"added director '{new_director}'")
            except Exception as e:
                return f"Error adding director: {str(e)}"
        

                # Add handling for release date
        if new_release_date:
            try:
                # Parse the date string (YYYY-MM-DD) to a datetime object
                from datetime import datetime
                date_obj = datetime.strptime(new_release_date, '%Y-%m-%d')
                if hasattr(media, 'editOriginallyAvailable'):
                    media.editOriginallyAvailable(date_obj)
                    changes_made.append(f"updated release date to '{new_release_date}'")
                else:
                    return f"This media type doesn't support editing release dates"
            except Exception as e:
                return f"Error updating release date: {str(e)}"
            
        # Handle tags/labels
        if new_tags:
            for tag in new_tags:
                try:
                    if hasattr(media, 'addLabel'):
                        # Check if tag already exists
                        existing_labels = [l.tag.lower() for l in getattr(media, 'labels', [])]
                        if tag.lower() not in existing_labels:
                            media.addLabel(tag)
                            changes_made.append(f"added tag '{tag}'")
                    else:
                        return f"This media type doesn't support adding tags/labels"
                except Exception as e:
                    return f"Error adding tag '{tag}': {str(e)}"
        
        # Refresh to apply changes
        try:
            media.refresh()
        except Exception as e:
            # Changes might still be applied even if refresh fails
            pass
        

        
        if not changes_made:
            return f"No changes were made to '{media.title}'."
            
        return f"Successfully updated metadata for '{media.title}'. Changes: {', '.join(changes_made)}."
    except Exception as e:
        return f"Error editing metadata: {str(e)}"

@mcp.tool()
async def media_get_artwork(media_title: str = None, media_id: int = None, library_name: str = None,
                         image_types: List[str] = ["poster"], output_format: str = "base64",
                         output_dir: str = "./") -> str:
    """Get images for a specific media item.
    
    Args:
        media_title: Title of the media to get images for (optional if media_id is provided)
        media_id: ID of the media to get images for (optional if media_title is provided)
        library_name: Optional library name to limit search to when using media_title
        image_types: List of image types to get (poster, art/background, logo, banner, thumb)
        output_format: Format to return image data in (base64, url, or file_path)
        output_dir: Directory to save images to when using file output format
    """
    try:
        plex = connect_to_plex()
        
        # Validate that at least one identifier is provided
        if not media_id and not media_title:
            return json.dumps({"error": "Either media_id or media_title must be provided"}, indent=4)
        
        # Find the media
        media = None
        
        # If media_id is provided, use it to directly fetch the media
        if media_id:
            try:
                media = plex.fetchItem(media_id)
                if not media:
                    return json.dumps({"error": f"Media with ID '{media_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching media by ID: {str(e)}"}, indent=4)
        else:
            # Search for the media by title
            results = []
            if library_name:
                try:
                    library = plex.library.section(library_name)
                    results = library.search(query=media_title)
                except NotFound:
                    return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
            else:
                # Search in all libraries
                results = plex.search(query=media_title)
            
            if not results:
                return json.dumps({"error": f"No media found matching '{media_title}'"}, indent=4)
            
            # If multiple results, return the possible matches
            if len(results) > 1:
                matches = []
                for item in results:
                    matches.append({
                        "title": getattr(item, 'title', 'Unknown'),
                        "id": getattr(item, 'ratingKey', None),
                        "type": getattr(item, 'type', 'unknown'),
                        "year": getattr(item, 'year', None)
                    })
                return json.dumps(matches, indent=4)
            
            media = results[0]
        
        # Map image types to their URL attributes and collection methods
        image_map = {
            "poster": {"url_attr": "thumbUrl", "collection_method": "posters"},
            "thumbnail": {"url_attr": "thumbUrl", "collection_method": "posters"},
            "thumb": {"url_attr": "thumbUrl", "collection_method": "posters"},
            "background": {"url_attr": "artUrl", "collection_method": "arts"},
            "art": {"url_attr": "artUrl", "collection_method": "arts"},
            "logo": {"url_attr": "logoUrl", "collection_method": "logos"},
            "banner": {"url_attr": "bannerUrl", "collection_method": "None"}
        }
        
        # Extract requested images
        result = {}
        
        for img_type in image_types:
            img_type = img_type.lower()
            if img_type not in image_map:
                result[img_type] = {"error": f"Invalid image type: {img_type}"}
                continue
            
            url_attr = image_map[img_type]["url_attr"]
            collection_method = image_map[img_type]["collection_method"]
            
            # Check if this attribute exists on the media object
            if not hasattr(media, url_attr):
                result[img_type] = {"error": f"This media item doesn't have {img_type} artwork"}
                continue
            
            img_url = getattr(media, url_attr)
            if not img_url:
                result[img_type] = {"error": f"No {img_type} artwork found for this media"}
                continue
            
            # Get available artwork versions
            available_versions = []
            if collection_method != "None" and hasattr(media, collection_method) and callable(getattr(media, collection_method)):
                try:
                    available_versions = getattr(media, collection_method)()
                except:
                    pass
            
            # Handle different output formats
            if output_format == "url":
                result[img_type] = {
                    "filename": f"{media.title}_{img_type}.jpg",
                    "type": img_type,
                    "url": img_url,
                    "versions_available": len(available_versions)
                }
                continue
            
            # Get the image data
            import requests
            response = requests.get(img_url)
            
            if response.status_code != 200:
                result[img_type] = {"error": f"Failed to download {img_type} image: HTTP {response.status_code}"}
                continue
            
            image_data = response.content
            
            # Handle file output
            if output_format == "file_path":
                file_path = os.path.join(output_dir, f"{media.title}_{img_type}.jpg")
                
                # Save the file
                try:
                    with open(file_path, 'wb') as f:
                        f.write(image_data)
                    result[img_type] = {
                        "filename": file_path,
                        "type": img_type,
                        "path": os.path.abspath(file_path),
                        "versions_available": len(available_versions)
                    }
                except Exception as e:
                    result[img_type] = {"error": f"Failed to save image file: {str(e)}"}
            
            # Handle base64 output
            elif output_format == "base64":
                import base64
                b64_data = base64.b64encode(image_data).decode('utf-8')
                result[img_type] = {
                    "filename": f"{media.title}_{img_type}.jpg",
                    "type": img_type,
                    "base64": b64_data,
                    "versions_available": len(available_versions)
                }
            
            else:
                result[img_type] = {"error": f"Invalid output format: {output_format}"}
        
        # Return all results
        return json.dumps(result, indent=4)
        
    except Exception as e:
        return json.dumps({"error": f"Error getting images: {str(e)}"}, indent=4)

@mcp.tool()
async def media_delete(media_title: str = None, media_id: int = None, library_name: str = None) -> str:
    """Delete a media item from the Plex library.
    
    Args:
        media_title: Title of the media to delete (optional if media_id is provided)
        media_id: ID of the media to delete (optional if media_title is provided)
        library_name: Optional library name to limit search to when using media_title
    """
    try:
        plex = connect_to_plex()
        
        # Validate that at least one identifier is provided
        if not media_id and not media_title:
            return json.dumps({"error": "Either media_id or media_title must be provided"}, indent=4)
        
        # Find the media
        media = None
        
        # If media_id is provided, use it to directly fetch the media
        if media_id:
            try:
                # Try fetching by ratingKey
                try:
                    media = plex.fetchItem(media_id)
                except:
                    # If that fails, try searching in all libraries
                    media = None
                
                if not media:
                    return json.dumps({"error": f"Media with ID '{media_id}' not found"}, indent=4)
                
                # Get the file path for information
                file_paths = []
                try:
                    if hasattr(media, 'media') and media.media:
                        for media_item in media.media:
                            if hasattr(media_item, 'parts') and media_item.parts:
                                for part in media_item.parts:
                                    if hasattr(part, 'file') and part.file:
                                        file_paths.append(part.file)
                except Exception:
                    pass
                
                # Store the title to return after deletion
                media_title_to_return = media.title
                media_type = getattr(media, 'type', 'unknown')
                
                # Perform the deletion
                try:
                    media.delete()
                    return json.dumps({
                        "deleted": True,
                        "title": media_title_to_return,
                        "type": media_type,
                        "files_on_disk": file_paths
                    }, indent=4)
                except Exception as delete_error:
                    return json.dumps({"error": f"Error during deletion: {str(delete_error)}"}, indent=4)
                
            except Exception as e:
                return json.dumps({"error": f"Error fetching media by ID: {str(e)}"}, indent=4)
        else:
            # Search for the media by title
            results = []
            if library_name:
                try:
                    library = plex.library.section(library_name)
                    results = library.search(query=media_title)
                except NotFound:
                    return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
            else:
                # Search in all libraries
                results = plex.search(query=media_title)
            
            if not results:
                return json.dumps({"error": f"No media found matching '{media_title}'"}, indent=4)
            
            # Filter results to only include valid media types
            valid_media_results = []
            for item in results:
                if hasattr(item, 'type') and getattr(item, 'type', None) in ['movie', 'show', 'episode', 'season', 'artist', 'album', 'track']:
                    valid_media_results.append(item)
            
            # If no valid media results, return an error
            if not valid_media_results:
                return json.dumps({"error": f"Found results for '{media_title}' but none were valid media items"}, indent=4)
                
            # When searching by title, always return multiple matches if multiple are found
            # This allows the user to select the specific media item they want to delete
            if len(valid_media_results) > 1:
                matches = []
                for item in valid_media_results:
                    try:
                        match_data = {
                            "title": getattr(item, 'title', 'Unknown'),
                            "id": getattr(item, 'ratingKey', None),
                            "type": getattr(item, 'type', 'unknown')
                        }
                        
                        # Add year if available (helps differentiate movies with same title)
                        if hasattr(item, 'year'):
                            match_data["year"] = item.year
                            
                        # Add library info if available
                        if hasattr(item, 'librarySectionTitle'):
                            match_data["library"] = item.librarySectionTitle
                            
                        # Add additional disambiguation info based on type
                        if item.type == 'episode':
                            if hasattr(item, 'grandparentTitle'):
                                match_data["show"] = item.grandparentTitle
                            if hasattr(item, 'parentIndex'):
                                match_data["season"] = item.parentIndex
                            if hasattr(item, 'index'):
                                match_data["episode"] = item.index
                        elif item.type == 'season':
                            if hasattr(item, 'parentTitle'):
                                match_data["show"] = item.parentTitle
                            if hasattr(item, 'index'):
                                match_data["season_number"] = item.index
                        elif item.type == 'album':
                            if hasattr(item, 'parentTitle'):
                                match_data["artist"] = item.parentTitle
                        elif item.type == 'track':
                            if hasattr(item, 'grandparentTitle'):
                                match_data["artist"] = item.grandparentTitle
                            if hasattr(item, 'parentTitle'):
                                match_data["album"] = item.parentTitle
                        
                        matches.append(match_data)
                    except Exception as e:
                        # Skip items that cause errors
                        continue
                
                if matches:
                    return json.dumps(matches, indent=4)
                else:
                    return json.dumps({"error": f"Found results for '{media_title}' but none had valid attributes"}, indent=4)
            else:
                # Use the single valid result
                media = valid_media_results[0]
                
                # Get the file path for information
                file_paths = []
                try:
                    if hasattr(media, 'media') and media.media:
                        for media_item in media.media:
                            if hasattr(media_item, 'parts') and media_item.parts:
                                for part in media_item.parts:
                                    if hasattr(part, 'file') and part.file:
                                        file_paths.append(part.file)
                except Exception:
                    pass
                
                # Store the title to return after deletion
                media_title_to_return = media.title
                media_type = getattr(media, 'type', 'unknown')
                
                # Perform the deletion
                try:
                    media.delete()
                    return json.dumps({
                        "deleted": True,
                        "title": media_title_to_return,
                        "type": media_type,
                        "files_on_disk": file_paths
                    }, indent=4)
                except Exception as delete_error:
                    return json.dumps({"error": f"Error during deletion: {str(delete_error)}"}, indent=4)
                
    except Exception as e:
        return json.dumps({"error": f"Error deleting media: {str(e)}"}, indent=4)

@mcp.tool()
async def media_set_artwork(media_title: str, library_name: str = None,
                          art_type: str = "poster", 
                          filepath: str = None, url: str = None,
                          lock: bool = False) -> str:
    """Set artwork for a specific media item.
    
    Args:
        media_title: Title of the media to set artwork for
        library_name: Optional library name to limit search to
        art_type: Type of artwork to set (poster, background/art, logo)
        filepath: Path to the local image file
        url: URL to the image file
        lock: Whether to lock the artwork to prevent Plex from changing it
    """
    try:
        if not filepath and not url:
            return "Error: Either filepath or url must be provided."
            
        if filepath and url:
            return "Error: Please provide either filepath OR url, not both."
        
        # Normalize art type
        art_type = art_type.lower()
        valid_types = ["poster", "background", "art", "logo"]
        
        if art_type not in valid_types:
            return f"Invalid art type: {art_type}. Supported types: {', '.join(valid_types)}"
        
        # Map art types to their upload methods
        upload_map = {
            "poster": "uploadPoster",
            "background": "uploadArt",
            "art": "uploadArt",
            "logo": "uploadLogo"
        }
        
        # Map art types to their lock methods
        lock_map = {
            "poster": "lockPoster",
            "background": "lockArt",
            "art": "lockArt",
            "logo": "lockLogo"
        }
        
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
        
        # Check if the object supports this art type
        upload_method = upload_map.get(art_type)
        if not hasattr(media, upload_method):
            return f"This media item doesn't support setting {art_type} artwork."
        
        # Upload the artwork
        upload_fn = getattr(media, upload_method)
        
        if filepath:
            if not os.path.isfile(filepath):
                return f"Artwork file not found: {filepath}"
            upload_fn(filepath=filepath)
        else:  # url
            upload_fn(url=url)
        
        # Lock the artwork if requested
        if lock:
            lock_method = lock_map.get(art_type)
            if hasattr(media, lock_method):
                lock_fn = getattr(media, lock_method)
                lock_fn()
                return f"Successfully set and locked {art_type} artwork for '{media.title}'."
        
        return f"Successfully set {art_type} artwork for '{media.title}'."
    except Exception as e:
        return f"Error setting {art_type} artwork: {str(e)}"

@mcp.tool()
async def media_list_available_artwork(media_title: str = None, media_id: int = None, library_name: str = None, art_type: str = "poster") -> str:
    """List all available artwork for a specific media item.
    
    Args:
        media_title: Title of the media to list artwork for (optional if media_id is provided)
        media_id: ID of the media to list artwork for (optional if media_title is provided)
        library_name: Optional library name to limit search to when using media_title
        art_type: Type of artwork to list (poster, background/art, logo)
    """
    try:
        # Validate that at least one identifier is provided
        if not media_id and not media_title:
            return json.dumps({"error": "Either media_id or media_title must be provided"}, indent=4)
            
        # Normalize art type
        art_type = art_type.lower()
        
        # Map art types to their methods that return available artwork
        art_methods = {
            "poster": "posters",
            "background": "arts", 
            "art": "arts",
            "logo": "logos"
        }
        
        if art_type not in art_methods:
            return json.dumps({"error": f"Invalid art type: {art_type}. Supported types: {', '.join(art_methods.keys())}"}, indent=4)
        
        plex = connect_to_plex()
        
        # Find the media
        media = None
        
        # If media_id is provided, use it to directly fetch the media
        if media_id:
            try:
                media = plex.fetchItem(media_id)
                if not media:
                    return json.dumps({"error": f"Media with ID '{media_id}' not found"}, indent=4)
                
                # Verify object type is a media item that can have artwork
                if not hasattr(media, 'type') or getattr(media, 'type', None) not in ['movie', 'show', 'episode', 'season', 'artist', 'album', 'track']:
                    return json.dumps({"error": f"The item with ID {media_id} is not a media item that can have artwork"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching media by ID: {str(e)}"}, indent=4)
        else:
            # Search for the media by title
            if library_name:
                try:
                    library = plex.library.section(library_name)
                    results = library.search(query=media_title)
                except NotFound:
                    return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
            else:
                results = plex.search(query=media_title)
            
            if not results:
                return json.dumps({"error": f"No media found matching '{media_title}'"}, indent=4)
            
            # Filter results to only include valid media types
            valid_media_results = []
            for item in results:
                if hasattr(item, 'type') and getattr(item, 'type', None) in ['movie', 'show', 'episode', 'season', 'artist', 'album', 'track']:
                    valid_media_results.append(item)
            
            # If no valid media results, return an error
            if not valid_media_results:
                return json.dumps({"error": f"Found results for '{media_title}' but none were valid media items that can have artwork"}, indent=4)
            
            # When searching by title, always return multiple matches if multiple are found
            # This allows the user to select the specific media item they want
            if len(valid_media_results) > 1:
                matches = []
                for item in valid_media_results:
                    try:
                        match_data = {
                            "title": getattr(item, 'title', 'Unknown'),
                            "id": getattr(item, 'ratingKey', None),
                            "type": getattr(item, 'type', 'unknown')
                        }
                        
                        # Add year if available (helps differentiate movies with same title)
                        if hasattr(item, 'year'):
                            match_data["year"] = item.year
                            
                        # Add additional disambiguation info based on type
                        if item.type == 'episode':
                            if hasattr(item, 'grandparentTitle'):
                                match_data["show"] = item.grandparentTitle
                            if hasattr(item, 'parentIndex'):
                                match_data["season"] = item.parentIndex
                            if hasattr(item, 'index'):
                                match_data["episode"] = item.index
                        elif item.type == 'season':
                            if hasattr(item, 'parentTitle'):
                                match_data["show"] = item.parentTitle
                            if hasattr(item, 'index'):
                                match_data["season_number"] = item.index
                        
                        matches.append(match_data)
                    except Exception as e:
                        # Skip items that cause errors
                        continue
                
                if matches:
                    return json.dumps(matches, indent=4)
                else:
                    return json.dumps({"error": f"Found results for '{media_title}' but none had valid attributes"}, indent=4)
            else:
                # Use the single valid result
                media = valid_media_results[0]
        
        # Check if the object supports this art type
        art_method = art_methods.get(art_type)
        if not hasattr(media, art_method):
            return json.dumps({"error": f"This media item doesn't support {art_type} artwork"}, indent=4)
        
        # Get available artwork safely
        try:
            get_art_fn = getattr(media, art_method)
            artwork_list = get_art_fn()
            
            if not artwork_list:
                return json.dumps({"error": f"No {art_type} artwork found for media"}, indent=4)
            
            # Build response as JSON
            artwork_info = []
            
            for i, art in enumerate(artwork_list, 1):
                art_data = {
                    "index": i,
                    "provider": getattr(art, 'provider', 'Unknown'),
                    "url": getattr(art, 'key', None),
                    "selected": getattr(art, 'selected', False),
                    "rating_key": getattr(art, 'ratingKey', None) if hasattr(art, 'ratingKey') else None
                }
                artwork_info.append(art_data)
                
            return json.dumps({
                "media_title": getattr(media, 'title', 'Unknown'),
                "media_id": getattr(media, 'ratingKey', None),
                "art_type": art_type,
                "count": len(artwork_info),
                "artwork": artwork_info
            }, indent=4)
        except Exception as art_error:
            return json.dumps({"error": f"Error retrieving {art_type} artwork: {str(art_error)}"}, indent=4)
    except Exception as e:
        return json.dumps({"error": f"Error listing {art_type} artwork: {str(e)}"}, indent=4)