from modules import mcp, connect_to_plex
from plexapi.server import PlexServer # type: ignore
import os

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
async def search_users(search_term: str = None) -> str:
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
                return f"No users found matching '{search_term}'."
            
            # Format the output for found users
            result = f"Users matching '{search_term}':\n\n"
            
            for user in found_users:
                is_owner = (user.username == account.username)
                result += f"=== {'Owner' if is_owner else 'Shared User'} ===\n"
                result += f"Username: {user.username}\n"
                result += f"Email: {user.email if hasattr(user, 'email') else 'N/A'}\n"
                result += f"Title: {user.title if hasattr(user, 'title') else user.username}\n"
                
                # Add servers this user has access to (for shared users)
                if not is_owner and hasattr(user, 'servers'):
                    sections = []
                    for server in user.servers:
                        if server.name == account.title or server.name == account.username:
                            for section in server.sections():
                                sections.append(section.title)
                    
                    if sections:
                        result += f"Has access to libraries: {', '.join(sections)}\n"
                    else:
                        result += "No specific library access information available\n"
                
                result += "\n"
            
            return result
        else:
            # List all users
            if not all_users:
                return "No shared users found. Only your account has access to this Plex server."
            
            # Format the output for all users
            result = "Users with access to your Plex server:\n\n"
            
            # First, add the owner's account
            result += "=== Owner ===\n"
            result += f"Username: {account.username}\n"
            result += f"Email: {account.email}\n"
            result += f"Title: {account.title}\n\n"
            
            # Then add all the shared users
            result += "=== Shared Users ===\n"
            for user in all_users:
                if user.username != account.username:
                    result += f"Username: {user.username}\n"
                    result += f"Email: {user.email if hasattr(user, 'email') else 'N/A'}\n"
                    result += f"Title: {user.title if hasattr(user, 'title') else user.username}\n\n"
            
            return result
    except Exception as e:
        return f"Error searching users: {str(e)}"

@mcp.tool()
async def get_user_info(username: str = PLEX_USERNAME) -> str:
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
            result = "=== Owner Account ===\n"
            result += f"Username: {account.username}\n"
            result += f"Email: {account.email}\n"
            result += f"Title: {account.title}\n"
            result += f"UUID: {account.uuid}\n"
            result += f"Authentication Token: {account.authenticationToken[:5]}...{account.authenticationToken[-5:]} (truncated for security)\n"
            result += f"Subscription: {'Active' if account.subscriptionActive else 'Inactive'}\n"
            if account.subscriptionActive:
                result += f"Subscription Features: {', '.join(account.subscriptionFeatures)}\n"
            result += f"Joined At: {account.joinedAt}\n"
            return result
        
        # Search for the user in the friends list
        target_user = None
        for user in account.users():
            if user.username == username:
                target_user = user
                break
        
        if not target_user:
            return f"User '{username}' not found among shared users."
        
        # Format the output
        result = "=== Shared User ===\n"
        result += f"Username: {target_user.username}\n"
        result += f"Email: {target_user.email if hasattr(target_user, 'email') else 'N/A'}\n"
        result += f"Title: {target_user.title if hasattr(target_user, 'title') else target_user.username}\n"
        result += f"ID: {target_user.id if hasattr(target_user, 'id') else 'N/A'}\n"
        
        # Add servers and sections this user has access to
        if hasattr(target_user, 'servers'):
            result += "\nServer Access:\n"
            for server in target_user.servers:
                if server.name == account.title or server.name == account.username:
                    result += f"Server: {server.name}\n"
                    result += "Libraries with access:\n"
                    for section in server.sections():
                        result += f"- {section.title}\n"
        
        # Get user's devices if available
        if hasattr(target_user, 'devices') and callable(getattr(target_user, 'devices')):
            try:
                devices = target_user.devices()
                if devices:
                    result += "\nDevices:\n"
                    for device in devices:
                        result += f"- {device.name} ({device.platform})\n"
                        if hasattr(device, 'clientIdentifier'):
                            result += f"  ID: {device.clientIdentifier}\n"
                        if hasattr(device, 'createdAt'):
                            result += f"  Created At: {device.createdAt}\n"
                        if hasattr(device, 'lastSeenAt'):
                            result += f"  Last Seen: {device.lastSeenAt}\n"
                        result += "\n"
            except:
                result += "\nDevice information unavailable\n"
        
        return result
    except Exception as e:
        return f"Error getting user info: {str(e)}"

