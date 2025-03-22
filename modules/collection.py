from plexapi.collection import Collection # type: ignore
from typing import List, Dict, Any
from modules import mcp, connect_to_plex
import os

@mcp.tool()
async def list_collections(library_name: str = None) -> str:
    """List all collections on the Plex server or in a specific library.
    
    Args:
        library_name: Optional name of the library to list collections from
    """
    try:
        plex = connect_to_plex()
        
        if library_name and library_name != "null":
            try:
                library = plex.library.section(library_name)
                collections = library.collections()
            except NotFound:
                return f"Library '{library_name}' not found."
        else:
            # Get collections from all libraries
            collections = []
            for section in plex.library.sections():
                if hasattr(section, 'collections'):
                    collections.extend(section.collections())
        
        if not collections:
            return "No collections found."
        
        result = f"Collections ({len(collections)}):\n"
        
        for collection in collections:
            title = getattr(collection, 'title', 'Unknown Title')
            item_count = getattr(collection, 'childCount', 0)
            
            # Get the library this collection belongs to
            section_title = getattr(collection, 'librarySectionTitle', 'Unknown Library')
            
            result += f"- {title} - {item_count} items [{section_title}]\n"
        
        return result
    except Exception as e:
        return f"Error listing collections: {str(e)}"

@mcp.tool()
async def create_collection(collection_title: str, library_name: str, 
                           item_titles: List[str]) -> str:
    """Create a new collection with specified items.
    
    Args:
        collection_title: Title for the new collection
        library_name: Name of the library to create the collection in
        item_titles: List of media titles to include in the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
            
        # Check if collection already exists
        existing_collections = library.collections()
        for collection in existing_collections:
            if collection.title.lower() == collection_title.lower():
                return f"A collection with the title '{collection_title}' already exists in library '{library_name}'. Please choose a different title or use 'add_to_collection' to add items to the existing collection."
        
        # Find the media items
        items = []
        not_found = []
        
        for item_title in item_titles:
            found = False
            
            # Search for the item in the library based on its type
            if library.type == 'show':
                # For TV Shows
                results = library.searchShows(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
                else:
                    # Try searching for episodes
                    results = library.searchEpisodes(title=item_title)
                    if results:
                        items.append(results[0])
                        found = True
            elif library.type == 'movie':
                # For Movies
                results = library.search(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
            elif library.type == 'artist':
                # For Music
                results = library.search(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
            
            if not found:
                not_found.append(item_title)
        
        if not items:
            return "No valid media items found for the collection."
        
        # Create the collection
        try:
            from plexapi.collection import Collection
            collection = Collection.create(plex, collection_title, library, items)
            
            # Report results
            result = f"Successfully created collection '{collection_title}' with {len(items)} items in library '{library_name}'."
            if not_found:
                result += f"\nThe following items were not found: {', '.join(not_found)}"
            return result
        except Exception as e:
            return f"Error creating collection: {str(e)}"
    except Exception as e:
        return f"Error creating collection: {str(e)}"

@mcp.tool()
async def add_to_collection(collection_title: str, library_name: str, 
                           item_titles: List[str]) -> str:
    """Add items to an existing collection.
    
    Args:
        collection_title: Title of the collection to add to
        library_name: Name of the library containing the collection
        item_titles: List of media titles to add to the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        # Find the collection
        collections = library.collections()
        target_collection = None
        
        for collection in collections:
            if collection.title.lower() == collection_title.lower():
                target_collection = collection
                break
        
        if not target_collection:
            return f"Collection '{collection_title}' not found in library '{library_name}'."
        
        # Find the media items
        items = []
        not_found = []
        
        for item_title in item_titles:
            found = False
            
            # Search for the item in the library
            if library.type == 'show':
                # Try to find episodes
                results = library.searchEpisodes(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
                else:
                    # Try to find shows
                    results = library.search(title=item_title)
                    if results:
                        items.append(results[0])
                        found = True
            else:
                # For movies, music, etc.
                results = library.search(title=item_title)
                if results:
                    items.append(results[0])
                    found = True
            
            if not found:
                not_found.append(item_title)
        
        if not items:
            return "No valid media items found to add to the collection."
        
        # Add items to the collection
        target_collection.addItems(items)
        
        result = f"Successfully added {len(items)} items to collection '{collection_title}'."
        if not_found:
            result += f"\nThe following items were not found: {', '.join(not_found)}"
        
        return result
    except Exception as e:
        return f"Error adding to collection: {str(e)}"

@mcp.tool()
async def remove_from_collection(collection_title: str, library_name: str, 
                                item_titles: List[str]) -> str:
    """Remove items from a collection.
    
    Args:
        collection_title: Title of the collection to remove from
        library_name: Name of the library containing the collection
        item_titles: List of media titles to remove from the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        # Find the collection
        collections = library.collections()
        target_collection = None
        
        for collection in collections:
            if collection.title.lower() == collection_title.lower():
                target_collection = collection
                break
        
        if not target_collection:
            return f"Collection '{collection_title}' not found in library '{library_name}'."
        
        # Get the items in the collection
        collection_items = target_collection.items()
        
        # Find and remove the specified items
        items_to_remove = []
        not_found = []
        
        for search_title in item_titles:
            found = False
            
            # Search for exact title matches first
            for item in collection_items:
                if getattr(item, 'title', '').lower() == search_title.lower():
                    items_to_remove.append(item)
                    found = True
                    break
            
            # If no exact match, try partial title matching
            if not found:
                for item in collection_items:
                    title = getattr(item, 'title', '')
                    if search_title.lower() in title.lower():
                        items_to_remove.append(item)
                        found = True
                        break
            
            if not found:
                not_found.append(search_title)
        
        if not items_to_remove:
            return f"No matching items found in collection '{collection_title}'."
        
        # Remove the items
        target_collection.removeItems(items_to_remove)
        
        result = f"Successfully removed {len(items_to_remove)} items from collection '{collection_title}'."
        if not_found:
            result += f"\nThe following items were not found: {', '.join(not_found)}"
        
        return result
    except Exception as e:
        return f"Error removing from collection: {str(e)}"

@mcp.tool()
async def delete_collection(collection_title: str, library_name: str) -> str:
    """Delete a collection.
    
    Args:
        collection_title: Title of the collection to delete
        library_name: Name of the library containing the collection
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return f"Library '{library_name}' not found."
        
        # Find the collection
        collections = library.collections()
        target_collection = None
        
        for collection in collections:
            if collection.title.lower() == collection_title.lower():
                target_collection = collection
                break
        
        if not target_collection:
            return f"Collection '{collection_title}' not found in library '{library_name}'."
        
        # Delete the collection
        target_collection.delete()
        
        return f"Successfully deleted collection '{collection_title}'."
    except Exception as e:
        return f"Error deleting collection: {str(e)}"

@mcp.tool()
async def edit_collection(
    collection_title: str, 
    library_name: str,
    new_title: str = None,
    new_sort_title: str = None,
    new_summary: str = None,
    new_content_rating: str = None,
    new_labels: List[str] = None,
    add_labels: List[str] = None,
    remove_labels: List[str] = None,
    poster_path: str = None,
    poster_url: str = None,
    background_path: str = None,
    background_url: str = None,
    new_advanced_settings: Dict[str, Any] = None
) -> str:
    """Comprehensively edit a collection's attributes.
    
    Args:
        collection_title: Title of the collection to edit
        library_name: Name of the library containing the collection
        new_title: New title for the collection
        new_sort_title: New sort title for the collection
        new_summary: New summary/description for the collection
        new_content_rating: New content rating (e.g., PG-13, R, etc.)
        new_labels: Set completely new labels (replaces existing)
        add_labels: Labels to add to existing ones
        remove_labels: Labels to remove from existing ones
        poster_path: Path to a new poster image file
        poster_url: URL to a new poster image
        background_path: Path to a new background/art image file
        background_url: URL to a new background/art image
        new_advanced_settings: Dictionary of advanced settings to apply
    """
    try:
        plex = connect_to_plex()
        
        # Find the library
        library = None
        for section in plex.library.sections():
            if section.title.lower() == library_name.lower():
                library = section
                break
        
        if not library:
            return f"Error: Library '{library_name}' not found."
        
        # Find the collection
        collection = None
        for c in library.collections():
            if c.title.lower() == collection_title.lower():
                collection = c
                break
        
        if not collection:
            return f"Error: Collection '{collection_title}' not found in library '{library_name}'."
        
        # Prepare edit parameters
        edit_kwargs = {}
        
        if new_title:
            edit_kwargs['title'] = new_title
        
        if new_sort_title:
            edit_kwargs['titleSort'] = new_sort_title
        
        if new_summary:
            edit_kwargs['summary'] = new_summary
        
        if new_content_rating:
            edit_kwargs['contentRating'] = new_content_rating
        
        # Apply the edits to fields that can be edited directly
        if edit_kwargs:
            collection.edit(**edit_kwargs)
        
        # Handle labels separately since they require special handling
        if new_labels is not None:
            # Replace all labels
            current_labels = collection.labels
            for label in current_labels:
                collection.removeLabel(label)
            for label in new_labels:
                collection.addLabel(label)
        else:
            # Add specified labels
            if add_labels:
                for label in add_labels:
                    collection.addLabel(label)
            
            # Remove specified labels
            if remove_labels:
                for label in remove_labels:
                    collection.removeLabel(label)
        
        # Handle poster upload if provided (either by path or URL)
        if poster_path and poster_url:
            return f"Error: Please provide either poster_path OR poster_url, not both."
        elif poster_path:
            if os.path.isfile(poster_path):
                collection.uploadPoster(filepath=poster_path)
            else:
                return f"Error: Poster file not found at '{poster_path}'"
        elif poster_url:
            collection.uploadPoster(url=poster_url)
        
        # Handle background/art upload if provided (either by path or URL)
        if background_path and background_url:
            return f"Error: Please provide either background_path OR background_url, not both."
        elif background_path:
            if os.path.isfile(background_path):
                collection.uploadArt(filepath=background_path)
            else:
                return f"Error: Background file not found at '{background_path}'"
        elif background_url:
            collection.uploadArt(url=background_url)
        
        # Handle advanced settings (these vary by media type and may require specific PlexAPI methods)
        if new_advanced_settings:
            for setting_name, setting_value in new_advanced_settings.items():
                # This is a placeholder - the actual implementation would depend on
                # which advanced settings are supported by PlexAPI for collections
                try:
                    setattr(collection, setting_name, setting_value)
                except Exception as setting_err:
                    return f"Error setting advanced property '{setting_name}': {str(setting_err)}"
        
        # Refresh to apply changes
        collection.reload()
        
        return f"Successfully updated collection '{collection_title}'."
    except Exception as e:
        return f"Error editing collection: {str(e)}"
