from plexapi.collection import Collection # type: ignore
from typing import List, Dict, Any
from modules import mcp, connect_to_plex
import os
from plexapi.exceptions import NotFound, BadRequest  # type: ignore
import json

@mcp.tool()
async def collection_list(library_name: str = None) -> str:
    """List all collections on the Plex server or in a specific library.
    
    Args:
        library_name: Optional name of the library to list collections from
    """
    try:
        plex = connect_to_plex()
        collections_data = []
        
        # If library_name is provided, only show collections from that library
        if library_name:
            try:
                library = plex.library.section(library_name)
                collections = library.collections()
                for collection in collections:
                    collection_info = {
                        "title": collection.title,
                        "summary": collection.summary,
                        "is_smart": collection.smart,
                        "ID": collection.ratingKey,
                        "items": collection.childCount
                    }
                    collections_data.append(collection_info)
                
                return json.dumps(collections_data, indent=4)
            except NotFound:
                return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
        
        # No library specified, get collections from all movie and show libraries
        movie_libraries = []
        show_libraries = []
        
        for section in plex.library.sections():
            if section.type == 'movie':
                movie_libraries.append(section)
            elif section.type == 'show':
                show_libraries.append(section)
        
        # Group collections by library
        libraries_collections = {}
        
        # Get movie collections
        for library in movie_libraries:
            lib_collections = []
            
            for collection in library.collections():
                collection_info = {
                    "title": collection.title,
                    "summary": collection.summary,
                    "is_smart": collection.smart,
                    "ID": collection.ratingKey,
                    "items": collection.childCount
                }
                lib_collections.append(collection_info)
            
            libraries_collections[library.title] = {
                "type": "movie",
                "collections_count": len(lib_collections),
                "collections": lib_collections
            }
        
        # Get TV show collections
        for library in show_libraries:
            lib_collections = []
            
            for collection in library.collections():
                collection_info = {
                    "title": collection.title,
                    "summary": collection.summary,
                    "is_smart": collection.smart,
                    "ID": collection.ratingKey,
                    "items": collection.childCount
                }
                lib_collections.append(collection_info)
            
            libraries_collections[library.title] = {
                "type": "show",
                "collections_count": len(lib_collections),
                "collections": lib_collections
            }
        
        return json.dumps(libraries_collections, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def collection_create(collection_title: str, library_name: str, item_titles: List[str] = None, item_ids: List[int] = None) -> str:
    """Create a new collection with specified items.
    
    Args:
        collection_title: Title for the new collection
        library_name: Name of the library to create the collection in
        item_titles: List of media titles to include in the collection (optional if item_ids is provided)
        item_ids: List of media IDs to include in the collection (optional if item_titles is provided)
    """
    try:
        plex = connect_to_plex()
        
        # Validate that at least one item source is provided
        if (not item_titles or len(item_titles) == 0) and (not item_ids or len(item_ids) == 0):
            return json.dumps({"error": "Either item_titles or item_ids must be provided"}, indent=4)
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
        
        # Check if collection already exists
        try:
            existing_collection = next((c for c in library.collections() if c.title.lower() == collection_title.lower()), None)
            if existing_collection:
                return json.dumps({"error": f"Collection '{collection_title}' already exists in library '{library_name}'"}, indent=4)
        except Exception:
            pass  # If we can't check existing collections, proceed anyway
        
        # Find items to add to the collection
        items = []
        not_found = []
        
        # If we have item IDs, try to add by ID first
        if item_ids and len(item_ids) > 0:
            for item_id in item_ids:
                try:
                    # Try to fetch the item by ID
                    item = plex.fetchItem(item_id)
                    if item:
                        items.append(item)
                    else:
                        not_found.append(str(item_id))
                except Exception as e:
                    not_found.append(str(item_id))
        
        # If we have item titles, search for them
        if item_titles and len(item_titles) > 0:
            for title in item_titles:
                # Search for the media item
                search_results = library.search(title=title)
                
                if search_results:
                    # Check for exact title match (case insensitive)
                    exact_matches = [item for item in search_results if item.title.lower() == title.lower()]
                    
                    if exact_matches:
                        items.append(exact_matches[0])
                    else:
                        # No exact match, collect possible matches
                        possible_matches = []
                        for item in search_results:
                            possible_matches.append({
                                "title": item.title,
                                "id": item.ratingKey,
                                "type": item.type,
                                "year": item.year if hasattr(item, 'year') and item.year else None
                            })
                        
                        not_found.append({
                            "title": title,
                            "possible_matches": possible_matches
                        })
                else:
                    not_found.append(title)
        
        # If we have possible matches but no items to add, return the possible matches
        if not items and any(isinstance(item, dict) for item in not_found):
            possible_matches_response = []
            for item in not_found:
                if isinstance(item, dict) and "possible_matches" in item:
                    for match in item["possible_matches"]:
                        if match not in possible_matches_response:
                            possible_matches_response.append(match)
            
            return json.dumps({"Multiple Possible Matches Use ID":possible_matches_response}, indent=4)
        
        if not items:
            return json.dumps({"error": "No matching media items found for the collection"}, indent=4)
        
        # Create the collection
        collection = library.createCollection(title=collection_title, items=items)
        
        return json.dumps({
            "created": True,
            "title": collection.title,
            "id": collection.ratingKey,
            "library": library_name,
            "items_added": len(items),
            "items_not_found": [item for item in not_found if not isinstance(item, dict)]
        }, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def collection_add_to(collection_title: str = None, collection_id: int = None, library_name: str = None, item_titles: List[str] = None, item_ids: List[int] = None) -> str:
    """Add items to an existing collection.
    
    Args:
        collection_title: Title of the collection to add to (optional if collection_id is provided)
        collection_id: ID of the collection to add to (optional if collection_title is provided)
        library_name: Name of the library containing the collection (required if using collection_title)
        item_titles: List of media titles to add to the collection (optional if item_ids is provided)
        item_ids: List of media IDs to add to the collection (optional if item_titles is provided)
    """
    try:
        plex = connect_to_plex()
        
        # Validate that at least one identifier is provided
        if not collection_id and not collection_title:
            return json.dumps({"error": "Either collection_id or collection_title must be provided"}, indent=4)
        
        # Validate that at least one item source is provided
        if (not item_titles or len(item_titles) == 0) and (not item_ids or len(item_ids) == 0):
            return json.dumps({"error": "Either item_titles or item_ids must be provided"}, indent=4)
        
        # Find the collection
        collection = None
        library = None
        
        # If collection_id is provided, use it to directly fetch the collection
        if collection_id:
            try:
                # Try fetching by ratingKey first
                try:
                    collection = plex.fetchItem(collection_id)
                except:
                    # If that fails, try finding by key in all libraries
                    collection = None
                    for section in plex.library.sections():
                        if section.type in ['movie', 'show']:
                            try:
                                for c in section.collections():
                                    if c.ratingKey == collection_id:
                                        collection = c
                                        library = section
                                        break
                                if collection:
                                    break
                            except:
                                continue
                
                if not collection:
                    return json.dumps({"error": f"Collection with ID '{collection_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching collection by ID: {str(e)}"}, indent=4)
        else:
            # If we're searching by title
            if not library_name:
                return json.dumps({"error": "Library name is required when adding items by collection title"}, indent=4)
            
            # Find the library
            try:
                library = plex.library.section(library_name)
            except NotFound:
                return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
            
            # Find matching collections
            matching_collections = [c for c in library.collections() if c.title.lower() == collection_title.lower()]
            
            if not matching_collections:
                return json.dumps({"error": f"Collection '{collection_title}' not found in library '{library_name}'"}, indent=4)
            
            # If multiple matching collections, return list of matches with IDs
            if len(matching_collections) > 1:
                matches = []
                for c in matching_collections:
                    matches.append({
                        "title": c.title,
                        "id": c.ratingKey,
                        "library": library_name,
                        "item_count": c.childCount if hasattr(c, 'childCount') else len(c.items())
                    })
                
                # Return as a direct array like playlist_list
                return json.dumps(matches, indent=4)
            
            collection = matching_collections[0]
        
        # Find items to add
        items_to_add = []
        not_found = []
        already_in_collection = []
        current_items = collection.items()
        current_item_ids = [item.ratingKey for item in current_items]
        
        # If we have item IDs, try to add by ID first
        if item_ids and len(item_ids) > 0:
            for item_id in item_ids:
                try:
                    # Try to fetch the item by ID
                    item = plex.fetchItem(item_id)
                    if item:
                        if item.ratingKey in current_item_ids:
                            already_in_collection.append(str(item_id))
                        else:
                            items_to_add.append(item)
                    else:
                        not_found.append(str(item_id))
                except Exception as e:
                    not_found.append(str(item_id))
        
        # If we have item titles, search for them with exact matching
        if item_titles and len(item_titles) > 0:
            if not library:
                # This could happen if we found the collection by ID
                # Try to determine which library the collection belongs to
                for section in plex.library.sections():
                    if section.type == 'movie' or section.type == 'show':
                        try:
                            for c in section.collections():
                                if c.ratingKey == collection.ratingKey:
                                    library = section
                                    break
                            if library:
                                break
                        except:
                            continue
                
                if not library:
                    return json.dumps({"error": "Could not determine which library to search in"}, indent=4)
            
            for title in item_titles:
                # Search for the media item with exact matching
                search_results = library.search(title=title)
                
                if search_results:
                    # Check for exact title match (case insensitive)
                    exact_matches = [item for item in search_results if item.title.lower() == title.lower()]
                    
                    if exact_matches:
                        item = exact_matches[0]
                        if item.ratingKey in current_item_ids:
                            already_in_collection.append(title)
                        else:
                            items_to_add.append(item)
                    else:
                        # No exact match, collect possible matches
                        possible_matches = []
                        for item in search_results:
                            possible_matches.append({
                                "title": item.title,
                                "id": item.ratingKey,
                                "type": item.type,
                                "year": item.year if hasattr(item, 'year') and item.year else None
                            })
                        
                        not_found.append({
                            "title": title,
                            "possible_matches": possible_matches
                        })
                else:
                    not_found.append(title)
        
        # If we have possible matches but no items to add, return the possible matches
        if not items_to_add and any(isinstance(item, dict) for item in not_found):
            possible_matches_response = []
            for item in not_found:
                if isinstance(item, dict) and "possible_matches" in item:
                    for match in item["possible_matches"]:
                        if match not in possible_matches_response:
                            possible_matches_response.append(match)
            
            return json.dumps(possible_matches_response, indent=4)
        
        # If no items to add and no possible matches
        if not items_to_add and not already_in_collection:
            return json.dumps({"error": "No matching media items found to add to the collection"}, indent=4)
        
        # Add items to the collection
        if items_to_add:
            collection.addItems(items_to_add)
        
        return json.dumps({
            "added": True,
            "title": collection.title,
            "items_added": [item.title for item in items_to_add],
            "items_already_in_collection": already_in_collection,
            "items_not_found": [item for item in not_found if not isinstance(item, dict)],
            "total_items": len(collection.items())
        }, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def collection_remove_from(collection_title: str = None, collection_id: int = None, library_name: str = None, item_titles: List[str] = None) -> str:
    """Remove items from a collection.
    
    Args:
        collection_title: Title of the collection to remove from (optional if collection_id is provided)
        collection_id: ID of the collection to remove from (optional if collection_title is provided)
        library_name: Name of the library containing the collection (required if using collection_title)
        item_titles: List of media titles to remove from the collection
    """
    try:
        plex = connect_to_plex()
        
        # Validate that at least one identifier is provided
        if not collection_id and not collection_title:
            return json.dumps({"error": "Either collection_id or collection_title must be provided"}, indent=4)
        
        if not item_titles or len(item_titles) == 0:
            return json.dumps({"error": "At least one item title must be provided to remove"}, indent=4)
        
        # Find the collection
        collection = None
        
        # If collection_id is provided, use it to directly fetch the collection
        if collection_id:
            try:
                # Try fetching by ratingKey first
                try:
                    collection = plex.fetchItem(collection_id)
                except:
                    # If that fails, try finding by key in all libraries
                    collection = None
                    for section in plex.library.sections():
                        if section.type in ['movie', 'show']:
                            try:
                                for c in section.collections():
                                    if c.ratingKey == collection_id:
                                        collection = c
                                        break
                                if collection:
                                    break
                            except:
                                continue
                
                if not collection:
                    return json.dumps({"error": f"Collection with ID '{collection_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching collection by ID: {str(e)}"}, indent=4)
        else:
            # If we get here, we're searching by title
            if not library_name:
                return json.dumps({"error": "Library name is required when removing items by collection title"}, indent=4)
            
            # Find the library
            try:
                library = plex.library.section(library_name)
            except NotFound:
                return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
            
            # Find matching collections
            matching_collections = [c for c in library.collections() if c.title.lower() == collection_title.lower()]
            
            if not matching_collections:
                return json.dumps({"error": f"Collection '{collection_title}' not found in library '{library_name}'"}, indent=4)
            
            # If multiple matching collections, return list of matches with IDs
            if len(matching_collections) > 1:
                matches = []
                for c in matching_collections:
                    matches.append({
                        "title": c.title,
                        "id": c.ratingKey,
                        "library": library_name,
                        "item_count": c.childCount if hasattr(c, 'childCount') else len(c.items())
                    })
                
                # Return as a direct array like playlist_list
                return json.dumps(matches, indent=4)
            
            collection = matching_collections[0]
        
        # Get current items in the collection
        collection_items = collection.items()
        
        # Find items to remove
        items_to_remove = []
        not_found = []
        
        for title in item_titles:
            found = False
            for item in collection_items:
                if item.title.lower() == title.lower():
                    items_to_remove.append(item)
                    found = True
                    break
            if not found:
                not_found.append(title)
        
        if not items_to_remove:
            # No items found to remove, return the current collection contents
            current_items = []
            for item in collection_items:
                current_items.append({
                    "title": item.title,
                    "type": item.type,
                    "id": item.ratingKey
                })
            
            return json.dumps({
                "error": "No matching items found in the collection to remove",
                "collection_title": collection.title,
                "collection_id": collection.ratingKey,
                "current_items": current_items
            }, indent=4)
        
        # Remove items from the collection
        collection.removeItems(items_to_remove)
        
        return json.dumps({
            "removed": True,
            "title": collection.title,
            "items_removed": [item.title for item in items_to_remove],
            "items_not_found": not_found,
            "remaining_items": len(collection.items())
        }, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def collection_delete(collection_title: str = None, collection_id: int = None, library_name: str = None) -> str:
    """Delete a collection.
    
    Args:
        collection_title: Title of the collection to delete (optional if collection_id is provided)
        collection_id: ID of the collection to delete (optional if collection_title is provided)
        library_name: Name of the library containing the collection (required if using collection_title)
    """
    try:
        plex = connect_to_plex()
        
        # Validate that at least one identifier is provided
        if not collection_id and not collection_title:
            return json.dumps({"error": "Either collection_id or collection_title must be provided"}, indent=4)
        
        # If collection_id is provided, use it to directly fetch the collection
        if collection_id:
            try:
                # Try fetching by ratingKey first
                try:
                    collection = plex.fetchItem(collection_id)
                except:
                    # If that fails, try finding by key in all libraries
                    collection = None
                    for section in plex.library.sections():
                        if section.type in ['movie', 'show']:
                            try:
                                for c in section.collections():
                                    if c.ratingKey == collection_id:
                                        collection = c
                                        break
                                if collection:
                                    break
                            except:
                                continue
                
                if not collection:
                    return json.dumps({"error": f"Collection with ID '{collection_id}' not found"}, indent=4)
                
                # Get the collection title to return in the message
                collection_title_to_return = collection.title
                
                # Delete the collection
                collection.delete()
                
                # Return a simple object with the result
                return json.dumps({
                    "deleted": True,
                    "title": collection_title_to_return
                }, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching collection by ID: {str(e)}"}, indent=4)
        
        # If we get here, we're searching by title
        if not library_name:
            return json.dumps({"error": "Library name is required when deleting by collection title"}, indent=4)
        
        # Find the library
        try:
            library = plex.library.section(library_name)
        except NotFound:
            return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
        
        # Find matching collections
        matching_collections = [c for c in library.collections() if c.title.lower() == collection_title.lower()]
        
        if not matching_collections:
            return json.dumps({"error": f"Collection '{collection_title}' not found in library '{library_name}'"}, indent=4)
        
        # If multiple matching collections, return list of matches with IDs
        if len(matching_collections) > 1:
            matches = []
            for c in matching_collections:
                matches.append({
                    "title": c.title,
                    "id": c.ratingKey,
                    "library": library_name,
                    "item_count": c.childCount if hasattr(c, 'childCount') else len(c.items())
                })
            
            # Return as a direct array like playlist_list
            return json.dumps(matches, indent=4)
        
        collection = matching_collections[0]
        collection_title_to_return = collection.title
        
        # Delete the collection
        collection.delete()
        
        # Return a simple object with the result
        return json.dumps({
            "deleted": True,
            "title": collection_title_to_return
        }, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

@mcp.tool()
async def collection_edit(collection_title: str = None, collection_id: int = None, library_name: str = None, 
                      new_title: str = None, new_sort_title: str = None,
                      new_summary: str = None, new_content_rating: str = None,
                      new_labels: List[str] = None, add_labels: List[str] = None,
                      remove_labels: List[str] = None,
                      poster_path: str = None, poster_url: str = None,
                      background_path: str = None, background_url: str = None,
                      new_advanced_settings: Dict[str, Any] = None) -> str:
    """Comprehensively edit a collection's attributes.
    
    Args:
        collection_title: Title of the collection to edit (optional if collection_id is provided)
        collection_id: ID of the collection to edit (optional if collection_title is provided)
        library_name: Name of the library containing the collection (required if using collection_title)
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
        
        # Validate that at least one identifier is provided
        if not collection_id and not collection_title:
            return json.dumps({"error": "Either collection_id or collection_title must be provided"}, indent=4)
        
        # Find the collection
        collection = None
        
        # If collection_id is provided, use it to directly fetch the collection
        if collection_id:
            try:
                # Try fetching by ratingKey first
                try:
                    collection = plex.fetchItem(collection_id)
                except:
                    # If that fails, try finding by key in all libraries
                    collection = None
                    for section in plex.library.sections():
                        if section.type in ['movie', 'show']:
                            try:
                                for c in section.collections():
                                    if c.ratingKey == collection_id:
                                        collection = c
                                        break
                                if collection:
                                    break
                            except:
                                continue
                
                if not collection:
                    return json.dumps({"error": f"Collection with ID '{collection_id}' not found"}, indent=4)
            except Exception as e:
                return json.dumps({"error": f"Error fetching collection by ID: {str(e)}"}, indent=4)
        else:
            # If we get here, we're searching by title
            if not library_name:
                return json.dumps({"error": "Library name is required when editing by collection title"}, indent=4)
            
            # Find the library
            try:
                library = plex.library.section(library_name)
            except NotFound:
                return json.dumps({"error": f"Library '{library_name}' not found"}, indent=4)
            
            # Find matching collections
            matching_collections = [c for c in library.collections() if c.title.lower() == collection_title.lower()]
            
            if not matching_collections:
                return json.dumps({"error": f"Collection '{collection_title}' not found in library '{library_name}'"}, indent=4)
            
            # If multiple matching collections, return list of matches with IDs
            if len(matching_collections) > 1:
                matches = []
                for c in matching_collections:
                    matches.append({
                        "title": c.title,
                        "id": c.ratingKey,
                        "library": library_name,
                        "item_count": c.childCount if hasattr(c, 'childCount') else len(c.items())
                    })
                
                # Return as a direct array like playlist_list
                return json.dumps(matches, indent=4)
            
            collection = matching_collections[0]
        
        # Track changes
        changes = []
        
        # Edit basic attributes
        edit_params = {}
        
        if new_title is not None and new_title != collection.title:
            edit_params['title'] = new_title
            changes.append(f"title to '{new_title}'")
        
        if new_sort_title is not None:
            current_sort = getattr(collection, 'titleSort', '')
            if new_sort_title != current_sort:
                edit_params['titleSort'] = new_sort_title
                changes.append(f"sort title to '{new_sort_title}'")
        
        if new_summary is not None:
            current_summary = getattr(collection, 'summary', '')
            if new_summary != current_summary:
                edit_params['summary'] = new_summary
                changes.append("summary")
        
        if new_content_rating is not None:
            current_rating = getattr(collection, 'contentRating', '')
            if new_content_rating != current_rating:
                edit_params['contentRating'] = new_content_rating
                changes.append(f"content rating to '{new_content_rating}'")
        
        # Apply the basic edits if any parameters were set
        if edit_params:
            collection.edit(**edit_params)
        
        # Handle labels
        current_labels = getattr(collection, 'labels', [])
        
        if new_labels is not None:
            # Replace all labels
            collection.removeLabel(current_labels)
            if new_labels:
                collection.addLabel(new_labels)
            changes.append("labels completely replaced")
        else:
            # Handle adding and removing individual labels
            if add_labels:
                for label in add_labels:
                    if label not in current_labels:
                        collection.addLabel(label)
                changes.append(f"added labels: {', '.join(add_labels)}")
            
            if remove_labels:
                for label in remove_labels:
                    if label in current_labels:
                        collection.removeLabel(label)
                changes.append(f"removed labels: {', '.join(remove_labels)}")
        
        # Handle artwork
        if poster_path:
            collection.uploadPoster(filepath=poster_path)
            changes.append("poster (from file)")
        elif poster_url:
            collection.uploadPoster(url=poster_url)
            changes.append("poster (from URL)")
        
        if background_path:
            collection.uploadArt(filepath=background_path)
            changes.append("background art (from file)")
        elif background_url:
            collection.uploadArt(url=background_url)
            changes.append("background art (from URL)")
        
        # Handle advanced settings
        if new_advanced_settings:
            for key, value in new_advanced_settings.items():
                try:
                    setattr(collection, key, value)
                    changes.append(f"advanced setting '{key}'")
                except Exception as setting_error:
                    return json.dumps({
                        "error": f"Error setting advanced parameter '{key}': {str(setting_error)}"
                    }, indent=4)
        
        if not changes:
            return json.dumps({"updated": False, "message": "No changes made to the collection"}, indent=4)
        
        # Get the collection title for the response (use new_title if it was changed)
        collection_title_to_return = new_title if new_title else collection.title
        
        return json.dumps({
            "updated": True,
            "title": collection_title_to_return,
            "changes": changes
        }, indent=4)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)
