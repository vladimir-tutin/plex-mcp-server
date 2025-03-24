from modules import mcp, connect_to_plex
from plexapi.server import PlexServer # type: ignore
import os
import json

try:
    from dotenv import load_dotenv # type: ignore
    # Load environment variables from .env file
    load_dotenv()
    PLEX_USERNAME = os.environ.get("PLEX_USERNAME", None)
    print("Successfully loaded environment variables from .env file")
except ImportError:
    print("Warning: python-dotenv not installed. Environment variables won't be loaded from .env file.")
    print("Install with: pip install python-dotenv")

@mcp.tool()
async def user_search_users(search_term: str = None) -> str:
    """Search for users with names, usernames, or emails containing the search term, or list all users if no search term is provided.
    
    Args:
        search_term: Optional term to search for in user information
    """
    try:
        plex = connect_to_plex()
        
        # Get account associated with the token
        account = plex.myPlexAccount()
        
        # Get list of all friends (shared users)
        all_users = account.users()
        
        # Add the owner's account to be searched as well
        all_users.append(account)
        
        if search_term:
            # Search for users that match the search term
            found_users = []
            for user in all_users:
                username = user.username.lower() if hasattr(user, 'username') else ''
                email = user.email.lower() if hasattr(user, 'email') else ''
                title = user.title.lower() if hasattr(user, 'title') else ''
                
                if (search_term.lower() in username or 
                    search_term.lower() in email or 
                    search_term.lower() in title):
                    found_users.append(user)
            
            if not found_users:
                return json.dumps({"message": f"No users found matching '{search_term}'."})
            
            # Format the output for found users
            result = {
                "searchTerm": search_term,
                "usersFound": len(found_users),
                "users": []
            }
            
            for user in found_users:
                is_owner = (user.username == account.username)
                user_data = {
                    "role": "Owner" if is_owner else "Shared User",
                    "username": user.username,
                    "email": user.email if hasattr(user, 'email') else None,
                    "title": user.title if hasattr(user, 'title') else user.username
                }
                
                # Add servers this user has access to (for shared users)
                if not is_owner and hasattr(user, 'servers'):
                    sections = []
                    for server in user.servers:
                        if server.name == account.title or server.name == account.username:
                            for section in server.sections():
                                sections.append(section.title)
                    
                    user_data["libraries"] = sections if sections else []
                
                result["users"].append(user_data)
            
            return json.dumps(result)
        else:
            # List all users
            if not all_users:
                return json.dumps({"message": "No shared users found. Only your account has access to this Plex server."})
            
            # Format the output for all users
            result = {
                "totalUsers": len(all_users),
                "owner": {
                    "username": account.username,
                    "email": account.email,
                    "title": account.title
                },
                "sharedUsers": []
            }
            
            # Add all the shared users
            for user in all_users:
                if user.username != account.username:
                    result["sharedUsers"].append({
                        "username": user.username,
                        "email": user.email if hasattr(user, 'email') else None,
                        "title": user.title if hasattr(user, 'title') else user.username
                    })
            
            return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error searching users: {str(e)}"})

