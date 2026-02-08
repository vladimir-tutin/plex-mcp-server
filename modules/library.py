import json
import requests
import aiohttp
import asyncio
from plexapi.exceptions import NotFound # type: ignore
from modules import mcp, connect_to_plex
from urllib.parse import urljoin
import time
from typing import Optional, Union, List, Dict

def get_plex_headers(plex):
    """Get standard Plex headers for HTTP requests"""
    return {
        'X-Plex-Token': plex._token,
        'Accept': 'application/json'
    }

async def async_get_json(session, url, headers):
    """Helper function to make async HTTP requests"""
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            status = response.status
            try:
                error_body = await response.text()
                error_msg = error_body[:200]
            except:
                error_msg = "Could not read error body"
            raise Exception(f"Plex API error {status}: {error_msg}")
        return await response.json()

@mcp.tool()
async def library_list() -> str:
    """List all available libraries on the Plex server."""
    try:
        plex = connect_to_plex()
        libraries = plex.library.sections()
        
        if not libraries:
            return json.dumps({"message": "No libraries found on your Plex server."})
        
        libraries_dict = {}
        for lib in libraries:
            libraries_dict[lib.title] = {
                "type": lib.type,
                "libraryId": lib.key,
                "totalSize": lib.totalSize,
                "uuid": lib.uuid,
                "locations": lib.locations,
                "updatedAt": lib.updatedAt.isoformat()
            }
        
        return json.dumps(libraries_dict)
    except Exception as e:
        return json.dumps({"error": f"Error listing libraries: {str(e)}"})

