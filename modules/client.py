"""
Client-related functions for Plex Media Server.
Provides tools to connect to clients and control media playback.
"""
import time
from typing import List, Dict, Optional, Union, Any

from modules import mcp, connect_to_plex
from plexapi.exceptions import NotFound, Unauthorized

@mcp.tool()
async def list_clients(include_details: bool = True) -> Union[List[str], List[Dict[str, Any]]]:
    """List all available Plex clients connected to the server.
    
    Args:
        include_details: Whether to include detailed information about each client
    
    Returns:
        List of client names or detailed info dictionaries
    """
    try:
        plex = connect_to_plex()
        clients = plex.clients()
        
        # Also get session clients which may not appear in clients()
        sessions = plex.sessions()
        session_clients = []
        
        # Extract clients from sessions
        for session in sessions:
            if hasattr(session, 'player') and session.player:
                session_clients.append(session.player)
        
        # Combine both client lists, avoiding duplicates
        all_clients = clients.copy()
        client_ids = {client.machineIdentifier for client in clients}
        
        for client in session_clients:
            if hasattr(client, 'machineIdentifier') and client.machineIdentifier not in client_ids:
                all_clients.append(client)
                client_ids.add(client.machineIdentifier)
        
        if not all_clients:
            return "No clients currently connected to your Plex server."
        
        if include_details:
            result = []
            for client in all_clients:
                result.append({
                    "name": client.title,
                    "device": getattr(client, 'device', 'Unknown'),
                    "model": getattr(client, "model", "Unknown"),
                    "product": getattr(client, 'product', 'Unknown'),
                    "version": getattr(client, 'version', 'Unknown'),
                    "platform": getattr(client, "platform", "Unknown"),
                    "state": getattr(client, "state", "Unknown"),
                    "machineIdentifier": getattr(client, 'machineIdentifier', 'Unknown'),
                    "address": getattr(client, "_baseurl", "Unknown") or getattr(client, "address", "Unknown"),
                    "protocolCapabilities": getattr(client, "protocolCapabilities", [])
                })
            return result
        else:
            return [client.title for client in all_clients]
            
    except Exception as e:
        return f"Error listing clients: {str(e)}"

@mcp.tool()
async def get_client_details(client_name: str) -> Dict[str, Any]:
    """Get detailed information about a specific Plex client.
    
    Args:
        client_name: Name of the client to get details for
    
    Returns:
        Dictionary containing client details
    """
    try:
        plex = connect_to_plex()
        
        # Get regular clients
        regular_clients = plex.clients()
        
        # Also get clients from sessions
        sessions = plex.sessions()
        session_clients = []
        
        # Extract clients from sessions
        for session in sessions:
            if hasattr(session, 'player') and session.player:
                session_clients.append(session.player)
        
        # Try to find the client first in regular clients
        client = None
        try:
            client = plex.client(client_name)
        except NotFound:
            # Try to find a client with a matching name in regular clients
            matching_clients = [c for c in regular_clients if client_name.lower() in c.title.lower()]
            if matching_clients:
                client = matching_clients[0]
            else:
                # Try to find in session clients
                matching_session_clients = [c for c in session_clients if 
                                           hasattr(c, 'title') and client_name.lower() in c.title.lower()]
                if matching_session_clients:
                    client = matching_session_clients[0]
                else:
                    return f"No client found matching '{client_name}'"
            
        return {
            "name": client.title,
            "device": getattr(client, 'device', 'Unknown'),
            "deviceClass": getattr(client, "deviceClass", "Unknown"),
            "model": getattr(client, "model", "Unknown"),
            "product": getattr(client, 'product', 'Unknown'),
            "version": getattr(client, 'version', 'Unknown'),
            "platform": getattr(client, "platform", "Unknown"),
            "platformVersion": getattr(client, "platformVersion", "Unknown"),
            "state": getattr(client, "state", "Unknown"),
            "machineIdentifier": getattr(client, 'machineIdentifier', 'Unknown'),
            "protocolCapabilities": getattr(client, "protocolCapabilities", []),
            "address": getattr(client, "_baseurl", "Unknown") or getattr(client, "address", "Unknown"),
            "local": getattr(client, "local", "Unknown"),
            "protocol": getattr(client, "protocol", "plex"),
            "protocolVersion": getattr(client, "protocolVersion", "Unknown"),
            "vendor": getattr(client, "vendor", "Unknown"),
        }
            
    except Exception as e:
        return f"Error getting client details: {str(e)}"