@mcp.tool()
async def user_get_info(username: str = PLEX_USERNAME) -> str:
    """Get detailed information about a specific Plex user.
    
    Args:
        username: Optional. Name of the user to get information for. Defaults to PLEX_USERNAME in .env
    """
    try:
        plex = connect_to_plex()
        
        # Get account associated with the token
        account = plex.myPlexAccount()
        
        # Check if the username is the owner
        if username == account.username:
            result = {
                "role": "Owner",
                "username": account.username,
                "email": account.email,
                "title": account.title,
                "uuid": account.uuid,
                "authToken": f"{account.authenticationToken[:5]}...{account.authenticationToken[-5:]} (truncated for security)",
                "subscription": {
                    "active": account.subscriptionActive
                }
            }
            
            if account.subscriptionActive:
                result["subscription"]["features"] = account.subscriptionFeatures
                
            result["joinedAt"] = str(account.joinedAt)
            
            return json.dumps(result)
        
        # Search for the user in the friends list
        target_user = None
        for user in account.users():
            if user.username == username:
                target_user = user
                break
        
        if not target_user:
            return json.dumps({"error": f"User '{username}' not found among shared users."})
        
        # Format the output
        result = {
            "role": "Shared User",
            "username": target_user.username,
            "email": target_user.email if hasattr(target_user, 'email') else None,
            "title": target_user.title if hasattr(target_user, 'title') else target_user.username,
            "id": target_user.id if hasattr(target_user, 'id') else None
        }
        
        # Add servers and sections this user has access to
        if hasattr(target_user, 'servers'):
            result["serverAccess"] = []
            for server in target_user.servers:
                if server.name == account.title or server.name == account.username:
                    server_data = {
                        "name": server.name,
                        "libraries": []
                    }
                    for section in server.sections():
                        server_data["libraries"].append(section.title)
                    result["serverAccess"].append(server_data)
        
        # Get user's devices if available
        if hasattr(target_user, 'devices') and callable(getattr(target_user, 'devices')):
            try:
                devices = target_user.devices()
                if devices:
                    result["devices"] = []
                    for device in devices:
                        device_data = {
                            "name": device.name,
                            "platform": device.platform
                        }
                        if hasattr(device, 'clientIdentifier'):
                            device_data["clientId"] = device.clientIdentifier
                        if hasattr(device, 'createdAt'):
                            device_data["createdAt"] = str(device.createdAt)
                        if hasattr(device, 'lastSeenAt'):
                            device_data["lastSeenAt"] = str(device.lastSeenAt)
                        result["devices"].append(device_data)
            except:
                result["devices"] = None
        
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error getting user info: {str(e)}"})

@mcp.tool()
async def user_get_on_deck(username: str = PLEX_USERNAME) -> str:
    """Get on deck (in progress) media for a specific user.
    
    Args:
        username: Name of the user to get on-deck items for
    """
    try:
        plex = connect_to_plex()
        
        # Try to switch to the user account to get their specific on-deck items
        if username.lower() == plex.myPlexAccount().username.lower():
            # This is the main account, use server directly
            on_deck_items = plex.library.onDeck()
        else:
            # For a different user, we need to get access to their account
            try:
                account = plex.myPlexAccount()
                
                # Find the user in the shared users
                target_user = None
                for user in account.users():
                    if user.username.lower() == username.lower() or user.title.lower() == username.lower():
                        target_user = user
                        break
                
                if not target_user:
                    return json.dumps({"error": f"User '{username}' not found."})
                
                # For a shared user, try to switch to that user and get their on-deck items
                # This requires admin privileges and may be limited by Plex server's capabilities
                user_token = target_user.get_token(plex.machineIdentifier)
                if not user_token:
                    return json.dumps({"error": f"Unable to access on-deck items for user '{username}'. Token not available."})
                
                user_plex = PlexServer(plex._baseurl, user_token)
                on_deck_items = user_plex.library.onDeck()
            except Exception as user_err:
                return json.dumps({"error": f"Error accessing user '{username}': {str(user_err)}"})
        
        if not on_deck_items:
            return json.dumps({"message": f"No on-deck items found for user '{username}'."})
        
        result = {
            "username": username,
            "count": len(on_deck_items),
            "items": []
        }
        
        for item in on_deck_items:
            media_type = getattr(item, 'type', 'unknown')
            title = getattr(item, 'title', 'Unknown Title')
            
            item_data = {
                "type": media_type,
                "title": title
            }
            
            if media_type == 'episode':
                item_data["show"] = getattr(item, 'grandparentTitle', 'Unknown Show')
                item_data["season"] = getattr(item, 'parentTitle', 'Unknown Season')
            else:
                item_data["year"] = getattr(item, 'year', '')
            
            # Add progress information
            if hasattr(item, 'viewOffset') and hasattr(item, 'duration'):
                progress_pct = (item.viewOffset / item.duration) * 100
                
                # Format as minutes:seconds
                total_mins = item.duration // 60000
                current_mins = item.viewOffset // 60000
                total_secs = (item.duration % 60000) // 1000
                current_secs = (item.viewOffset % 60000) // 1000
                
                # Set progress as a single percentage value
                item_data["progress"] = round(progress_pct, 1)
                
                # Add time info as separate fields
                item_data["current_time"] = f"{current_mins}:{current_secs:02d}"
                item_data["total_time"] = f"{total_mins}:{total_secs:02d}"
            
            result["items"].append(item_data)
        
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error getting on-deck items: {str(e)}"})
    
