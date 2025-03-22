from modules import mcp, connect_to_plex
from typing import List
from plexapi.exceptions import NotFound # type: ignore
import base64
import os

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

@mcp.tool()
async def get_media_details(media_title: str, library_name: str = None) -> str:
    """Get detailed information about a specific media item using PlexAPI's Media and Mixin functions.
    
    Args:
        media_title: Title of the media to get details for
        library_name: Optional library name to limit search to
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        results = []
        if library_name:
            target_section = plex.library.section(library_name)
            results = target_section.search(title=media_title)
        else:
            results = plex.search(title=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        media = results[0]
        
        # Use PlexAPI's Media and Mixin functions to gather details
        details = {
            'Title': media.title,
            'Type': media.type,
            'Summary': media.summary,
            'Added At': media.addedAt.strftime("%Y-%m-%d %H:%M:%S") if media.addedAt else 'Unknown',
            'Rating': media.rating if hasattr(media, 'rating') else 'N/A',
            'Content Rating': media.contentRating if hasattr(media, 'contentRating') else 'N/A',
            'Duration': f"{media.duration // 60000} minutes" if media.duration else 'N/A',
            'Studio': media.studio if hasattr(media, 'studio') else 'N/A',
            'Genres': ', '.join([genre.tag for genre in media.genres]) if hasattr(media, 'genres') else 'N/A',
            'Directors': ', '.join([director.tag for director in media.directors]) if hasattr(media, 'directors') else 'N/A',
            'Writers': ', '.join([writer.tag for writer in media.writers]) if hasattr(media, 'writers') else 'N/A',
            'Actors': ', '.join([actor.tag for actor in media.actors]) if hasattr(media, 'actors') else 'N/A',
        }
        
        # Format the details into a string
        result = f"Details for '{media.title}' [{media.type}]:\n"
        for key, value in details.items():
            result += f"{key}: {value}\n"
        
        return result
    except Exception as e:
        return f"Error getting media details: {str(e)}"

@mcp.tool()
async def edit_metadata(media_title: str, library_name: str = None, 
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
                results = library.search(title=media_title)
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
async def extract_media_images(media_title: str, library_name: str = None, 
                              output_dir: str = "./", image_types: List[str] = ["poster", "art"], output_format: str = "base64") -> str:
    """Extract all images associated with a media item.
    
    Args:
        media_title: Title of the media to extract images from
        library_name: Optional library name to limit search to
        output_dir: Directory to save images to (default: current directory)
        image_types: Types of images to extract (e.g., poster, art, thumb, banner)
        output_format: Format to return image data in (base64, url, or file)
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(title=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            results = plex.search(title=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."
        
        media = results[0]
        
        # Define image attributes to check
        image_attributes = {
            "poster": "thumb",
            "art": "art",
            "banner": "banner",
            "theme": "theme",
            "thumbnail": "thumb"
        }
        
        # Extract requested images
        extracted_images = {}
        
        for img_type in image_types:
            attr = image_attributes.get(img_type.lower())
            if not attr:
                continue
            
            # Check if this attribute exists on the media object
            img_url = getattr(media, attr, None)
            if img_url:
                # Use get_media_poster to handle the image processing
                # We need to temporarily change the media's thumb attribute to the current image URL
                original_thumb = media.thumb
                media.thumb = img_url  # Set the thumb to the current image URL
                
                try:
                    # Use get_media_poster to retrieve the image
                    result = await get_media_poster(
                        media_title=media_title,
                        library_name=library_name,
                        output_path=os.path.join(output_dir, f"{media.title}_{img_type}.jpg") if output_format == "file" else None,
                        output_format=output_format
                    )
                    
                    # Add to our results
                    if output_format == "file":
                        extracted_images[img_type] = os.path.join(output_dir, f"{media.title}_{img_type}.jpg")
                    elif output_format == "url":
                        extracted_images[img_type] = img_url
                    elif output_format == "base64":
                        extracted_images[img_type] = result
                    
                finally:
                    # Restore the original thumb attribute
                    media.thumb = original_thumb
                
        if not extracted_images:
            return f"No images found for '{media_title}' with the requested types."
        
        return extracted_images
    except Exception as e:
        return f"Error extracting images: {str(e)}"

@mcp.tool()
async def delete_media(media_title: str, library_name: str = None) -> str:
    """Delete a media item from the Plex library.
    
    Args:
        media_title: Title of the media to delete
        library_name: Optional library name to limit search to
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        results = []
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(title=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            # Search in all libraries
            results = plex.search(title=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        # If only one result, delete it directly
        if len(results) == 1:
            media = results[0]
            media_type = getattr(media, 'type', 'unknown')
            year = getattr(media, 'year', '')
            year_str = f" ({year})" if year else ""
            
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
            
            # Format the information message
            info_message = f"'{media.title}{year_str}' [{media_type}] will be removed from library."
            
            if file_paths:
                info_message += "\nFiles that will remain on disk:"
                for path in file_paths:
                    info_message += f"\n- {path}"
            
            # Perform the deletion
            try:
                media.delete()
                return f"Successfully removed '{media.title}{year_str}' from library.\n\n{info_message}"
            except Exception as delete_error:
                return f"Error during deletion: {str(delete_error)}"
        
        # Multiple results found - return detailed information to help user select
        else:
            result_list = f"Multiple items found matching '{media_title}'. Please specify which one to delete:\n\n"
            
            for idx, item in enumerate(results, 1):
                # Get basic information
                title = getattr(item, 'title', 'Unknown')
                item_type = getattr(item, 'type', 'unknown')
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                
                # Add library information if available
                library_title = getattr(item, 'librarySectionTitle', '')
                library_str = f" [Library: {library_title}]" if library_title else ""
                
                # Format based on item type
                if item_type == 'movie':
                    result_list += f"{idx}. Movie: {title}{year_str}{library_str}\n"
                elif item_type == 'show':
                    result_list += f"{idx}. TV Show: {title}{year_str}{library_str}\n"
                elif item_type == 'episode':
                    show = getattr(item, 'grandparentTitle', 'Unknown Show')
                    season = getattr(item, 'parentIndex', '?')
                    episode = getattr(item, 'index', '?')
                    result_list += f"{idx}. Episode: {show} - S{season:02d}E{episode:02d} - {title}{library_str}\n"
                elif item_type == 'artist':
                    result_list += f"{idx}. Artist: {title}{library_str}\n"
                elif item_type == 'album':
                    artist = getattr(item, 'parentTitle', 'Unknown Artist')
                    result_list += f"{idx}. Album: {artist} - {title}{year_str}{library_str}\n"
                elif item_type == 'track':
                    artist = getattr(item, 'grandparentTitle', 'Unknown Artist')
                    album = getattr(item, 'parentTitle', 'Unknown Album')
                    result_list += f"{idx}. Track: {artist} - {album} - {title}{library_str}\n"
                else:
                    result_list += f"{idx}. {item_type.capitalize()}: {title}{library_str}\n"
            
            result_list += "\nTo delete a specific item, call this function again with a more specific title or specify a library."
            return result_list
            
    except Exception as e:
        return f"Error deleting media: {str(e)}"

@mcp.tool()
async def get_media_artwork(media_title: str, library_name: str = None, 
                           art_type: str = "poster", output_format: str = "base64",
                           output_path: str = None) -> dict:
    """Get artwork for a specific media item.
    
    Args:
        media_title: Title of the media to get artwork for
        library_name: Optional library name to limit search to
        art_type: Type of artwork to get (poster, background, art, logo)
        output_format: Format to return image data in (base64, url, or file)
        output_path: Optional path to save the image to a file
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(title=media_title)
            except NotFound:
                return {"error": f"Library '{library_name}' not found."}
        else:
            results = plex.search(title=media_title)
        
        if not results:
            return {"error": f"No media found matching '{media_title}'."}
        
        if len(results) > 1:
            return {"error": f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."}
        
        media = results[0]
        
        # Normalize art type
        art_type = art_type.lower()
        
        # Map art types to their URL attributes
        art_map = {
            "poster": "thumbUrl",
            "thumbnail": "thumbUrl",
            "thumb": "thumbUrl",
            "background": "artUrl",
            "art": "artUrl", 
            "logo": "logoUrl",
            "banner": "bannerUrl"
        }
        
        if art_type not in art_map:
            return {"error": f"Invalid art type: {art_type}. Supported types: {', '.join(art_map.keys())}"}
        
        # Get URL for the requested art type
        url_attr = art_map[art_type]
        if not hasattr(media, url_attr):
            return {"error": f"This media item doesn't have {art_type} artwork."}
        
        artwork_url = getattr(media, url_attr)
        if not artwork_url:
            return {"error": f"No {art_type} artwork found for '{media_title}'."}
        
        # Get available artwork versions based on type
        available_versions = []
        if art_type in ["poster", "thumb", "thumbnail"]:
            if hasattr(media, "posters") and callable(getattr(media, "posters")):
                try:
                    available_versions = media.posters()
                except:
                    pass
        elif art_type in ["background", "art"]:
            if hasattr(media, "arts") and callable(getattr(media, "arts")):
                try:
                    available_versions = media.arts()
                except:
                    pass
        elif art_type == "logo":
            if hasattr(media, "logos") and callable(getattr(media, "logos")):
                try:
                    available_versions = media.logos()
                except:
                    pass
                    
        # Handle different output formats
        if output_format == "url":
            return {
                "filename": f"{media.title}_{art_type}.jpg",
                "type": art_type,
                "url": artwork_url,
                "versions_available": len(available_versions)
            }
        
        # Get the image data
        import requests
        response = requests.get(artwork_url)
        
        if response.status_code != 200:
            return {"error": f"Failed to download {art_type} image: HTTP {response.status_code}"}
        
        image_data = response.content
        
        # Handle file output
        if output_format == "file" or output_path:
            # Determine output path
            file_path = output_path
            if not file_path:
                file_path = f"{media.title}_{art_type}.jpg"
                
            # Save the file
            try:
                with open(file_path, 'wb') as f:
                    f.write(image_data)
                return {
                    "filename": file_path,
                    "type": art_type,
                    "path": os.path.abspath(file_path),
                    "versions_available": len(available_versions)
                }
            except Exception as e:
                return {"error": f"Failed to save image file: {str(e)}"}
        
        # Handle base64 output (default)
        if output_format == "base64":
            import base64
            b64_data = base64.b64encode(image_data).decode('utf-8')
            return {
                "filename": f"{media.title}_{art_type}.jpg",
                "type": art_type,
                "base64": b64_data,
                "versions_available": len(available_versions)
            }
        
        return {"error": f"Invalid output format: {output_format}"}
        
    except Exception as e:
        return {"error": f"Error getting {art_type} artwork: {str(e)}"}

@mcp.tool()
async def set_media_artwork(media_title: str, library_name: str = None,
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
                results = library.search(title=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            results = plex.search(title=media_title)
        
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
async def list_available_artwork(media_title: str, library_name: str = None, art_type: str = "poster") -> str:
    """List all available artwork for a specific media item.
    
    Args:
        media_title: Title of the media to list artwork for
        library_name: Optional library name to limit search to
        art_type: Type of artwork to list (poster, background/art, logo)
    """
    try:
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
            return f"Invalid art type: {art_type}. Supported types: {', '.join(art_methods.keys())}"
        
        plex = connect_to_plex()
        
        # Search for the media
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(title=media_title)
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            results = plex.search(title=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."
        
        media = results[0]
        
        # Check if the object supports this art type
        art_method = art_methods.get(art_type)
        if not hasattr(media, art_method):
            return f"This media item doesn't support {art_type} artwork."
        
        # Get available artwork
        get_art_fn = getattr(media, art_method)
        artwork_list = get_art_fn()
        
        if not artwork_list:
            return f"No {art_type} artwork found for '{media.title}'."
        
        # Build response
        output = f"Available {art_type} artwork for '{media.title}':\n\n"
        
        for i, art in enumerate(artwork_list, 1):
            provider = getattr(art, 'provider', 'Unknown')
            preview_url = getattr(art, 'key', 'No URL available')
            selected = "(Selected)" if getattr(art, 'selected', False) else ""
            
            output += f"{i}. Provider: {provider} {selected}\n"
            output += f"   URL: {preview_url}\n\n"
            
        return output
    except Exception as e:
        return f"Error listing {art_type} artwork: {str(e)}"