@mcp.tool()
async def get_client_timelines(client_name: str) -> Dict[str, Any]:
    """Get the current timeline information for a specific Plex client.
    
    Args:
        client_name: Name of the client to get timeline for
    
    Returns:
        Timeline information for the client
    """
    try:
        plex = connect_to_plex()
        
        # Get regular clients
        regular_clients = plex.clients()
        
        # Also get clients from sessions
        sessions = plex.sessions()
        session_clients = []
        
        # Extract clients from sessions
        for session in sessions:
            if hasattr(session, 'player') and session.player:
                session_clients.append(session.player)
        
        # Try to find the client first in regular clients
        client = None
        try:
            client = plex.client(client_name)
        except NotFound:
            # Try to find a client with a matching name in regular clients
            matching_clients = [c for c in regular_clients if client_name.lower() in c.title.lower()]
            if matching_clients:
                client = matching_clients[0]
            else:
                # Try to find in session clients
                matching_session_clients = [c for c in session_clients if 
                                           hasattr(c, 'title') and client_name.lower() in c.title.lower()]
                if matching_session_clients:
                    client = matching_session_clients[0]
                else:
                    return f"No client found matching '{client_name}'"
            
        # Some clients may not always respond to timeline requests
        try:
            timeline = client.timeline
            
            # If timeline is None, the client might not be actively playing anything
            if timeline is None:
                # Check if this client has an active session
                for session in sessions:
                    if (hasattr(session, 'player') and session.player and 
                       hasattr(session.player, 'machineIdentifier') and 
                       hasattr(client, 'machineIdentifier') and
                       session.player.machineIdentifier == client.machineIdentifier):
                        # Use session information instead
                        return {
                            "state": session.player.state if hasattr(session.player, 'state') else "Unknown",
                            "time": session.viewOffset if hasattr(session, 'viewOffset') else 0,
                            "duration": session.duration if hasattr(session, 'duration') else 0,
                            "progress": round((session.viewOffset / session.duration * 100) if hasattr(session, 'viewOffset') and 
                                               hasattr(session, 'duration') and session.duration else 0, 2),
                            "title": session.title if hasattr(session, 'title') else "Unknown",
                            "type": session.type if hasattr(session, 'type') else "Unknown",
                        }
                
                return f"Client '{client.title}' is not currently playing any media."
                
            # Process timeline data
            return {
                "type": timeline.type,
                "state": timeline.state,
                "time": timeline.time,
                "duration": timeline.duration,
                "progress": round((timeline.time / timeline.duration * 100) if timeline.duration else 0, 2),
                "key": getattr(timeline, "key", None),
                "ratingKey": getattr(timeline, "ratingKey", None),
                "playQueueItemID": getattr(timeline, "playQueueItemID", None),
                "playbackRate": getattr(timeline, "playbackRate", 1),
                "shuffled": getattr(timeline, "shuffled", False),
                "repeated": getattr(timeline, "repeated", 0),
                "muted": getattr(timeline, "muted", False),
                "volume": getattr(timeline, "volume", None),
                "title": getattr(timeline, "title", None),
                "guid": getattr(timeline, "guid", None),
            }
        except:
            # Check if there's an active session for this client
            for session in sessions:
                if (hasattr(session, 'player') and session.player and 
                    hasattr(session.player, 'machineIdentifier') and 
                    hasattr(client, 'machineIdentifier') and
                    session.player.machineIdentifier == client.machineIdentifier):
                    # Use session information instead
                    return {
                        "state": session.player.state if hasattr(session.player, 'state') else "Unknown",
                        "time": session.viewOffset if hasattr(session, 'viewOffset') else 0,
                        "duration": session.duration if hasattr(session, 'duration') else 0,
                        "progress": round((session.viewOffset / session.duration * 100) if hasattr(session, 'viewOffset') and 
                                           hasattr(session, 'duration') and session.duration else 0, 2),
                        "title": session.title if hasattr(session, 'title') else "Unknown",
                        "type": session.type if hasattr(session, 'type') else "Unknown",
                    }
                    
            return f"Unable to get timeline information for client '{client.title}'. The client may not be responding to timeline requests."
            
    except Exception as e:
        return f"Error getting client timeline: {str(e)}"

