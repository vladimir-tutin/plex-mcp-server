from typing import Optional
from plexapi.exceptions import NotFound # type: ignore
from modules import mcp, connect_to_plex

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
async def get_library_stats(library_name: str) -> str:
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
            return f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"
        
        # Get the library stats
        result = f"Statistics for library '{target_section.title}':\n"
        result += f"Type: {target_section.type}\n"
        result += f"Total items: {target_section.totalSize}\n"
        
        # Type-specific stats
        if target_section.type == 'movie':
            result += "\n=== Movie Library Stats ===\n"
            result += f"Movies: {len(target_section.all())}\n"
            
            # Get unwatched movies count
            unwatched = target_section.search(unwatched=True)
            result += f"Unwatched: {len(unwatched)}\n"
            
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
            
            # Add to results if we have data
            if genres:
                result += "\nTop Genres:\n"
                for genre, count in sorted(genres.items(), key=lambda x: x[1], reverse=True)[:5]:
                    result += f"- {genre}: {count} movies\n"
            
            if directors:
                result += "\nTop Directors:\n"
                for director, count in sorted(directors.items(), key=lambda x: x[1], reverse=True)[:5]:
                    result += f"- {director}: {count} movies\n"
            
            if studios:
                result += "\nTop Studios:\n"
                for studio, count in sorted(studios.items(), key=lambda x: x[1], reverse=True)[:5]:
                    result += f"- {studio}: {count} movies\n"
                    
            if decades:
                result += "\nMovies by Decade:\n"
                for decade, count in sorted(decades.items()):
                    result += f"- {decade}s: {count} movies\n"
                    
        elif target_section.type == 'show':
            result += "\n=== TV Show Library Stats ===\n"
            all_shows = target_section.all()
            result += f"Shows: {len(all_shows)}\n"
            
            # Count seasons and episodes
            season_count = 0
            episode_count = 0
            for show in all_shows:
                seasons = show.seasons()
                season_count += len(seasons)
                for season in seasons:
                    episode_count += len(season.episodes())
            
            result += f"Seasons: {season_count}\n"
            result += f"Episodes: {episode_count}\n"
            
            # Get unwatched shows count
            unwatched_shows = target_section.search(unwatched=True)
            result += f"Unwatched Shows: {len(unwatched_shows)}\n"
            
        elif target_section.type == 'artist':
            result += "\n=== Music Library Stats ===\n"
            artists = target_section.all()
            result += f"Artists: {len(artists)}\n"
            
            # Count albums and tracks
            album_count = 0
            track_count = 0
            for artist in artists:
                albums = artist.albums()
                album_count += len(albums)
                for album in albums:
                    track_count += len(album.tracks())
            
            result += f"Albums: {album_count}\n"
            result += f"Tracks: {track_count}\n"
            
        return result
    except Exception as e:
        return f"Error getting library stats: {str(e)}"

@mcp.tool()
async def refresh_library(library_name: str = None) -> str:
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
                return f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"
            
            # Refresh the library
            section.refresh()
            return f"Refreshing library '{section.title}'. This may take some time."
        else:
            # Refresh all libraries
            plex.library.refresh()
            return "Refreshing all libraries. This may take some time."
    except Exception as e:
        return f"Error refreshing library: {str(e)}"

@mcp.tool()
async def scan_library(library_name: str, path: str = None) -> str:
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
            return f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"
        
        # Scan the library
        if path:
            try:
                section.update(path=path)
                return f"Scanning path '{path}' in library '{section.title}'. This may take some time."
            except NotFound:
                return f"Path '{path}' not found in library '{section.title}'."
        else:
            section.update()
            return f"Scanning library '{section.title}'. This may take some time."
    except Exception as e:
        return f"Error scanning library: {str(e)}"

@mcp.tool()
async def get_library_details(library_name: str) -> str:
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
            return f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"
        
        # Get the library details
        result = f"Details for library '{target_section.title}':\n"
        result += f"Type: {target_section.type}\n"
        result += f"UUID: {target_section.uuid}\n"
        result += f"Total items: {target_section.totalSize}\n"
        
        # Get locations
        result += "\nLocations:\n"
        for location in target_section.locations:
            result += f"- {location}\n"
        
        # Get agent, scanner, and language
        result += f"\nAgent: {target_section.agent}\n"
        result += f"Scanner: {target_section.scanner}\n"
        result += f"Language: {target_section.language}\n"
        
        # Get additional attributes using _data
        data = target_section._data
        
        # Add scanner settings if available
        if 'scannerSettings' in data:
            result += "\nScanner Settings:\n"
            for setting in data['scannerSettings']:
                if 'value' in setting:
                    value = setting['value']
                    result += f"- {setting.get('key', 'unknown')}: {value}\n"
        
        # Add agent settings if available
        if 'agentSettings' in data:
            result += "\nAgent Settings:\n"
            for setting in data['agentSettings']:
                if 'value' in setting:
                    value = setting['value']
                    result += f"- {setting.get('key', 'unknown')}: {value}\n"
        
        # Add advanced settings if available
        if 'advancedSettings' in data:
            result += "\nAdvanced Settings:\n"
            for setting in data['advancedSettings']:
                if 'value' in setting:
                    value = setting['value']
                    result += f"- {setting.get('key', 'unknown')}: {value}\n"
                
        return result
    except Exception as e:
        return f"Error getting library details: {str(e)}"

