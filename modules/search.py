from typing import Optional
from modules import mcp, connect_to_plex

@mcp.tool()
async def search_media(query: str, content_type: str = None) -> str:
    """Search for media across all libraries.
    
    Args:
        query: Search term to look for
        content_type: Optional content type to limit search to
    """
    try:
        plex = connect_to_plex()
        results = []
                
        if content_type in ["movie", "show", "season", "episode", "album", "track", "artist"]:
                results = plex.library.search(title=query, libtype=content_type)
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
                    if item_type == 'movie':
                        title = item.title
                        year = getattr(item, 'year', '')
                        rating = getattr(item, 'rating', '')
                        output += f"- {title} ({year}) [{rating}]\n"
                    
                    elif item_type == 'show':
                        title = item.title
                        year = getattr(item, 'year', '')
                        seasons = len(item.seasons()) if hasattr(item, 'seasons') and callable(item.seasons) else 0
                        output += f"- {title} ({year}) - {seasons} seasons\n"
                    
                    elif item_type == 'season':
                        show_title = getattr(item, 'parentTitle', 'Unknown Show')
                        season_num = getattr(item, 'index', '?')
                        output += f"- {show_title}: Season {season_num}\n"
                    
                    elif item_type == 'episode':
                        show_title = getattr(item, 'grandparentTitle', 'Unknown Show')
                        season_num = getattr(item, 'parentIndex', '?')
                        episode_num = getattr(item, 'index', '?')
                        title = item.title
                        output += f"- {show_title}: S{season_num}E{episode_num} - {title}\n"
                    
                    elif item_type == 'artist':
                        title = item.title
                        albums = len(item.albums()) if hasattr(item, 'albums') and callable(item.albums) else 0
                        output += f"- {title} - {albums} albums\n"
                    
                    elif item_type == 'album':
                        artist = getattr(item, 'parentTitle', 'Unknown Artist')
                        title = item.title
                        tracks = len(item.tracks()) if hasattr(item, 'tracks') and callable(item.tracks) else 0
                        output += f"- {artist} - {title} ({tracks} tracks)\n"
                    
                    elif item_type == 'track':
                        artist = getattr(item, 'grandparentTitle', 'Unknown Artist')
                        album = getattr(item, 'parentTitle', 'Unknown Album')
                        title = item.title
                        output += f"- {artist} - {album} - {title}\n"
                    
                    else:
                        # Generic handler for other types
                        title = getattr(item, 'title', 'Unknown')
                        output += f"- {title}\n"
                
                except Exception as format_error:
                    # If there's an error formatting a particular item, just output basic info
                    title = getattr(item, 'title', 'Unknown')
                    output += f"- {title} (Error: {str(format_error)})\n"
            
            output += "\n"
        
        return output
    except Exception as e:
        return f"Error searching: {str(e)}"