@mcp.tool()
async def get_active_clients() -> List[Dict[str, Any]]:
    """Get all clients that are currently playing media.
    
    Returns:
        List of active clients with their playback status
    """
    try:
        plex = connect_to_plex()
        
        # Get active sessions first
        sessions = plex.sessions()
        active_clients = []
        
        if not sessions:
            # Try regular clients method as backup
            clients = plex.clients()
            
            if not clients:
                return "No clients currently connected to your Plex server."
                
            # Check each client for activity
            for client in clients:
                try:
                    # Check if the client is playing media
                    if client.isPlayingMedia(includePaused=True):
                        timeline = client.timeline
                        
                        active_clients.append({
                            "name": client.title,
                            "device": getattr(client, 'device', 'Unknown'),
                            "product": getattr(client, 'product', 'Unknown'),
                            "state": timeline.state if timeline else "Unknown",
                            "media_type": timeline.type if timeline else "Unknown",
                            "progress": round((timeline.time / timeline.duration * 100) if timeline and timeline.duration else 0, 2),
                            "time": timeline.time if timeline else 0,
                            "duration": timeline.duration if timeline else 0,
                            "title": getattr(timeline, "title", "Unknown") if timeline else "Unknown",
                        })
                except:
                    # Skip clients that don't respond to timeline requests
                    continue
        else:
            # Extract clients from active sessions
            for session in sessions:
                if hasattr(session, 'player') and session.player:
                    player = session.player
                    active_clients.append({
                        "name": player.title,
                        "device": getattr(player, 'device', 'Unknown'),
                        "product": getattr(player, 'product', 'Unknown'),
                        "state": getattr(player, 'state', 'Unknown'),
                        "media_type": getattr(session, 'type', 'Unknown'),
                        "progress": round((session.viewOffset / session.duration * 100) if hasattr(session, 'viewOffset') and 
                                          hasattr(session, 'duration') and session.duration else 0, 2),
                        "time": getattr(session, 'viewOffset', 0),
                        "duration": getattr(session, 'duration', 0),
                        "title": getattr(session, 'title', 'Unknown'),
                    })
        
        if not active_clients:
            return "No clients are currently playing media."
        
        return active_clients
            
    except Exception as e:
        return f"Error getting active clients: {str(e)}"