@mcp.tool()
async def get_user_on_deck(username: str = PLEX_USERNAME) -> str:
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
                    return f"User '{username}' not found."
                
                # For a shared user, try to switch to that user and get their on-deck items
                # This requires admin privileges and may be limited by Plex server's capabilities
                user_token = target_user.get_token(plex.machineIdentifier)
                if not user_token:
                    return f"Unable to access on-deck items for user '{username}'. Token not available."
                
                user_plex = PlexServer(plex._baseurl, user_token)
                on_deck_items = user_plex.library.onDeck()
            except Exception as user_err:
                return f"Error accessing user '{username}': {str(user_err)}"
        
        if not on_deck_items:
            return f"No on-deck items found for user '{username}'."
        
        result = f"On deck for {username} ({len(on_deck_items)} items):\n"
        
        for item in on_deck_items:
            media_type = getattr(item, 'type', 'unknown')
            title = getattr(item, 'title', 'Unknown Title')
            
            if media_type == 'episode':
                show = getattr(item, 'grandparentTitle', 'Unknown Show')
                season = getattr(item, 'parentTitle', 'Unknown Season')
                result += f"- {show} - {season} - {title}"
            else:
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                result += f"- {title}{year_str} [{media_type}]"
            
            # Add progress information
            if hasattr(item, 'viewOffset') and hasattr(item, 'duration'):
                progress_pct = (item.viewOffset / item.duration) * 100
                
                # Format as minutes:seconds
                total_mins = item.duration // 60000
                current_mins = item.viewOffset // 60000
                total_secs = (item.duration % 60000) // 1000
                current_secs = (item.viewOffset % 60000) // 1000
                
                result += f" - {current_mins:02d}:{current_secs:02d}/{total_mins:02d}:{total_secs:02d} ({progress_pct:.1f}%)"
            
            result += "\n"
        
        return result
    except Exception as e:
        return f"Error getting on-deck items: {str(e)}"
    
@mcp.tool()
async def get_user_watch_history(username: str = PLEX_USERNAME, limit: int = 10) -> str:
    """Get recent watch history for a specific user.
    
    Args:
        username: Name of the user to get watch history for
        limit: Maximum number of recently watched items to show
    """
    try:
        plex = connect_to_plex()
        
        # For the main account owner
        if username.lower() == plex.myPlexAccount().username.lower():
            history_items = plex.history(maxresults=limit)
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
                    return f"User '{username}' not found."
                
                # For a shared user, use accountID to filter history
                history_items = plex.history(maxresults=limit, accountID=target_user.id)
            except Exception as user_err:
                return f"Error accessing history for user '{username}': {str(user_err)}"
        
        if not history_items:
            return f"No watch history found for user '{username}'."
        
        result = f"Recent watch history for {username} ({len(history_items)} items):\n"
        
        for item in history_items:
            media_type = getattr(item, 'type', 'unknown')
            title = getattr(item, 'title', 'Unknown Title')
            
            # Format based on media type
            if media_type == 'episode':
                show = getattr(item, 'grandparentTitle', 'Unknown Show')
                season = getattr(item, 'parentTitle', 'Unknown Season')
                result += f"- {show} - {season} - {title}"
            else:
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                result += f"- {title}{year_str} [{media_type}]"
            
            # Add viewed date if available
            if hasattr(item, 'viewedAt') and item.viewedAt:
                viewed_at = item.viewedAt.strftime("%Y-%m-%d %H:%M")
                result += f" (Viewed: {viewed_at})"
            
            result += "\n"
        
        return result
    except Exception as e:
        return f"Error getting watch history: {str(e)}"