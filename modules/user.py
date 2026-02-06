from modules import mcp, connect_to_plex
from plexapi.server import PlexServer # type: ignore
import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

try:
    from dotenv import load_dotenv # type: ignore
    # Load environment variables from .env file
    load_dotenv()
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
async def user_list_all_users() -> str:
    """List all users (owner, home users, and shared users) with their IDs and types.
    
    This is useful for getting the correct user IDs to filter watch history, especially for home users.
    """
    try:
        plex = connect_to_plex()
        account = plex.myPlexAccount()
        
        # Get all users from account
        all_users = account.users()
        
        result = {
            "owner": {
                "id": account.id,
                "username": account.username,
                "email": account.email,
                "title": account.title,
                "uuid": account.uuid,
                "type": "Owner",
                "home": getattr(account, 'home', True),
                "homeAdmin": getattr(account, 'homeAdmin', True)
            },
            "users": []
        }
        
        # Process all users
        for user in all_users:
            user_data = {
                "id": user.id,
                "title": user.title if hasattr(user, 'title') else user.username,
                "username": user.username if hasattr(user, 'username') else "",
                "email": user.email if hasattr(user, 'email') else "",
                "uuid": user.uuid if hasattr(user, 'uuid') else "",
                "thumb": user.thumb if hasattr(user, 'thumb') else "",
                # User type flags
                "home": getattr(user, 'home', False),
                "guest": getattr(user, 'guest', False),
                "restricted": getattr(user, 'restricted', False),
                "admin": getattr(user, 'admin', False),
                "protected": getattr(user, 'protected', False)
            }
            
            # Classify user type
            if getattr(user, 'home', False):
                if getattr(user, 'restricted', False):
                    user_data["type"] = "Home User (Managed)"
                else:
                    user_data["type"] = "Home User"
            else:
                user_data["type"] = "Shared User"
            
            result["users"].append(user_data)
        
        result["total_users"] = len(result["users"])
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error listing users: {str(e)}"})