@mcp.tool()
async def start_playback(media_title: str, client_name: str = None, 
                        offset: int = 0, library_name: str = None, 
                        use_external_player: bool = False) -> str:
    """Start playback of a media item on a specified client or in the default video player.
    
    Args:
        media_title: Title of the media to play
        client_name: Name of the client to play on (optional)
        offset: Time offset in milliseconds
        library_name: Optional library name to limit search to
        use_external_player: If True, open in system's default video player instead of Plex
    
    Returns:
        Result message
    """
    try:
        plex = connect_to_plex()
        
        # Find the media
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
        
        # External player mode
        if use_external_player:
            if not hasattr(media, 'getStreamURL'):
                return f"Cannot play '{media.title}' in external player: Stream URL not available."
                
            try:
                stream_url = media.getStreamURL()
                import webbrowser
                webbrowser.open(stream_url)
                return f"Opening '{media.title}' in your default video player."
            except Exception as ex:
                return f"Error opening external player: {str(ex)}"
        
        # Client playback mode (requires client_name)
        if not client_name:
            return "Please specify a client name for Plex playback, or set use_external_player=True."
            
        # Find the client
        client = None
        
        # First try to find the client by exact name
        try:
            # Get all clients first
            all_clients = plex.clients()
            
            # Try to find by exact match
            exact_matches = [c for c in all_clients if c.title == client_name]
            if exact_matches:
                client = exact_matches[0]
            else:
                # Try partial match
                partial_matches = [c for c in all_clients if client_name.lower() in c.title.lower()]
                if partial_matches:
                    client = partial_matches[0]
        except Exception as e:
            pass
        
        # If not found in clients list, try sessions
        if not client:
            try:
                sessions = plex.sessions()
                
                # Try to find in active sessions
                for session in sessions:
                    if (hasattr(session, 'player') and 
                        hasattr(session.player, 'title') and 
                        client_name.lower() in session.player.title.lower()):
                        
                        if hasattr(session.player, 'machineIdentifier'):
                            try:
                                # Convert to a proper PlexClient
                                client = plex.client(session.player.machineIdentifier)
                                break
                            except Exception:
                                continue
            except Exception as e:
                pass
        
        if not client:
            # One last attempt to connect to client directly
            try:
                client = plex.client(client_name)
            except NotFound:
                return f"No client found matching '{client_name}'. Make sure the client is connected to your Plex server."
        
        # Play the media on the client
        client.playMedia(media, offset=offset)
        
        # Return success message with media details
        media_type = getattr(media, 'type', 'unknown')
        year = getattr(media, 'year', '')
        year_str = f" ({year})" if year else ""
        
        return f"Playing '{media.title}{year_str}' [{media_type}] on client '{client.title}'."
            
    except Exception as e:
        return f"Error starting playback: {str(e)}"