@mcp.tool()
async def get_recently_added(count: int = 50, library_name: str = None) -> str:
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
                return f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"
            
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
            return "No recently added items found."
        
        # Format the output
        result = f"Recently added items{' in ' + library_name if library_name else ''} (showing {len(recent)} of {count}):\n\n"
        
        # Group results by type
        results_by_type = {}
        for item in recent:
            item_type = getattr(item, 'type', 'unknown')
            if item_type not in results_by_type:
                results_by_type[item_type] = []
            results_by_type[item_type].append(item)
        
        # Output results organized by type
        for item_type, items in results_by_type.items():
            result += f"=== {item_type.upper()} ===\n"
            for item in items:
                try:
                    added_at = getattr(item, 'addedAt', 'Unknown date')
                    
                    if item_type == 'movie':
                        title = item.title
                        year = getattr(item, 'year', '')
                        result += f"- {title} ({year}) - Added: {added_at}\n"
                    
                    elif item_type == 'show':
                        title = item.title
                        year = getattr(item, 'year', '')
                        result += f"- {title} ({year}) - Added: {added_at}\n"
                    
                    elif item_type == 'season':
                        show_title = getattr(item, 'parentTitle', 'Unknown Show')
                        season_num = getattr(item, 'index', '?')
                        result += f"- {show_title}: Season {season_num} - Added: {added_at}\n"
                    
                    elif item_type == 'episode':
                        show_title = getattr(item, 'grandparentTitle', 'Unknown Show')
                        season_num = getattr(item, 'parentIndex', '?')
                        episode_num = getattr(item, 'index', '?')
                        title = item.title
                        result += f"- {show_title}: S{season_num}E{episode_num} - {title} - Added: {added_at}\n"
                    
                    elif item_type == 'artist':
                        title = item.title
                        result += f"- {title} - Added: {added_at}\n"
                    
                    elif item_type == 'album':
                        artist = getattr(item, 'parentTitle', 'Unknown Artist')
                        title = item.title
                        result += f"- {artist} - {title} - Added: {added_at}\n"
                    
                    elif item_type == 'track':
                        artist = getattr(item, 'grandparentTitle', 'Unknown Artist')
                        album = getattr(item, 'parentTitle', 'Unknown Album')
                        title = item.title
                        result += f"- {artist} - {album} - {title} - Added: {added_at}\n"
                    
                    else:
                        # Generic handler for other types
                        title = getattr(item, 'title', 'Unknown')
                        result += f"- {title} - Added: {added_at}\n"
                
                except Exception as format_error:
                    # If there's an error formatting a particular item, just output basic info
                    title = getattr(item, 'title', 'Unknown')
                    result += f"- {title} - Error: {str(format_error)}\n"
            
            result += "\n"
        
        return result
    except Exception as e:
        return f"Error getting recently added items: {str(e)}"

@mcp.tool()
async def get_library_contents(library_name: str, limit: int = 100, offset: int = 0) -> str:
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
            return f"Library '{library_name}' not found. Available libraries: {', '.join([s.title for s in all_sections])}"
        
        # Get all items in the library
        all_items = target_section.all()
        total_items = len(all_items)
        
        # Apply pagination
        paginated_items = all_items[offset:offset+limit]
        
        # Format the output
        result = f"Contents of library '{target_section.title}' (showing {len(paginated_items)} of {total_items} items):\n\n"
        
        # Output based on library type
        if target_section.type == 'movie':
            for item in paginated_items:
                year = getattr(item, 'year', 'Unknown')
                duration = getattr(item, 'duration', 0)
                # Convert duration from milliseconds to hours and minutes
                hours, remainder = divmod(duration // 1000, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                # Get resolution
                media_info = ""
                if hasattr(item, 'media') and item.media:
                    for media in item.media:
                        resolution = getattr(media, 'videoResolution', '')
                        codec = getattr(media, 'videoCodec', '')
                        if resolution and codec:
                            media_info = f" [{resolution} {codec}]"
                            break
                
                # Check if watched
                watched = "✓" if getattr(item, 'viewCount', 0) > 0 else " "
                
                result += f"{watched} {item.title} ({year}) - {hours}h {minutes}m{media_info}\n"
        
        elif target_section.type == 'show':
            for item in paginated_items:
                year = getattr(item, 'year', 'Unknown')
                season_count = len(item.seasons())
                episode_count = sum(len(season.episodes()) for season in item.seasons())
                
                # Check if all episodes are watched
                unwatched = item.unwatched()
                status = "✓" if len(unwatched) == 0 and episode_count > 0 else " "
                
                result += f"{status} {item.title} ({year}) - {season_count} seasons, {episode_count} episodes\n"
        
        elif target_section.type == 'artist':
            for item in paginated_items:
                album_count = len(item.albums())
                track_count = sum(len(album.tracks()) for album in item.albums())
                
                result += f"- {item.title} - {album_count} albums, {track_count} tracks\n"
        
        else:
            # Generic handler for other types
            for item in paginated_items:
                result += f"- {item.title}\n"
        
        # Add pagination info
        if total_items > limit:
            result += f"\nShowing items {offset+1}-{min(offset+limit, total_items)} of {total_items}."
            if offset + limit < total_items:
                result += f" Use offset={offset+limit} to see the next page."
            if offset > 0:
                result += f" Use offset={max(0, offset-limit)} to see the previous page."
        
        return result
    except Exception as e:
        return f"Error getting library contents: {str(e)}"