@mcp.tool()
async def user_get_watch_history(username: str = PLEX_USERNAME, limit: int = 10, content_type: str = None) -> str:
    """Get recent watch history for a specific user.
    
    Args:
        username: Name of the user to get watch history for
        limit: Maximum number of recently watched items to show
        content_type: Optional filter for content type (movie, show, episode, etc)
    """
    try:
        plex = connect_to_plex()
        account = plex.myPlexAccount()
        
        # Track items we've already seen to avoid duplicates when expanding search
        seen_item_ids = set()
        filtered_items = []
        current_search_limit = limit * 2  # Start with 2x the requested limit
        max_attempts = 4  # Maximum number of search expansions to prevent infinite loops
        attempt = 0
        
        while len(filtered_items) < limit and attempt < max_attempts:
            attempt += 1
            
            # For the main account owner
            if username.lower() == account.username.lower():
                history_items = plex.history(maxresults=current_search_limit)
            else:
                # For a different user, find them in shared users
                target_user = None
                for user in account.users():
                    if user.username.lower() == username.lower() or user.title.lower() == username.lower():
                        target_user = user
                        break
                
                if not target_user:
                    return json.dumps({"error": f"User '{username}' not found."})
                
                # For a shared user, use accountID to filter history
                history_items = plex.history(maxresults=current_search_limit, accountID=target_user.id)
            
            # Filter by content type and deduplicate
            for item in history_items:
                item_id = getattr(item, 'ratingKey', None)
                
                # Skip if we've already processed this item
                if item_id and item_id in seen_item_ids:
                    continue
                
                # Add to seen items
                if item_id:
                    seen_item_ids.add(item_id)
                
                # Apply content type filter if specified
                item_type = getattr(item, 'type', 'unknown')
                if content_type and item_type.lower() != content_type.lower():
                    continue
                
                filtered_items.append(item)
                
                # Stop if we've reached the limit
                if len(filtered_items) >= limit:
                    break
            
            # If we still need more items, double the search limit for next attempt
            if len(filtered_items) < limit and history_items:
                current_search_limit *= 2
            else:
                # Either we have enough items or there are no more to fetch
                break
        
        # If we couldn't find any matching items
        if not filtered_items:
            message = f"No watch history found for user '{username}'"
            if content_type:
                message += f" with content type '{content_type}'"
            return json.dumps({"message": message})
        
        # Format the results
        result = {
            "username": username,
            "count": len(filtered_items),
            "requestedLimit": limit,
            "contentType": content_type,
            "items": []
        }
        
        # Add only the requested limit number of items
        for item in filtered_items[:limit]:
            media_type = getattr(item, 'type', 'unknown')
            title = getattr(item, 'title', 'Unknown Title')
            
            item_data = {
                "type": media_type,
                "title": title,
                "ratingKey": getattr(item, 'ratingKey', None)
            }
            
            # Format based on media type
            if media_type == 'episode':
                item_data["show"] = getattr(item, 'grandparentTitle', 'Unknown Show')
                item_data["season"] = getattr(item, 'parentTitle', 'Unknown Season')
                item_data["episodeNumber"] = getattr(item, 'index', None)
                item_data["seasonNumber"] = getattr(item, 'parentIndex', None)
            else:
                item_data["year"] = getattr(item, 'year', '')
            
            # Add viewed date if available
            if hasattr(item, 'viewedAt') and item.viewedAt:
                item_data["viewedAt"] = item.viewedAt.strftime("%Y-%m-%d %H:%M")
            
            result["items"].append(item_data)
        
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error getting watch history: {str(e)}"})