@mcp.tool()
async def control_playback(client_name: str, action: str, 
                         parameter: int = None, media_type: str = 'video') -> str:
    """Control playback on a specific client.
    
    Args:
        client_name: Name of the client to control
        action: Action to perform (play, pause, stop, skipNext, skipPrevious, 
                stepForward, stepBack, seekTo, setVolume, setRepeat, setShuffle)
        parameter: Optional parameter value for actions that require it
                  (seekTo position in ms, setVolume 0-100, setRepeat 0-2, setShuffle 0-1)
        media_type: Media type (video, music, photo)
    
    Returns:
        Result message
    """
    try:
        debug_info = []
        debug_info.append(f"Looking for client: {client_name}")
        
        plex = connect_to_plex()
        debug_info.append("Connected to Plex server")
        
        # First try to find the client by exact name
        client = None
        try:
            # Get all clients first
            all_clients = plex.clients()
            debug_info.append(f"Found {len(all_clients)} clients")
            
            for c in all_clients:
                debug_info.append(f"Client: {c.title}, Machine ID: {getattr(c, 'machineIdentifier', 'Unknown')}")
            
            # Try to find by exact match
            exact_matches = [c for c in all_clients if c.title == client_name]
            if exact_matches:
                client = exact_matches[0]
                debug_info.append(f"Found exact match: {client.title}")
            else:
                # Try partial match
                partial_matches = [c for c in all_clients if client_name.lower() in c.title.lower()]
                if partial_matches:
                    client = partial_matches[0]
                    debug_info.append(f"Found partial match: {client.title}")
        except Exception as e:
            debug_info.append(f"Error finding client in clients list: {str(e)}")
        
        # If not found in clients list, try sessions
        if not client:
            debug_info.append("Client not found in clients list, trying sessions")
            try:
                sessions = plex.sessions()
                debug_info.append(f"Found {len(sessions)} active sessions")
                
                for s in sessions:
                    if hasattr(s, 'player'):
                        debug_info.append(f"Session player: {s.player.title if hasattr(s.player, 'title') else 'Unknown'}")
                
                # Look for the client in active sessions
                for session in sessions:
                    if hasattr(session, 'player') and session.player:
                        player = session.player
                        if hasattr(player, 'title'):
                            debug_info.append(f"Checking player: {player.title}")
                            if client_name.lower() in player.title.lower():
                                debug_info.append(f"Found matching player: {player.title}")
                                # Try to get the machineIdentifier to create a proper client
                                if hasattr(player, 'machineIdentifier'):
                                    try:
                                        debug_info.append(f"Trying to get client by machineIdentifier: {player.machineIdentifier}")
                                        # This gets a proper PlexClient object
                                        client = plex.client(player.machineIdentifier)
                                        debug_info.append(f"Successfully got client: {client.title}")
                                        break
                                    except Exception as e:
                                        debug_info.append(f"Error getting client by machineIdentifier: {str(e)}")
                                        
                                        # Try direct initialization if all else fails
                                        try:
                                            from plexapi.client import PlexClient
                                            if hasattr(player, 'address'):
                                                debug_info.append(f"Trying direct client connection to {player.address}")
                                                baseurl = f"http://{player.address}:32500"
                                                client = PlexClient(baseurl=baseurl, token=plex._token)
                                                debug_info.append(f"Direct client connection succeeded: {client.title}")
                                                break
                                        except Exception as direct_e:
                                            debug_info.append(f"Direct client connection failed: {str(direct_e)}")
            except Exception as e:
                debug_info.append(f"Error finding client in sessions: {str(e)}")
        
        if not client:
            debug_info.append("Client not found, gathering available client information")
            clients_list = []
            try:
                for c in plex.clients():
                    clients_list.append(c.title)
            except Exception as e:
                debug_info.append(f"Error getting clients list: {str(e)}")
                
            sessions_list = []
            try:
                for s in plex.sessions():
                    if hasattr(s, 'player') and hasattr(s.player, 'title'):
                        sessions_list.append(s.player.title)
            except Exception as e:
                debug_info.append(f"Error getting sessions list: {str(e)}")
                
            # Try connecting to the SHIELD with the API approach
            # Try a direct HTTP request to control the device
            debug_info.append("Trying manual command approach")
            try:
                sessions = plex.sessions()
                for session in sessions:
                    if hasattr(session, 'player') and hasattr(session.player, 'title') and client_name.lower() in session.player.title.lower():
                        player = session.player
                        if hasattr(player, 'address'):
                            debug_info.append(f"Found player with address: {player.address}")
                            
                            # Try direct HTTP command
                            import requests
                            base_url = f"http://{player.address}:32500"
                            command_url = f"{base_url}/player/playback/{action}?type={media_type}&commandID=1"
                            debug_info.append(f"Sending command to: {command_url}")
                            
                            headers = {
                                'X-Plex-Token': plex._token
                            }
                            
                            response = requests.get(command_url, headers=headers, timeout=5)
                            debug_info.append(f"Response: {response.status_code} {response.text}")
                            
                            if response.status_code == 200:
                                return f"Successfully sent {action} command to player at {player.address}"
            except Exception as e:
                debug_info.append(f"Error with manual command: {str(e)}")
            
            debug_info_str = "\n".join(debug_info)
            return f"Could not find client '{client_name}'. Available clients: {', '.join(clients_list) if clients_list else 'None'}. Active sessions: {', '.join(sessions_list) if sessions_list else 'None'}\n\nDebug info:\n{debug_info_str}"
        
        # We have a valid PlexClient object now
        debug_info.append(f"Using client: {client.title}")
        
        # Validate media type
        if media_type not in ['video', 'music', 'photo']:
            return f"Invalid media type: {media_type}. Must be one of: video, music, photo."
        
        # Validate and perform action
        action = action.lower()
        debug_info.append(f"Performing action: {action}")
        
        # Direct action calls on the PlexClient object
        try:
            if action == 'play':
                client.play(mtype=media_type)
                action_desc = "Started playback"
            elif action == 'pause':
                client.pause(mtype=media_type)
                action_desc = "Paused playback"
            elif action == 'stop':
                client.stop(mtype=media_type)
                action_desc = "Stopped playback"
            elif action == 'skipnext':
                client.skipNext(mtype=media_type)
                action_desc = "Skipped to next item"
            elif action == 'skipprevious':
                client.skipPrevious(mtype=media_type)
                action_desc = "Skipped to previous item"
            elif action == 'stepforward':
                client.stepForward(mtype=media_type)
                action_desc = "Stepped forward"
            elif action == 'stepback':
                client.stepBack(mtype=media_type)
                action_desc = "Stepped back"
            elif action == 'seekto':
                if parameter is None:
                    return "The 'seekTo' action requires a position parameter (in milliseconds)."
                client.seekTo(parameter, mtype=media_type)
                action_desc = f"Seeked to position {parameter}ms"
            elif action == 'setvolume':
                if parameter is None:
                    return "The 'setVolume' action requires a volume parameter (0-100)."
                if not 0 <= parameter <= 100:
                    return f"Volume must be between 0 and 100, got {parameter}."
                client.setVolume(parameter, mtype=media_type)
                action_desc = f"Set volume to {parameter}%"
            elif action == 'setrepeat':
                if parameter is None:
                    return "The 'setRepeat' action requires a repeat mode parameter (0=off, 1=repeat one, 2=repeat all)."
                if not 0 <= parameter <= 2:
                    return f"Repeat mode must be between 0 and 2, got {parameter}."
                client.setRepeat(parameter, mtype=media_type)
                action_desc = f"Set repeat mode to {parameter} ({'off' if parameter == 0 else 'repeat one' if parameter == 1 else 'repeat all'})"
            elif action == 'setshuffle':
                if parameter is None:
                    return "The 'setShuffle' action requires a shuffle mode parameter (0=off, 1=on)."
                if not 0 <= parameter <= 1:
                    return f"Shuffle mode must be 0 or 1, got {parameter}."
                client.setShuffle(parameter, mtype=media_type)
                action_desc = f"Set shuffle mode to {parameter} ({'off' if parameter == 0 else 'on'})"
            else:
                return f"Invalid action: {action}. Valid actions are: play, pause, stop, skipNext, skipPrevious, stepForward, stepBack, seekTo, setVolume, setRepeat, setShuffle"
        except Exception as e:
            debug_info.append(f"Error executing action: {str(e)}")
            debug_info_str = "\n".join(debug_info)
            return f"Error executing {action} on client '{client.title}': {str(e)}\n\nDebug info:\n{debug_info_str}"
            
        debug_info.append(f"Action completed successfully: {action_desc}")
        return f"{action_desc} on client '{client.title}'."
            
    except Exception as e:
        return f"Error controlling playback: {str(e)}"

