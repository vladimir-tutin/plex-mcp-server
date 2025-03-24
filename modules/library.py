import json
from plexapi.exceptions import NotFound # type: ignore
from modules import mcp, connect_to_plex

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
        
        # Get all library sections
        all_sections = plex.library.sections()
        target_section = None
        
        # Find the section with the matching name (case-insensitive)
        for section in all_sections:
            if section.title.lower() == library_name.lower():
                target_section = section
                print(f"Found library: {target_section.title}")
                break
        
        if not target_section:
            return json.dumps({"error": f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"})
        
        # Create the response dictionary
        result = {
            "name": target_section.title,
            "type": target_section.type,
            "totalItems": target_section.totalSize
        }
        
        # Type-specific stats
        if target_section.type == 'movie':
            movie_stats = {
                "count": len(target_section.all()),
                "unwatched": len(target_section.search(unwatched=True))
            }
            
            # Get genres, directors and studios statistics
            genres = {}
            directors = {}
            studios = {}
            decades = {}
            
            for movie in target_section.all():
                # Process genres
                for genre in getattr(movie, 'genres', []) or []:
                    genre_name = genre.tag
                    genres[genre_name] = genres.get(genre_name, 0) + 1
                
                # Process directors
                for director in getattr(movie, 'directors', []) or []:
                    director_name = director.tag
                    directors[director_name] = directors.get(director_name, 0) + 1
                
                # Process studios
                studio = getattr(movie, 'studio', None)
                if studio:
                    studios[studio] = studios.get(studio, 0) + 1
                
                # Process decades
                year = getattr(movie, 'year', None)
                if year:
                    decade = (year // 10) * 10
                    decades[decade] = decades.get(decade, 0) + 1
            
            # Add top items to results
            if genres:
                movie_stats["topGenres"] = {}
                for genre, count in sorted(genres.items(), key=lambda x: x[1], reverse=True)[:5]:
                    movie_stats["topGenres"][genre] = count
            
            if directors:
                movie_stats["topDirectors"] = {}
                for director, count in sorted(directors.items(), key=lambda x: x[1], reverse=True)[:5]:
                    movie_stats["topDirectors"][director] = count
            
            if studios:
                movie_stats["topStudios"] = {}
                for studio, count in sorted(studios.items(), key=lambda x: x[1], reverse=True)[:5]:
                    movie_stats["topStudios"][studio] = count
                    
            if decades:
                movie_stats["byDecade"] = {}
                for decade, count in sorted(decades.items()):
                    movie_stats["byDecade"][str(decade)] = count
            
            result["movieStats"] = movie_stats
                    
        elif target_section.type == 'show':
            all_shows = target_section.all()
            
            # Count seasons and episodes
            season_count = 0
            episode_count = 0
            for show in all_shows:
                seasons = show.seasons()
                season_count += len(seasons)
                for season in seasons:
                    episode_count += len(season.episodes())
            
            show_stats = {
                "shows": len(all_shows),
                "seasons": season_count,
                "episodes": episode_count,
                "unwatchedShows": len(target_section.search(unwatched=True))
            }
            
            result["showStats"] = show_stats
            
        elif target_section.type == 'artist':
            artists = target_section.all()
            
            # Count albums and tracks
            album_count = 0
            track_count = 0
            for artist in artists:
                albums = artist.albums()
                album_count += len(albums)
                for album in albums:
                    track_count += len(album.tracks())
            
            music_stats = {
                "artists": len(artists),
                "albums": album_count,
                "tracks": track_count
            }
            
            result["musicStats"] = music_stats
            
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error getting library stats: {str(e)}"})

@mcp.tool()
async def library_refresh(library_name: str = None) -> str:
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
async def library_scan(library_name: str, path: str = None) -> str:
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
async def library_get_recently_added(count: int = 50, library_name: str = None) -> str:
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
async def library_get_contents(library_name: str, limit: int = 100, offset: int = 0) -> str:
    """Get the full contents of a specific library.
    
    Args:
        library_name: Name of the library to get contents from
        limit: Maximum number of items to return (default: 100)
        offset: Number of items to skip (default: 0)
    
    Returns:
        String listing all items in the library
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
        
        # Get all items in the library
        all_items = target_section.all()
        total_items = len(all_items)
        
        # Apply pagination
        paginated_items = all_items[offset:offset+limit]
        
        # Prepare the result
        result = {
            "name": target_section.title,
            "type": target_section.type,
            "totalItems": total_items,
            "offset": offset,
            "limit": limit,
            "itemsReturned": len(paginated_items),
            "items": []
        }
        
        # Output based on library type
        if target_section.type == 'movie':
            for item in paginated_items:
                year = getattr(item, 'year', 'Unknown')
                duration = getattr(item, 'duration', 0)
                # Convert duration from milliseconds to hours and minutes
                hours, remainder = divmod(duration // 1000, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                # Get resolution
                media_info = {}
                if hasattr(item, 'media') and item.media:
                    for media in item.media:
                        resolution = getattr(media, 'videoResolution', '')
                        codec = getattr(media, 'videoCodec', '')
                        if resolution and codec:
                            media_info = {
                                "resolution": resolution,
                                "codec": codec
                            }
                            break
                
                # Check if watched
                watched = getattr(item, 'viewCount', 0) > 0
                
                result["items"].append({
                    "title": item.title,
                    "year": year,
                    "duration": {
                        "hours": hours,
                        "minutes": minutes
                    },
                    "mediaInfo": media_info,
                    "watched": watched
                })
        
        elif target_section.type == 'show':
            for item in paginated_items:
                year = getattr(item, 'year', 'Unknown')
                season_count = len(item.seasons())
                episode_count = sum(len(season.episodes()) for season in item.seasons())
                
                # Check if all episodes are watched
                unwatched = item.unwatched()
                watched = len(unwatched) == 0 and episode_count > 0
                
                result["items"].append({
                    "title": item.title,
                    "year": year,
                    "seasonCount": season_count,
                    "episodeCount": episode_count,
                    "watched": watched
                })
        
        elif target_section.type == 'artist':
            for item in paginated_items:
                album_count = len(item.albums())
                track_count = sum(len(album.tracks()) for album in item.albums())
                
                result["items"].append({
                    "title": item.title,
                    "albumCount": album_count,
                    "trackCount": track_count
                })
        
        else:
            # Generic handler for other types
            for item in paginated_items:
                result["items"].append({
                    "title": item.title
                })
        
        # Add pagination info
        if total_items > limit:
            result["pagination"] = {
                "showing": {
                    "from": offset + 1,
                    "to": min(offset + limit, total_items),
                    "of": total_items
                }
            }
            
            if offset + limit < total_items:
                result["pagination"]["nextOffset"] = offset + limit
            if offset > 0:
                result["pagination"]["previousOffset"] = max(0, offset - limit)
        
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error getting library contents: {str(e)}"})