@mcp.tool()
async def user_get_info(username: str = None) -> str:
    """Get detailed information about a specific Plex user.
    
    Args:
        username: Optional. Name of the user to get information for. Defaults to the authenticated owner.
    """
    try:
        plex = connect_to_plex()
        
        # Get account associated with the token
        account = plex.myPlexAccount()
        
        # Check if the username is the owner or if no username provided (default to owner)
        if username is None or username.lower() == account.username.lower():
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
async def user_get_on_deck(username: str = None) -> str:
    """Get on deck (in progress) media for a specific user.
    
    Args:
        username: Name of the user to get on-deck items for
    """
    try:
        plex = connect_to_plex()
        
        # Try to switch to the user account to get their specific on-deck items
        account = plex.myPlexAccount()
        
        if username is None or username.lower() == account.username.lower():
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
async def user_get_watch_history(username: str = None, limit: int = 10, content_type: str = None, user_id: int = None) -> str:
    """Get recent watch history for a specific user.
    
    Args:
        username: Name of the user to get watch history for (ignored if user_id is provided)
        limit: Maximum number of recently watched items to show
        content_type: Optional filter for content type (movie, show, episode, etc)
        user_id: Optional user ID to filter by (takes precedence over username). Use user_list_all_users to get IDs.
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
        
        # Determine which account ID to use
        target_account_id = None
        target_username = username
        is_owner = False
        
        if user_id is not None:
            # User ID provided directly
            target_account_id = user_id
            # Check if this is the owner
            if user_id == account.id:
                is_owner = True
                target_username = account.username
                # IMPORTANT: Owner's history uses accountID=1, not their real account ID
                target_account_id = 1
            else:
                # Try to find username for display purposes
                for user in account.users():
                    if user.id == user_id:
                        target_username = user.title if hasattr(user, 'title') else user.username
                        break
        elif username and username.lower() != account.username.lower():
            # Username provided (and not owner), need to look up the user
            target_user = None
            for user in account.users():
                if user.username.lower() == username.lower() or (hasattr(user, 'title') and user.title.lower() == username.lower()):
                    target_user = user
                    break
            
            if not target_user:
                return json.dumps({"error": f"User '{username}' not found."})
            
            target_account_id = target_user.id
        else:
            # Username is None (implying owner) OR username matches owner
            is_owner = True
            target_username = account.username
            # IMPORTANT: Owner's history uses accountID=1, not their real account ID
            target_account_id = 1
        
        while len(filtered_items) < limit and attempt < max_attempts:
            attempt += 1
            
            # Get history based on account ID
            if target_account_id is None:
                # Should not happen, but fallback to unfiltered
                history_items = plex.history(maxresults=current_search_limit)
            else:
                # Specific user, filter by account ID
                history_items = plex.history(maxresults=current_search_limit, accountID=target_account_id)
            
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
            message = f"No watch history found for user '{target_username}'"
            if content_type:
                message += f" with content type '{content_type}'"
            return json.dumps({"message": message})
        
        # Format the results
        result = {
            "username": target_username,
            "user_id": target_account_id,
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

@mcp.tool()
async def user_get_statistics(time_period: str = "last_24_hours", username: str = None) -> str:
    """Get statistics about user watch activity over different time periods.
    
    Args:
        time_period: Time period for statistics - options: "last_24_hours", "last_7_days", "last_30_days", "last_90_days", "last_year", "all_time"
        username: Optional. Filter statistics for a specific user. If not provided, returns statistics for all users.
    """
    try:
        plex = connect_to_plex()
        base_url = plex._baseurl
        token = plex._token
        
        # Get the current epoch time
        current_time = int(time.time())
        
        # Map time_period to Plex API parameters
        time_mapping = {
            "last_24_hours": {"timespan": 4, "at": current_time - 24*60*60},
            "last_7_days": {"timespan": 3, "at": current_time - 7*24*60*60},
            "last_30_days": {"timespan": 2, "at": current_time - 30*24*60*60},
            "last_90_days": {"timespan": 2, "at": current_time - 90*24*60*60},
            "last_year": {"timespan": 1, "at": current_time - 365*24*60*60},
            "all_time": {"timespan": 1, "at": 0}
        }
        
        if time_period not in time_mapping:
            return json.dumps({"error": f"Invalid time period. Choose from: {', '.join(time_mapping.keys())}"})
        
        # Build the statistics URL
        params = time_mapping[time_period]
        stats_url = f"{base_url}/statistics/media?timespan={params['timespan']}&at>={params['at']}"
        
        # Add Plex headers
        headers = {
            'X-Plex-Token': token,
            'Accept': 'application/json'
        }
        
        # Make the request to get statistics
        response = requests.get(stats_url, headers=headers)
        if response.status_code != 200:
            return json.dumps({"error": f"Failed to fetch statistics: HTTP {response.status_code}"})
        
        data = response.json()
        
        # Get data from response
        container = data.get('MediaContainer', {})
        device_list = container.get('Device', [])
        account_list = container.get('Account', [])
        stats_list = container.get('StatisticsMedia', [])
        
        # Create lookup dictionaries for accounts and devices
        account_lookup: Dict[int, Dict[str, Any]] = {}
        for account in account_list:
            account_lookup[account.get('id')] = {
                'name': account.get('name'),
                'key': account.get('key'),
                'thumb': account.get('thumb')
            }
        
        device_lookup: Dict[int, Dict[str, Any]] = {}
        for device in device_list:
            device_lookup[device.get('id')] = {
                'name': device.get('name'),
                'platform': device.get('platform'),
                'clientIdentifier': device.get('clientIdentifier')
            }
        
        # Filter by username if specified
        target_account_id = None
        if username:
            # Get the account ID for the specified username
            account = plex.myPlexAccount()
            
            # Check if the username matches the owner
            if username.lower() == account.username.lower():
                # Find the owner's account ID in the account list
                for acc in account_list:
                    if acc.get('name').lower() == username.lower():
                        target_account_id = acc.get('id')
                        break
            else:
                # Check shared users
                for user in account.users():
                    if user.username.lower() == username.lower() or (hasattr(user, 'title') and user.title.lower() == username.lower()):
                        # Find this user's account ID in the account list
                        for acc in account_list:
                            if acc.get('name').lower() == user.username.lower():
                                target_account_id = acc.get('id')
                                break
                        break
            
            if target_account_id is None:
                return json.dumps({"error": f"User '{username}' not found in the statistics data."})
        
        # Process the statistics data
        user_stats: Dict[int, Dict[str, Any]] = {}
        
        # Media type mapping
        media_type_map = {
            1: "movie", 
            4: "episode", 
            10: "track",
            100: "photo"
        }
        
        for stat in stats_list:
            account_id = stat.get('accountID')
            
            # Skip if we're filtering by user and this isn't the target user
            if target_account_id is not None and account_id != target_account_id:
                continue
                
            device_id = stat.get('deviceID')
            duration = stat.get('duration', 0)  # Duration in seconds
            count = stat.get('count', 0)  # Number of items played
            metadata_type = stat.get('metadataType', 0)
            media_type = media_type_map.get(metadata_type, f"unknown-{metadata_type}")
            
            # Initialize user stats if not already present
            if account_id not in user_stats:
                account_info = account_lookup.get(account_id, {'name': f"Unknown User {account_id}"})
                user_stats[account_id] = {
                    'user': account_info.get('name'),
                    'user_thumb': account_info.get('thumb'),
                    'total_duration': 0,
                    'total_plays': 0,
                    'media_types': {},
                    'devices': {}
                }
            
            # Update total duration and play count
            user_stats[account_id]['total_duration'] += duration
            user_stats[account_id]['total_plays'] += count
            
            # Update media type stats
            if media_type not in user_stats[account_id]['media_types']:
                user_stats[account_id]['media_types'][media_type] = {
                    'duration': 0,
                    'count': 0
                }
            user_stats[account_id]['media_types'][media_type]['duration'] += duration
            user_stats[account_id]['media_types'][media_type]['count'] += count
            
            # Update device stats
            if device_id is not None:
                device_info = device_lookup.get(device_id, {'name': f"Unknown Device {device_id}", 'platform': 'unknown'})
                device_name = device_info.get('name')
                
                if device_name not in user_stats[account_id]['devices']:
                    user_stats[account_id]['devices'][device_name] = {
                        'platform': device_info.get('platform'),
                        'duration': 0,
                        'count': 0
                    }
                user_stats[account_id]['devices'][device_name]['duration'] += duration
                user_stats[account_id]['devices'][device_name]['count'] += count
        
        # Format duration for better readability in each stat entry
        for account_id, stats in user_stats.items():
            # Format total duration
            hours, remainder = divmod(stats['total_duration'], 3600)
            minutes, seconds = divmod(remainder, 60)
            stats['formatted_duration'] = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            
            # Format media type durations
            for media_type, media_stats in stats['media_types'].items():
                hours, remainder = divmod(media_stats['duration'], 3600)
                minutes, seconds = divmod(remainder, 60)
                media_stats['formatted_duration'] = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            
            # Format device durations
            for device_name, device_stats in stats['devices'].items():
                hours, remainder = divmod(device_stats['duration'], 3600)
                minutes, seconds = divmod(remainder, 60)
                device_stats['formatted_duration'] = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        
        # Sort users by total duration (descending)
        sorted_users = sorted(
            user_stats.values(), 
            key=lambda x: x['total_duration'], 
            reverse=True
        )
        
        # Format the final result
        result = {
            "time_period": time_period,
            "user_filter": username,
            "total_users": len(sorted_users),
            "stats_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "users": sorted_users
        }
        
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Error getting user statistics: {str(e)}"})