@mcp.tool()
async def navigate_client(client_name: str, action: str) -> str:
    """Send navigation commands to a client.
    
    Args:
        client_name: Name of the client to control
        action: Navigation action (moveUp, moveDown, moveLeft, moveRight, 
                select, back, home, contextMenu)
    
    Returns:
        Result message
    """
    try:
        plex = connect_to_plex()
        
        # Find the client (first in regular clients, then in session clients)
        client = None
        
        try:
            client = plex.client(client_name)
        except NotFound:
            # Try to find a client with a matching name in regular clients
            matching_clients = [c for c in plex.clients() if client_name.lower() in c.title.lower()]
            
            # Also check clients from active sessions if not found
            if not matching_clients:
                sessions = plex.sessions()
                for session in sessions:
                    if (hasattr(session, 'player') and session.player and 
                        hasattr(session.player, 'title') and client_name.lower() in session.player.title.lower()):
                        # Need to use clientIdentifier to get a proper PlexClient object
                        if hasattr(session.player, 'machineIdentifier'):
                            try:
                                client = plex.client(session.player.machineIdentifier)
                                matching_clients.append(client)
                                break
                            except:
                                pass
            
            if not matching_clients:
                return f"No client found matching '{client_name}'"
            client = matching_clients[0]
        
        # Validate and perform action
        action = action.lower()
        valid_actions = {
            'moveup': client.moveUp,
            'movedown': client.moveDown,
            'moveleft': client.moveLeft,
            'moveright': client.moveRight,
            'select': client.select,
            'back': client.goBack,
            'home': client.goToHome,
            'contextmenu': client.contextMenu,
            'pageup': client.pageUp,
            'pagedown': client.pageDown,
            'nextletter': client.nextLetter,
            'previousletter': client.previousLetter,
            'osd': client.toggleOSD,
        }
        
        if action not in valid_actions:
            return f"Invalid action: {action}. Valid actions are: {', '.join(valid_actions.keys())}"
        
        # Execute the action
        func = valid_actions[action]
        result = func()
        
        # Build response message
        action_descriptions = {
            'moveup': 'Moved up',
            'movedown': 'Moved down',
            'moveleft': 'Moved left',
            'moveright': 'Moved right',
            'select': 'Selected item',
            'back': 'Navigated back',
            'home': 'Navigated to home',
            'contextmenu': 'Opened context menu',
            'pageup': 'Page up',
            'pagedown': 'Page down',
            'nextletter': 'Next letter',
            'previousletter': 'Previous letter',
            'osd': 'Toggled on-screen display',
        }
        
        return f"{action_descriptions[action]} on client '{client.title}'."
            
    except Exception as e:
        return f"Error navigating client: {str(e)}"