@mcp.tool()
async def library_get_stats(library_name: str) -> str:
    """Get statistics for a specific library.
    
    Args:
        library_name: Name of the library to get stats for
    """
    try:
        plex = connect_to_plex()
        base_url = plex._baseurl
        headers = get_plex_headers(plex)
        
        async with aiohttp.ClientSession() as session:
            # First get library sections
            sections_url = urljoin(base_url, 'library/sections')
            sections_data = await async_get_json(session, sections_url, headers)
            
            target_section = None
            for section in sections_data['MediaContainer']['Directory']:
                if section['title'].lower() == library_name.lower():
                    target_section = section
                    break
                    
            if not target_section:
                return json.dumps({"error": f"Library '{library_name}' not found"})
                
            section_id = target_section['key']
            library_type = target_section['type']
            
            # Create base result
            result = {
                "name": target_section['title'],
                "type": library_type,
                "totalItems": target_section.get('totalSize', 0)
            }
            
            # Prepare URLs for concurrent requests
            all_items_url = urljoin(base_url, f'library/sections/{section_id}/all')
            unwatched_url = urljoin(base_url, f'library/sections/{section_id}/all?unwatched=1')
            
            # Make concurrent requests for all and unwatched items
            all_data, unwatched_data = await asyncio.gather(
                async_get_json(session, all_items_url, headers),
                async_get_json(session, unwatched_url, headers)
            )
            all_data = all_data['MediaContainer']
            unwatched_data = unwatched_data['MediaContainer']
            
            if library_type == 'movie':
                movie_stats = {
                    "count": all_data.get('size', 0),
                    "unwatched": unwatched_data.get('size', 0)
                }
                
                # Get genres, directors, studios stats
                genres = {}
                directors = {}
                studios = {}
                decades = {}
                
                for movie in all_data.get('Metadata', []):
                    # Process genres
                    for genre in movie.get('Genre', []):
                        genre_name = genre['tag']
                        genres[genre_name] = genres.get(genre_name, 0) + 1
                    
                    # Process directors
                    for director in movie.get('Director', []):
                        director_name = director['tag']
                        directors[director_name] = directors.get(director_name, 0) + 1
                    
                    # Process studios
                    studio = movie.get('studio')
                    if studio:
                        studios[studio] = studios.get(studio, 0) + 1
                    
                    # Process decades
                    year = movie.get('year')
                    if year:
                        decade = (year // 10) * 10
                        decades[decade] = decades.get(decade, 0) + 1
                
                # Add top items to results
                if genres:
                    movie_stats["topGenres"] = dict(sorted(genres.items(), key=lambda x: x[1], reverse=True)[:5])
                if directors:
                    movie_stats["topDirectors"] = dict(sorted(directors.items(), key=lambda x: x[1], reverse=True)[:5])
                if studios:
                    movie_stats["topStudios"] = dict(sorted(studios.items(), key=lambda x: x[1], reverse=True)[:5])
                if decades:
                    movie_stats["byDecade"] = dict(sorted(decades.items()))
                
                result["movieStats"] = movie_stats
                
            elif library_type == 'show':
                # Prepare URLs for concurrent requests
                seasons_url = urljoin(base_url, f'library/sections/{section_id}/all?type=3')
                episodes_url = urljoin(base_url, f'library/sections/{section_id}/all?type=4')
                
                # Make concurrent requests for seasons and episodes
                seasons_data, episodes_data = await asyncio.gather(
                    async_get_json(session, seasons_url, headers),
                    async_get_json(session, episodes_url, headers)
                )
                seasons_data = seasons_data['MediaContainer']
                episodes_data = episodes_data['MediaContainer']
                
                # Process show stats
                genres = {}
                studios = {}
                decades = {}
                
                for show in all_data.get('Metadata', []):
                    # Process genres
                    for genre in show.get('Genre', []):
                        genre_name = genre['tag']
                        genres[genre_name] = genres.get(genre_name, 0) + 1
                    
                    # Process studios
                    studio = show.get('studio')
                    if studio:
                        studios[studio] = studios.get(studio, 0) + 1
                    
                    # Process decades
                    year = show.get('year')
                    if year:
                        decade = (year // 10) * 10
                        decades[decade] = decades.get(decade, 0) + 1
                
                show_stats = {
                    "shows": all_data.get('size', 0),
                    "seasons": seasons_data.get('size', 0),
                    "episodes": episodes_data.get('size', 0),
                    "unwatchedShows": unwatched_data.get('size', 0)
                }
                
                # Add top items to results
                if genres:
                    show_stats["topGenres"] = dict(sorted(genres.items(), key=lambda x: x[1], reverse=True)[:5])
                if studios:
                    show_stats["topStudios"] = dict(sorted(studios.items(), key=lambda x: x[1], reverse=True)[:5])
                if decades:
                    show_stats["byDecade"] = dict(sorted(decades.items()))
                
                result["showStats"] = show_stats
                
            elif library_type == 'artist':
                # Initialize statistics
                artist_stats = {
                    "count": all_data.get('size', 0),
                    "totalTracks": 0,
                    "totalAlbums": 0,
                    "totalPlays": 0
                }
                
                # Track data for statistics
                all_genres = {}
                all_years = {}
                top_artists = {}
                top_albums = {}
                audio_formats = {}
                
                # Process artists one by one for accurate stats
                for artist in all_data.get('Metadata', []):
                    artist_id = artist.get('ratingKey')
                    artist_name = artist.get('title', '')
                    
                    if not artist_id:
                        continue
                    
                    # Store artist views for top artists calculation
                    artist_view_count = 0
                    artist_albums = set()
                    artist_track_count = 0
                    
                    # Get tracks directly for this artist
                    artist_tracks_url = urljoin(base_url, f'library/sections/{section_id}/all?artist.id={artist_id}&type=10')
                    artist_tracks_data = await async_get_json(session, artist_tracks_url, headers)
                    
                    if 'MediaContainer' in artist_tracks_data and 'Metadata' in artist_tracks_data['MediaContainer']:
                        for track in artist_tracks_data['MediaContainer']['Metadata']:
                            # Count total tracks
                            artist_track_count += 1
                            
                            # Count track views for this artist
                            track_views = track.get('viewCount', 0)
                            artist_view_count += track_views
                            artist_stats["totalPlays"] += track_views
                            
                            # Add album to set
                            album_title = track.get('parentTitle')
                            if album_title:
                                artist_albums.add(album_title)
                                
                                # Track album plays for top albums
                                album_key = f"{artist_name} - {album_title}"
                                if album_key not in top_albums:
                                    top_albums[album_key] = 0
                                top_albums[album_key] += track_views
                            
                            # Process genres if available
                            if 'Genre' in track:
                                for genre in track.get('Genre', []):
                                    genre_name = genre['tag']
                                    all_genres[genre_name] = all_genres.get(genre_name, 0) + 1
                            
                            # Process years instead of decades
                            year = track.get('parentYear') or track.get('year')
                            if year:
                                all_years[year] = all_years.get(year, 0) + 1
                            
                            # Track audio formats
                            if 'Media' in track and track['Media'] and 'audioCodec' in track['Media'][0]:
                                audio_codec = track['Media'][0]['audioCodec']
                                audio_formats[audio_codec] = audio_formats.get(audio_codec, 0) + 1
                    
                    # Update top artists
                    if artist_track_count > 0:
                        top_artists[artist_name] = artist_view_count
                    
                    # Update totals
                    artist_stats["totalTracks"] += artist_track_count
                    artist_stats["totalAlbums"] += len(artist_albums)
                
                # Add top items to results
                if all_genres:
                    artist_stats["topGenres"] = dict(sorted(all_genres.items(), key=lambda x: x[1], reverse=True)[:10])
                if top_artists:
                    artist_stats["topArtists"] = dict(sorted(top_artists.items(), key=lambda x: x[1], reverse=True)[:10])
                if top_albums:
                    artist_stats["topAlbums"] = dict(sorted(top_albums.items(), key=lambda x: x[1], reverse=True)[:10])
                if all_years:
                    artist_stats["byYear"] = dict(sorted(all_years.items()))
                if audio_formats:
                    artist_stats["audioFormats"] = audio_formats
                
                result["musicStats"] = artist_stats
            
            return json.dumps(result)
            
    except Exception as e:
        return json.dumps({"error": f"Error getting library stats: {str(e)}"})

@mcp.tool()
async def library_refresh(library_name: Optional[str] = None) -> str:
    """Refresh a specific library or all libraries.
    
    Args:
        library_name: Optional name of the library to refresh (refreshes all if None)
    """
    try:
        plex = connect_to_plex()
        
        if library_name:
            # Refresh a specific library
            section = None
            all_sections = plex.library.sections()
            
            # Find the section with matching name (case-insensitive)
            for s in all_sections:
                if s.title.lower() == library_name.lower():
                    section = s
                    break
            
            if not section:
                return json.dumps({"error": f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"})
            
            # Refresh the library
            section.refresh()
            return json.dumps({"success": True, "message": f"Refreshing library '{section.title}'. This may take some time."})
        else:
            # Refresh all libraries
            plex.library.refresh()
            return json.dumps({"success": True, "message": "Refreshing all libraries. This may take some time."})
    except Exception as e:
        return json.dumps({"error": f"Error refreshing library: {str(e)}"})

@mcp.tool()
async def library_scan(library_name: str, path: Optional[str] = None) -> str:
    """Scan a specific library or part of a library.
    
    Args:
        library_name: Name of the library to scan
        path: Optional specific path to scan within the library
    """
    try:
        plex = connect_to_plex()
        
        # Find the specified library
        section = None
        all_sections = plex.library.sections()
        
        # Find the section with matching name (case-insensitive)
        for s in all_sections:
            if s.title.lower() == library_name.lower():
                section = s
                break
        
        if not section:
            return json.dumps({"error": f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"})
        
        # Scan the library
        if path:
            try:
                section.update(path=path)
                return json.dumps({"success": True, "message": f"Scanning path '{path}' in library '{section.title}'. This may take some time."})
            except NotFound:
                return json.dumps({"error": f"Path '{path}' not found in library '{section.title}'."})
        else:
            section.update()
            return json.dumps({"success": True, "message": f"Scanning library '{section.title}'. This may take some time."})
    except Exception as e:
        return json.dumps({"error": f"Error scanning library: {str(e)}"})

@mcp.tool()
async def library_get_details(library_name: str) -> str:
    """Get detailed information about a specific library, including folder paths and settings.
    
    Args:
        library_name: Name of the library to get details for
    """
    try:
        plex = connect_to_plex()
        
        # Get all library sections
        all_sections = plex.library.sections()
        target_section = None
        
        # Find the section with the matching name (case-insensitive)
        for section in all_sections:
            if section.title.lower() == library_name.lower():
                target_section = section
                break
        
        if not target_section:
            return json.dumps({"error": f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"})
        
        # Create the result dictionary
        result = {
            "name": target_section.title,
            "type": target_section.type,
            "uuid": target_section.uuid,
            "totalItems": target_section.totalSize,
            "locations": target_section.locations,
            "agent": target_section.agent,
            "scanner": target_section.scanner,
            "language": target_section.language
        }
        
        # Get additional attributes using _data
        data = target_section._data
        
        # Add scanner settings if available
        if 'scannerSettings' in data:
            scanner_settings = {}
            for setting in data['scannerSettings']:
                if 'value' in setting:
                    scanner_settings[setting.get('key', 'unknown')] = setting['value']
            if scanner_settings:
                result["scannerSettings"] = scanner_settings
        
        # Add agent settings if available
        if 'agentSettings' in data:
            agent_settings = {}
            for setting in data['agentSettings']:
                if 'value' in setting:
                    agent_settings[setting.get('key', 'unknown')] = setting['value']
            if agent_settings:
                result["agentSettings"] = agent_settings
        
        # Add advanced settings if available
        if 'advancedSettings' in data:
            advanced_settings = {}
            for setting in data['advancedSettings']:
                if 'value' in setting:
                    advanced_settings[setting.get('key', 'unknown')] = setting['value']
            if advanced_settings:
                result["advancedSettings"] = advanced_settings
                
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error getting library details: {str(e)}"})

@mcp.tool()
async def library_get_recently_added(count: int = 50, library_name: Optional[str] = None) -> str:
    """Get recently added media across all libraries or in a specific library.
    
    Args:
        count: Number of items to return (default: 50)
        library_name: Optional library name to limit results to
    """
    try:
        plex = connect_to_plex()
        
        # Check if we need to filter by library
        if library_name:
            # Find the specified library
            section = None
            all_sections = plex.library.sections()
            
            # Find the section with matching name (case-insensitive)
            for s in all_sections:
                if s.title.lower() == library_name.lower():
                    section = s
                    break
            
            if not section:
                return json.dumps({"error": f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"})
            
            # Get recently added from this library
            recent = section.recentlyAdded(maxresults=count)
        else:
            # Get recently added across all libraries
            recent = plex.library.recentlyAdded()
            # Sort by date added (newest first) and limit to count
            if recent:
                try:
                    recent = sorted(recent, key=lambda x: getattr(x, 'addedAt', None), reverse=True)[:count]
                except Exception as sort_error:
                    # If sorting fails, just take the first 'count' items
                    recent = recent[:count]
        
        if not recent:
            return json.dumps({"message": "No recently added items found."})
        
        # Prepare the result
        result = {
            "count": len(recent),
            "requestedCount": count,
            "library": library_name if library_name else "All Libraries",
            "items": {}
        }
        
        # Group results by type
        for item in recent:
            item_type = getattr(item, 'type', 'unknown')
            if item_type not in result["items"]:
                result["items"][item_type] = []
            
            try:
                added_at = str(getattr(item, 'addedAt', 'Unknown date'))
                
                if item_type == 'movie':
                    result["items"][item_type].append({
                        "title": item.title,
                        "year": getattr(item, 'year', ''),
                        "addedAt": added_at
                    })
                
                elif item_type == 'show':
                    result["items"][item_type].append({
                        "title": item.title,
                        "year": getattr(item, 'year', ''),
                        "addedAt": added_at
                    })
                
                elif item_type == 'season':
                    result["items"][item_type].append({
                        "showTitle": getattr(item, 'parentTitle', 'Unknown Show'),
                        "seasonNumber": getattr(item, 'index', '?'),
                        "addedAt": added_at
                    })
                
                elif item_type == 'episode':
                    result["items"][item_type].append({
                        "showTitle": getattr(item, 'grandparentTitle', 'Unknown Show'),
                        "seasonNumber": getattr(item, 'parentIndex', '?'),
                        "episodeNumber": getattr(item, 'index', '?'),
                        "title": item.title,
                        "addedAt": added_at
                    })
                
                elif item_type == 'artist':
                    result["items"][item_type].append({
                        "title": item.title,
                        "addedAt": added_at
                    })
                
                elif item_type == 'album':
                    result["items"][item_type].append({
                        "artist": getattr(item, 'parentTitle', 'Unknown Artist'),
                        "title": item.title,
                        "addedAt": added_at
                    })
                
                elif item_type == 'track':
                    result["items"][item_type].append({
                        "artist": getattr(item, 'grandparentTitle', 'Unknown Artist'),
                        "album": getattr(item, 'parentTitle', 'Unknown Album'),
                        "title": item.title,
                        "addedAt": added_at
                    })
                
                else:
                    # Generic handler for other types
                    result["items"][item_type].append({
                        "title": getattr(item, 'title', 'Unknown'),
                        "addedAt": added_at
                    })
            
            except Exception as format_error:
                # If there's an error formatting a particular item, just output basic info
                result["items"][item_type].append({
                    "title": getattr(item, 'title', 'Unknown'),
                    "error": str(format_error)
                })
        
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error getting recently added items: {str(e)}"})

@mcp.tool()
async def library_get_contents(
    library_name: str, 
    unwatched: bool = False, 
    watched: bool = False,
    sort: Optional[str] = None, 
    offset: int = 0, 
    limit: int = 50,
    genre: Optional[str] = None,
    year: Optional[Union[int, str]] = None,
    content_rating: Optional[str] = None,
    director: Optional[str] = None,
    actor: Optional[str] = None,
    writer: Optional[str] = None,
    resolution: Optional[str] = None,
    network: Optional[str] = None,
    studio: Optional[str] = None
) -> str:
    """Get the filtered and paginated contents of a specific library.
    
    Args:
        library_name: Name of the library to get contents from
        unwatched: If True, only return unwatched items
        watched: If True, only return watched items
        sort: Sort order (e.g., 'addedAt:desc', 'title:asc')
        offset: Number of items to skip (default: 0)
        limit: Maximum number of items to return (default: 50)
        genre: Filter by genre tag
        year: Filter by release year
        content_rating: Filter by content rating (e.g., 'PG-13')
        director: Filter by director tag
        actor: Filter by actor tag
        writer: Filter by writer tag
        resolution: Filter by resolution (e.g., '4k', '1080')
        network: Filter by network tag (primarily for TV)
        studio: Filter by studio tag
    
    Returns:
        JSON string listing items in the library with pagination metadata
    """
    try:
        plex = connect_to_plex()
        base_url = plex._baseurl
        headers = get_plex_headers(plex)
        
        async with aiohttp.ClientSession() as session:
            # First get library sections
            sections_url = urljoin(base_url, 'library/sections')
            sections_data = await async_get_json(session, sections_url, headers)
            
            target_section = None
            for section in sections_data['MediaContainer']['Directory']:
                if section['title'].lower() == library_name.lower():
                    target_section = section
                    break
                    
            if not target_section:
                return json.dumps({"error": f"Library '{library_name}' not found"})
            
            section_id = target_section['key']
            library_type = target_section['type']
            
            from urllib.parse import urlencode
            
            # Build query parameters for filtering and pagination
            # Plex supports 'start' and 'size' as query parameters for library sections
            query_params = {
                'start': offset,
                'size': limit
            }
            if unwatched:
                query_params['unwatched'] = '1'
            elif watched:
                query_params['unwatched'] = '0'
            if sort:
                query_params['sort'] = sort
            
            # Add advanced filters
            if genre:
                query_params['genre'] = genre
            if year:
                query_params['year'] = str(year)
            if content_rating:
                query_params['contentRating'] = content_rating
            if director:
                query_params['director'] = director
            if actor:
                query_params['actor'] = actor
            if writer:
                query_params['writer'] = writer
            if resolution:
                query_params['resolution'] = resolution
            if network:
                query_params['network'] = network
            if studio:
                query_params['studio'] = studio
            
            # Also set pagination headers which Plex often expects/supports
            request_headers = headers.copy()
            request_headers['X-Plex-Container-Start'] = str(offset)
            request_headers['X-Plex-Container-Size'] = str(limit)
            
            # Get items with filters and pagination
            all_items_url = urljoin(base_url, f'library/sections/{section_id}/all?{urlencode(query_params)}')
            all_data = await async_get_json(session, all_items_url, request_headers)
            all_data = all_data['MediaContainer']
            
            # Prepare the result
            result = {
                "name": target_section['title'],
                "type": library_type,
                "totalItems": all_data.get('totalSize', all_data.get('size', 0)),
                "offset": offset,
                "limit": limit,
                "size": all_data.get('size', 0),
                "items": []
            }
            
            # Process items based on library type
            if library_type == 'movie':
                for item in all_data.get('Metadata', []):
                    year = item.get('year', 'Unknown')
                    duration = item.get('duration', 0)
                    # Convert duration from milliseconds to hours and minutes
                    hours, remainder = divmod(duration // 1000, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    # Get media info
                    media_info = {}
                    if 'Media' in item:
                        media = item['Media'][0] if item['Media'] else {}
                        resolution = media.get('videoResolution', '')
                        codec = media.get('videoCodec', '')
                        if resolution and codec:
                            media_info = {
                                "resolution": resolution,
                                "codec": codec
                            }
                    
                    # Check if watched
                    watched = item.get('viewCount', 0) > 0
                    
                    result["items"].append({
                        "title": item.get('title', ''),
                        "year": year,
                        "duration": {
                            "hours": hours,
                            "minutes": minutes
                        },
                        "mediaInfo": media_info,
                        "watched": watched
                    })
            
            elif library_type == 'show':
                # Get all shows metadata in parallel
                show_urls = [
                    (item["ratingKey"], urljoin(base_url, f'library/metadata/{item["ratingKey"]}'))
                    for item in all_data.get('Metadata', [])
                ]
                show_responses = await asyncio.gather(
                    *[async_get_json(session, url, headers) for _, url in show_urls]
                )
                
                for item, show_data in zip(all_data.get('Metadata', []), show_responses):
                    show_data = show_data['MediaContainer']['Metadata'][0]
                    
                    year = item.get('year', 'Unknown')
                    season_count = show_data.get('childCount', 0)
                    episode_count = show_data.get('leafCount', 0)
                    watched = episode_count > 0 and show_data.get('viewedLeafCount', 0) == episode_count
                    
                    result["items"].append({
                        "title": item.get('title', ''),
                        "year": year,
                        "seasonCount": season_count,
                        "episodeCount": episode_count,
                        "watched": watched
                    })
            
            elif library_type == 'artist':
                # Process artists one by one for more accurate track/album counting
                artists_info = {}
                
                for artist in all_data.get('Metadata', []):
                    artist_id = artist.get('ratingKey')
                    artist_name = artist.get('title', '')
                    
                    if not artist_id:
                        continue
                    
                    # Store the original artist viewCount and skipCount as fallback
                    orig_view_count = artist.get('viewCount', 0)
                    orig_skip_count = artist.get('skipCount', 0)
                    
                    # Get tracks directly for this artist
                    artist_tracks_url = urljoin(base_url, f'library/sections/{section_id}/all?artist.id={artist_id}&type=10')
                    artist_tracks_data = await async_get_json(session, artist_tracks_url, headers)
                    
                    # Initialize artist data
                    if artist_name not in artists_info:
                        artists_info[artist_name] = {
                            "title": artist_name,
                            "albums": set(),
                            "trackCount": 0,
                            "viewCount": 0,
                            "skipCount": 0
                        }
                    
                    # Count tracks and albums from the track-level data
                    track_view_count = 0
                    track_skip_count = 0
                    if 'MediaContainer' in artist_tracks_data and 'Metadata' in artist_tracks_data['MediaContainer']:
                        for track in artist_tracks_data['MediaContainer']['Metadata']:
                            # Count each track
                            artists_info[artist_name]["trackCount"] += 1
                            
                            # Add album to set (to get unique album count)
                            if 'parentTitle' in track and track['parentTitle']:
                                artists_info[artist_name]["albums"].add(track['parentTitle'])
                            
                            # Count views and skips
                            track_view_count += track.get('viewCount', 0)
                            track_skip_count += track.get('skipCount', 0)
                    
                    # Use the sum of track counts if they're non-zero, otherwise fall back to artist level counts
                    artists_info[artist_name]["viewCount"] = track_view_count if track_view_count > 0 else orig_view_count
                    artists_info[artist_name]["skipCount"] = track_skip_count if track_skip_count > 0 else orig_skip_count
                
                # Convert album sets to counts and add to results
                for artist_name, info in artists_info.items():
                    result["items"].append({
                        "title": info["title"],
                        "albumCount": len(info["albums"]),
                        "trackCount": info["trackCount"],
                        "viewCount": info["viewCount"],
                        "skipCount": info["skipCount"]
                    })
            
            else:
                # Generic handler for other types
                for item in all_data.get('Metadata', []):
                    result["items"].append({
                        "title": item.get('title', '')
                    })
            
            return json.dumps(result)
            
    except Exception as e:
        return json.dumps({"error": f"Error getting library contents: {str(e)}"})
