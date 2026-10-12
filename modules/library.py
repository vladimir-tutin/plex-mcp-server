import json
import requests
import aiohttp
import asyncio
from plexapi.exceptions import NotFound # type: ignore
from modules import mcp, connect_to_plex
from modules.profiles import server_for_user
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
    library_name: Optional[str] = None,
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
    studio: Optional[str] = None,
    username: Optional[str] = None,
    title: Optional[str] = None,
    media_type: Optional[str] = None
) -> str:
    """Get filtered, paginated items from one library or across accessible libraries.
    
    Args:
        library_name: Optional library name. Omit to search all accessible libraries; media_type is then required.
        media_type: movie, show, episode, artist, album, or track. Defaults to the named library type.
        unwatched: Only unplayed items; for shows, those with unwatched episodes (including partial shows).
        watched: Only return played items; for shows, those with no unwatched episodes.
            Partially watched shows are excluded; inspect watchStatus and watchedEpisodeCount.
            Cannot be combined with unwatched. Watch state belongs to the selected user.
        sort: Sort order (e.g., 'addedAt:desc', 'title:asc')
        offset: Number of items to skip (default: 0)
        limit: Maximum number of items to return (default: 50)
        title: Case-insensitive Plex title search, not exact-only or arbitrary substring matching.
            Searches names of the selected media_type; TV libraries default to show names.
            Applied before pagination and combined with the other filters.
        genre: Filter by genre tag (parent show genre for episodes).
        year: Filter by release year (parent album year for tracks).
        content_rating: Filter by content rating (e.g., 'PG-13')
        director: Filter by director tag
        actor: Filter by actor tag
        writer: Filter by writer tag
        resolution: Filter by resolution (e.g., '4k', '1080')
        network: Filter by network tag (primarily for TV)
        studio: Filter by studio (parent show for episodes, parent album for tracks).
        username: Optional Plex username or profile title; omit for the configured account. Failed access returns an error.
    
    Returns:
        JSON string listing items with media_id and pagination metadata. For shows,
        watched means all available episodes are played; watchStatus distinguishes
        unwatched, partial, and watched. Empty shows are unwatched.
        Movies also include inProgress (a positive saved playback offset) and
        progressPercent (0-100, or null if duration is unknown), independently of
        watched and Continue Watching membership. This is not live playback status.
    """
    type_ids = {"movie": 1, "show": 2, "episode": 4, "artist": 8, "album": 9, "track": 10}
    if media_type is not None and media_type not in type_ids:
        return json.dumps({"error": "media_type must be movie, show, episode, artist, album, or track"})
    if not library_name and not media_type:
        return json.dumps({"error": "Specify library_name or media_type"})
    if resolution is not None:
        resolution = resolution.strip().lower()
        if resolution not in {'sd', '480', '576', '720', '1080', '2k', '4k', '8k'}:
            return json.dumps({'error': 'resolution must be sd, 480, 576, 720, 1080, 2k, 4k, or 8k'})
    if offset < 0 or limit < 1:
        return json.dumps({"error": "offset must be nonnegative and limit must be positive"})
    if watched and unwatched:
        return json.dumps({"error": "watched and unwatched cannot both be true"})

    try:
        plex = await asyncio.to_thread(lambda: server_for_user(connect_to_plex(), username=username))
        base_url = plex._baseurl
        headers = get_plex_headers(plex)
        
        async with aiohttp.ClientSession() as session:
            section_id = None
            target_section = {"title": "All libraries", "type": media_type}
            if library_name:
                sections_data = await async_get_json(session, urljoin(base_url, 'library/sections'), headers)
                target_section = next((section for section in sections_data['MediaContainer']['Directory']
                                       if section['title'].lower() == library_name.lower()), None)
                if target_section is None:
                    return json.dumps({"error": f"Library '{library_name}' not found."})
                section_id = target_section['key']
                allowed = {'movie': {'movie'}, 'show': {'show', 'episode'},
                           'artist': {'artist', 'album', 'track'}}
                if media_type and media_type not in allowed.get(target_section['type'], set()):
                    return json.dumps({"error": f"media_type '{media_type}' is incompatible with this library"})
            library_type = media_type or target_section['type']

            from urllib.parse import urlencode
            
            # Build query parameters for filtering and pagination
            # Plex supports 'start' and 'size' as query parameters for library sections
            query_params = {
                'start': offset,
                'size': limit
            }
            if media_type:
                query_params['type'] = type_ids[media_type]
            watch_filter = 'show.unwatchedLeaves' if library_type == 'show' else 'unwatched'
            if unwatched:
                query_params[watch_filter] = '1'
            elif watched:
                query_params[watch_filter] = '0'
            if sort:
                query_params['sort'] = sort
            
            # Add advanced filters
            if title and title.strip():
                query_params['title'] = title.strip()
            if genre:
                query_params['genre'] = genre
            if year is not None:
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
            
            # Qualify parent metadata filters, and reject combinations Plex would ignore.
            supplied = {k: v for k, v in {
                'genre': genre, 'year': year, 'contentRating': content_rating,
                'director': director, 'actor': actor, 'writer': writer,
                'resolution': resolution, 'network': network, 'studio': studio,
            }.items() if v is not None and v != ''}
            supported = {
                'movie': {'genre', 'year', 'contentRating', 'director', 'actor', 'writer', 'resolution', 'studio'},
                'show': {'genre', 'year', 'contentRating', 'director', 'actor', 'writer', 'network', 'studio'},
                'episode': {'genre', 'year', 'contentRating', 'director', 'actor', 'writer', 'resolution', 'network', 'studio'},
                'artist': {'genre'}, 'album': {'genre', 'year', 'studio'},
                'track': {'genre', 'year', 'studio'},
            }
            invalid = set(supplied) - supported.get(library_type, set())
            if invalid:
                return json.dumps({'error': f"Unsupported filters for {library_type}: {', '.join(sorted(invalid))}"})
            for field in list(supplied):
                if library_type == 'episode' and field in {'genre', 'contentRating', 'director', 'actor', 'writer', 'network', 'studio'}:
                    query_params['show.' + field] = query_params.pop(field)
                elif library_type == 'track' and field in {'year', 'studio'}:
                    query_params['album.' + field] = query_params.pop(field)

            # Also set pagination headers which Plex often expects/supports
            request_headers = headers.copy()
            request_headers['X-Plex-Container-Start'] = str(offset)
            request_headers['X-Plex-Container-Size'] = str(limit)
            
            # Get items with filters and pagination
            endpoint = f'library/sections/{section_id}/all' if section_id else 'library/all'
            all_items_url = urljoin(base_url, f'{endpoint}?{urlencode(query_params)}')
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
            if library_type in ('movie', 'episode', 'track'):
                for item in all_data.get('Metadata', []):
                    year = item.get('year', 'Unknown')
                    duration = item.get('duration') or 0
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
                    # Saved progress is independent of completed plays and may
                    # remain even when Plex omits the movie from Continue Watching.
                    playback_offset = max(0, item.get('viewOffset') or 0)
                    progress_percent = (
                        round(min(100, playback_offset / duration * 100), 1)
                        if duration > 0 else None
                    )
                    
                    result["items"].append({
                        "media_id": item.get('ratingKey'),
                        "title": item.get('title', ''),
                        "year": year,
                        "duration": {
                            "hours": hours,
                            "minutes": minutes
                        },
                        "mediaInfo": media_info,
                        "watched": watched,
                        "inProgress": playback_offset > 0,
                        "progressPercent": progress_percent
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
                    watched_episode_count = show_data.get('viewedLeafCount', 0)
                    fully_watched = episode_count > 0 and watched_episode_count >= episode_count
                    watch_status = "watched" if fully_watched else (
                        "partial" if watched_episode_count > 0 else "unwatched"
                    )
                    
                    result["items"].append({
                        "media_id": item.get('ratingKey'),
                        "title": item.get('title', ''),
                        "year": year,
                        "seasonCount": season_count,
                        "episodeCount": episode_count,
                        "watchedEpisodeCount": watched_episode_count,
                        "watchStatus": watch_status,
                        "watched": fully_watched
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
                    artist_tracks_url = urljoin(base_url, f'{endpoint}?artist.id={artist_id}&type=10')
                    artist_tracks_data = await async_get_json(session, artist_tracks_url, headers)
                    
                    # Initialize artist data
                    if artist_id not in artists_info:
                        artists_info[artist_id] = {
                            "media_id": artist_id,
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
                            artists_info[artist_id]["trackCount"] += 1
                            
                            # Add album to set (to get unique album count)
                            if 'parentTitle' in track and track['parentTitle']:
                                artists_info[artist_id]["albums"].add(track['parentTitle'])
                            
                            # Count views and skips
                            track_view_count += track.get('viewCount', 0)
                            track_skip_count += track.get('skipCount', 0)
                    
                    # Use the sum of track counts if they're non-zero, otherwise fall back to artist level counts
                    artists_info[artist_id]["viewCount"] = track_view_count if track_view_count > 0 else orig_view_count
                    artists_info[artist_id]["skipCount"] = track_skip_count if track_skip_count > 0 else orig_skip_count
                
                # Convert album sets to counts and add to results
                for info in artists_info.values():
                    result["items"].append({
                        "media_id": info["media_id"],
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
                        "media_id": item.get('ratingKey'),
                        "title": item.get('title', '')
                    })
            
            # Preserve existing fields while identifying the originating library and parent media.
            for formatted, raw in zip(result['items'], all_data.get('Metadata', [])):
                if media_type or not library_name:
                    formatted['type'] = raw.get('type', library_type)
                    formatted['library'] = raw.get('librarySectionTitle', library_name)
                    formatted['library_id'] = raw.get('librarySectionID', section_id)
                    if library_type == 'episode':
                        formatted.update(show=raw.get('grandparentTitle'), season=raw.get('parentIndex'),
                                         episode=raw.get('index'))
                    elif library_type == 'track':
                        formatted.update(artist=raw.get('grandparentTitle'), album=raw.get('parentTitle'))
                    elif library_type == 'artist':
                        formatted['watched'] = formatted['viewCount'] > 0
                    elif library_type == 'album':
                        formatted.update(artist=raw.get('parentTitle'), viewCount=raw.get('viewCount', 0) or 0,
                                         watched=(raw.get('viewCount', 0) or 0) > 0)

            return json.dumps(result)
            
    except Exception as e:
        return json.dumps({"error": f"Error getting library contents: {str(e)}"})