@mcp.tool()
async def set_streams(client_name: str, audio_stream_id: str = None, 
                    subtitle_stream_id: str = None, video_stream_id: str = None) -> str:
    """Set the audio, subtitle, and video streams for the current playback.
    
    Args:
        client_name: Name of the client to control
        audio_stream_id: ID of the audio stream to select
        subtitle_stream_id: ID of the subtitle stream to select
        video_stream_id: ID of the video stream to select
    
    Returns:
        Result message
    """
    try:
        plex = connect_to_plex()
        
        # Find the client (first in regular clients, then in session clients)
        client = None
        
        try:
            client = plex.client(client_name)
        except NotFound:
            # Try to find a client with a matching name in regular clients
            matching_clients = [c for c in plex.clients() if client_name.lower() in c.title.lower()]
            
            # Also check clients from active sessions if not found
            if not matching_clients:
                sessions = plex.sessions()
                for session in sessions:
                    if (hasattr(session, 'player') and session.player and 
                        hasattr(session.player, 'title') and client_name.lower() in session.player.title.lower()):
                        # Need to use clientIdentifier to get a proper PlexClient object
                        if hasattr(session.player, 'machineIdentifier'):
                            try:
                                client = plex.client(session.player.machineIdentifier)
                                matching_clients.append(client)
                                break
                            except:
                                pass
            
            if not matching_clients:
                return f"No client found matching '{client_name}'"
            client = matching_clients[0]
        
        # Ensure at least one stream is being set
        if not audio_stream_id and not subtitle_stream_id and not video_stream_id:
            return "Please specify at least one stream ID to set (audio, subtitle, or video)."
        
        # Set the streams
        result = client.setStreams(
            audioStreamID=audio_stream_id,
            subtitleStreamID=subtitle_stream_id,
            videoStreamID=video_stream_id
        )
        
        # Build response message
        stream_changes = []
        if audio_stream_id:
            stream_changes.append(f"audio stream to {audio_stream_id}")
        if subtitle_stream_id:
            stream_changes.append(f"subtitle stream to {subtitle_stream_id}")
        if video_stream_id:
            stream_changes.append(f"video stream to {video_stream_id}")
        
        return f"Set {', '.join(stream_changes)} on client '{client.title}'."
            
    except Exception as e:
        return f"Error setting streams: {str(e)}" 