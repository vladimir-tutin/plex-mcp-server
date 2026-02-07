"""
Client-related functions for Plex Media Server.
Provides tools to connect to clients and control media playback.
"""
import json
import time
from typing import List, Dict, Optional, Union, Any, Tuple

from modules import mcp, connect_to_plex
from plexapi.exceptions import NotFound, Unauthorized


def _find_client(plex, client_identifier: str) -> Tuple[Optional[Any], Optional[Any], str]:
    """Find a client by name or machineIdentifier.

    Args:
        plex: PlexServer instance
        client_identifier: Client name or machineIdentifier
        
    Returns:
        Tuple of (client, session, client_name) where:
        - client: The controllable PlexClient if found, None otherwise
        - session: The active session if found (for session-only control), None otherwise  
        - client_name: The display name of the client found
    """
    client = None
    session = None
    client_found_name = None
    
    # 1. Try direct client lookup first
    try:
        client = plex.client(client_identifier)
        client_found_name = client.title
        return client, None, client_found_name
    except (NotFound, Exception):
        pass
    
    # 2. Search in plex.clients() by partial name or machineIdentifier
    try:
        all_clients = plex.clients()
        for c in all_clients:
            machine_id = getattr(c, 'machineIdentifier', '')
            if (client_identifier.lower() in c.title.lower() or 
                client_identifier.lower() == machine_id.lower()):
                client = c
                client_found_name = c.title
                return client, None, client_found_name
    except Exception:
        pass
    
    # 3. Look in active sessions
    try:
        sessions = plex.sessions()
        for s in sessions:
            if hasattr(s, 'player') and s.player:
                player = s.player
                player_title = getattr(player, 'title', '')
                player_machine_id = getattr(player, 'machineIdentifier', '')
                
                if (client_identifier.lower() in player_title.lower() or 
                    client_identifier.lower() == player_machine_id.lower()):
                    session = s
                    client_found_name = player_title
                    
                    # Try to get a controllable client from this session's player
                    try:
                        client = plex.client(player_title)
                        return client, session, client_found_name
                    except (NotFound, Exception):
                        pass
                    
                    # Try by machine identifier
                    try:
                        for c in plex.clients():
                            if getattr(c, 'machineIdentifier', '') == player_machine_id:
                                client = c
                                return client, session, client_found_name
                    except Exception:
                        pass
                    
                    # Return session only (limited control)
                    return None, session, client_found_name
    except Exception:
        pass
    
    return None, None, None

@mcp.tool()
async def client_list(include_details: bool = True) -> str:
    """List all available Plex clients connected to the server.
    
    Args:
        include_details: Whether to include detailed information about each client
    
    Returns:
        List of clients with user info. Use machineIdentifier for reliable client control.
    """
    try:
        plex = connect_to_plex()
        clients = plex.clients()
        
        # Get sessions to find user info and additional clients
        sessions = plex.sessions()
        
        # Build a lookup of machineIdentifier -> session info (user, media, etc.)
        session_info = {}
        for session in sessions:
            if hasattr(session, 'player') and session.player:
                player = session.player
                machine_id = getattr(player, 'machineIdentifier', None)
                if machine_id:
                    # Get user info
                    username = "Unknown"
                    if hasattr(session, 'usernames') and session.usernames:
                        username = session.usernames[0]
                    
                    # Get media info
                    media_title = getattr(session, 'title', 'Unknown')
                    media_type = getattr(session, 'type', 'unknown')
                    
                    session_info[machine_id] = {
                        "user": username,
                        "media_title": media_title,
                        "media_type": media_type,
                        "state": getattr(player, 'state', 'unknown'),
                        "player": player
                    }
        
        # Combine clients from both sources
        all_clients = clients.copy()
        client_ids = {getattr(c, 'machineIdentifier', '') for c in clients}
        
        # Add session players that aren't in clients list
        for machine_id, info in session_info.items():
            if machine_id and machine_id not in client_ids:
                all_clients.append(info["player"])
                client_ids.add(machine_id)
        
        if not all_clients:
            return json.dumps({
                "status": "success",
                "message": "No clients currently connected to your Plex server.",
                "count": 0,
                "clients": []
            })
        
        result = []
        if include_details:
            for client in all_clients:
                machine_id = getattr(client, 'machineIdentifier', 'Unknown')
                
                # Get session info if available
                info = session_info.get(machine_id, {})
                
                client_data = {
                    "machineIdentifier": machine_id,  # First for emphasis
                    "name": client.title,
                    "user": info.get("user", None),  # Who's using this client
                    "state": info.get("state") or getattr(client, "state", "idle"),
                    "nowPlaying": info.get("media_title") if info else None,
                    "device": getattr(client, 'device', 'Unknown'),
                    "product": getattr(client, 'product', 'Unknown'),
                    "platform": getattr(client, "platform", "Unknown"),
                    "version": getattr(client, 'version', 'Unknown'),
                    "address": getattr(client, "address", None) or getattr(client, "_baseurl", "Unknown"),
                    "local": getattr(client, "local", None),
                    "controllable": machine_id in [getattr(c, 'machineIdentifier', '') for c in clients]
                }
                
                result.append(client_data)
        else:
            result = [{"machineIdentifier": getattr(c, 'machineIdentifier', ''), "name": c.title} for c in all_clients]
            
        return json.dumps({
            "status": "success",
            "message": f"Found {len(all_clients)} connected clients",
            "count": len(all_clients),
            "note": "Use machineIdentifier for reliable client control",
            "clients": result
        }, indent=2)
            
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error listing clients: {str(e)}"
        })

@mcp.tool()
async def client_get_details(client_name: str) -> str:
    """Get detailed information about a specific Plex client.
    
    Args:
        client_name: Name or machineIdentifier of the client to get details for
    
    Returns:
        Dictionary containing client details
    """
    try:
        plex = connect_to_plex()
        
        # Find the client
        client, session, client_found_name = _find_client(plex, client_name)
        
        # Use session player info if no controllable client
        if client is None and session is not None:
            player = session.player
            client_details = {
                "machineIdentifier": getattr(player, 'machineIdentifier', 'Unknown'),
                "name": getattr(player, 'title', 'Unknown'),
                "device": getattr(player, 'device', 'Unknown'),
                "product": getattr(player, 'product', 'Unknown'),
                "platform": getattr(player, "platform", "Unknown"),
                "state": getattr(player, "state", "Unknown"),
                "address": getattr(player, "address", "Unknown"),
                "controllable": False,
                "note": "This client is only visible via active session"
            }
            return json.dumps({
                "status": "success",
                "client": client_details
            }, indent=2)
        
        if client is None:
            return json.dumps({
                "status": "error",
                "message": f"No client found matching '{client_name}'. Use client_list to see available clients."
            })
            
        client_details = {
            "machineIdentifier": getattr(client, 'machineIdentifier', 'Unknown'),
            "name": client.title,
            "device": getattr(client, 'device', 'Unknown'),
            "deviceClass": getattr(client, "deviceClass", "Unknown"),
            "model": getattr(client, "model", "Unknown"),
            "product": getattr(client, 'product', 'Unknown'),
            "version": getattr(client, 'version', 'Unknown'),
            "platform": getattr(client, "platform", "Unknown"),
            "platformVersion": getattr(client, "platformVersion", "Unknown"),
            "state": getattr(client, "state", "Unknown"),
            "protocolCapabilities": getattr(client, "protocolCapabilities", []),
            "address": getattr(client, "address", None) or getattr(client, "_baseurl", "Unknown"),
            "local": getattr(client, "local", None),
            "protocol": getattr(client, "protocol", "plex"),
            "protocolVersion": getattr(client, "protocolVersion", "Unknown"),
            "vendor": getattr(client, "vendor", "Unknown"),
            "controllable": True
        }
        
        return json.dumps({
            "status": "success",
            "client": client_details
        }, indent=2)
            
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error getting client details: {str(e)}"
        })

@mcp.tool()
async def client_get_timelines(client_name: str) -> str:
    """Get the current timeline information for a specific Plex client.
    
    Args:
        client_name: Name or machineIdentifier of the client to get timeline for
    
    Returns:
        Timeline information for the client
    """
    try:
        plex = connect_to_plex()
        
        # Find the client
        client, session, client_found_name = _find_client(plex, client_name)
        
        # If we only have a session (no controllable client), use session info
        if client is None and session is not None:
            session_data = {
                "state": getattr(session.player, 'state', 'Unknown'),
                "time": getattr(session, 'viewOffset', 0),
                "duration": getattr(session, 'duration', 0),
                "progress": round((session.viewOffset / session.duration * 100) if hasattr(session, 'viewOffset') and 
                                   hasattr(session, 'duration') and session.duration else 0, 2),
                "title": getattr(session, 'title', 'Unknown'),
                "type": getattr(session, 'type', 'Unknown'),
            }
            return json.dumps({
                "status": "success",
                "client_name": client_found_name,
                "source": "session",
                "timeline": session_data
            }, indent=2)
        
        if client is None:
            return json.dumps({
                "status": "error",
                "message": f"No client found matching '{client_name}'. Use client_list to see available clients."
            })
            
        # Try to get timeline from client
        try:
            timeline = client.timeline
            
            if timeline is None:
                # Check if this client has an active session
                sessions = plex.sessions()
                for s in sessions:
                    if (hasattr(s, 'player') and s.player and 
                       getattr(s.player, 'machineIdentifier', '') == getattr(client, 'machineIdentifier', '')):
                        session_data = {
                            "state": getattr(s.player, 'state', 'Unknown'),
                            "time": getattr(s, 'viewOffset', 0),
                            "duration": getattr(s, 'duration', 0),
                            "progress": round((s.viewOffset / s.duration * 100) if s.duration else 0, 2),
                            "title": getattr(s, 'title', 'Unknown'),
                            "type": getattr(s, 'type', 'Unknown'),
                        }
                        return json.dumps({
                            "status": "success",
                            "client_name": client_found_name,
                            "source": "session",
                            "timeline": session_data
                        }, indent=2)
                
                return json.dumps({
                    "status": "info",
                    "message": f"Client '{client_found_name}' is not currently playing any media.",
                    "client_name": client_found_name
                })
                
            # Process timeline data
            timeline_data = {
                "type": getattr(timeline, 'type', 'Unknown'),
                "state": getattr(timeline, 'state', 'Unknown'),
                "time": getattr(timeline, 'time', 0),
                "duration": getattr(timeline, 'duration', 0),
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
            
            return json.dumps({
                "status": "success",
                "client_name": client_found_name,
                "source": "timeline",
                "timeline": timeline_data
            }, indent=2)
        except Exception:
            # Fallback to session info
            sessions = plex.sessions()
            for s in sessions:
                if (hasattr(s, 'player') and s.player and 
                    getattr(s.player, 'machineIdentifier', '') == getattr(client, 'machineIdentifier', '')):
                    session_data = {
                        "state": getattr(s.player, 'state', 'Unknown'),
                        "time": getattr(s, 'viewOffset', 0),
                        "duration": getattr(s, 'duration', 0),
                        "progress": round((s.viewOffset / s.duration * 100) if s.duration else 0, 2),
                        "title": getattr(s, 'title', 'Unknown'),
                        "type": getattr(s, 'type', 'Unknown'),
                    }
                    return json.dumps({
                        "status": "success",
                        "client_name": client_found_name,
                        "source": "session",
                        "timeline": session_data
                    }, indent=2)
            
            return json.dumps({
                "status": "warning",
                "message": f"Unable to get timeline information for client '{client_found_name}'. The client may not be responding.",
                "client_name": client_found_name
            })
            
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error getting client timeline: {str(e)}"
        })

@mcp.tool()
async def client_get_active() -> str:
    """Get all clients that are currently playing media.
    
    Returns:
        List of active clients with their playback status
    """
    try:
        plex = connect_to_plex()
        
        # Get all sessions
        sessions = plex.sessions()
        
        if not sessions:
            return json.dumps({
                "status": "success",
                "message": "No active playback sessions found.",
                "count": 0,
                "active_clients": []
            })
        
        active_clients = []
        
        for session in sessions:
            if hasattr(session, 'player') and session.player:
                player = session.player
                
                # Get media information
                media_info = {
                    "title": session.title if hasattr(session, 'title') else "Unknown",
                    "type": session.type if hasattr(session, 'type') else "Unknown",
                }
                
                # Add additional info based on media type
                if hasattr(session, 'type'):
                    if session.type == 'episode':
                        media_info["show"] = getattr(session, 'grandparentTitle', 'Unknown Show')
                        media_info["season"] = getattr(session, 'parentTitle', 'Unknown Season')
                        media_info["seasonEpisode"] = f"S{getattr(session, 'parentIndex', '?')}E{getattr(session, 'index', '?')}"
                    elif session.type == 'movie':
                        media_info["year"] = getattr(session, 'year', 'Unknown')
                
                # Calculate progress if possible
                progress = None
                if hasattr(session, 'viewOffset') and hasattr(session, 'duration') and session.duration:
                    progress = round((session.viewOffset / session.duration) * 100, 1)
                
                # Get user info
                username = "Unknown User"
                if hasattr(session, 'usernames') and session.usernames:
                    username = session.usernames[0]
                
                # Get transcoding status
                transcoding = False
                if hasattr(session, 'transcodeSessions') and session.transcodeSessions:
                    transcoding = True
                
                client_info = {
                    "name": player.title,
                    "device": getattr(player, 'device', 'Unknown'),
                    "product": getattr(player, 'product', 'Unknown'),
                    "platform": getattr(player, 'platform', 'Unknown'),
                    "state": getattr(player, 'state', 'Unknown'),
                    "user": username,
                    "media": media_info,
                    "progress": progress,
                    "transcoding": transcoding
                }
                
                active_clients.append(client_info)
        
        return json.dumps({
            "status": "success",
            "message": f"Found {len(active_clients)} active clients",
            "count": len(active_clients),
            "active_clients": active_clients
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error getting active clients: {str(e)}"
        })

@mcp.tool()
async def client_start_playback(media_title: str, client_name: str = None, 
                        offset: int = 0, library_name: str = None, 
                        use_external_player: bool = False) -> str:
    """Start playback of media on a specified client.
    
    Args:
        media_title: Title of the media to play
        client_name: Optional name of the client to play on (will prompt if not provided)
        offset: Optional time offset in milliseconds to start from
        library_name: Optional name of the library to search in
        use_external_player: Whether to use the client's external player
    """
    try:
        plex = connect_to_plex()
        
        # First, find the media item
        results = []
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(title=media_title)
            except Exception:
                return json.dumps({
                    "status": "error",
                    "message": f"Library '{library_name}' not found"
                })
        else:
            results = plex.search(media_title)
        
        if not results:
            return json.dumps({
                "status": "error",
                "message": f"No media found matching '{media_title}'"
            })
        
        if len(results) > 1:
            # If multiple results, provide information about them
            media_list = []
            for i, media in enumerate(results[:10], 1):  # Limit to first 10 to avoid overwhelming
                media_type = getattr(media, 'type', 'unknown')
                title = getattr(media, 'title', 'Unknown')
                year = getattr(media, 'year', '')
                
                media_info = {
                    "index": i,
                    "title": title,
                    "type": media_type,
                }
                
                if year:
                    media_info["year"] = year
                
                if media_type == 'episode':
                    show = getattr(media, 'grandparentTitle', 'Unknown Show')
                    season = getattr(media, 'parentIndex', '?')
                    episode = getattr(media, 'index', '?')
                    media_info["show"] = show
                    media_info["season"] = season
                    media_info["episode"] = episode
                
                media_list.append(media_info)
            
            return json.dumps({
                "status": "multiple_results",
                "message": f"Multiple items found matching '{media_title}'. Please specify a library or use a more specific title.",
                "count": len(results),
                "results": media_list
            }, indent=2)
        
        media = results[0]
        
        # If no client name specified, list available clients
        if not client_name:
            clients = plex.clients()
            
            if not clients:
                return json.dumps({
                    "status": "error",
                    "message": "No clients are currently connected to your Plex server."
                })
            
            client_list = []
            for i, client in enumerate(clients, 1):
                client_list.append({
                    "index": i,
                    "name": client.title,
                    "device": getattr(client, 'device', 'Unknown')
                })
            
            return json.dumps({
                "status": "client_selection",
                "message": "Please specify a client to play on using the client_name parameter",
                "available_clients": client_list
            }, indent=2)
        
        # Try to find the client
        client, session, client_found_name = _find_client(plex, client_name)
        
        if client is None:
            if session is not None:
                return json.dumps({
                    "status": "error",
                    "message": f"Client '{client_found_name}' does not support playback control. Only session stop is available."
                })
            return json.dumps({
                "status": "error",
                "message": f"No client found matching '{client_name}'. Use client_list to see available clients."
            })
        
        # Start playback
        media_type = getattr(media, 'type', 'unknown')
        title = getattr(media, 'title', 'Unknown')
        
        formatted_title = title
        if media_type == 'episode':
            show = getattr(media, 'grandparentTitle', 'Unknown Show')
            season = getattr(media, 'parentIndex', '?')
            episode = getattr(media, 'index', '?')
            formatted_title = f"{show} - S{season}E{episode} - {title}"
        elif hasattr(media, 'year') and media.year:
            formatted_title = f"{title} ({media.year})"
        
        try:
            if use_external_player:
                # Open in external player if supported by client
                capabilities = getattr(client, 'protocolCapabilities', []) or []
                if "Player" in capabilities:
                    media.playOn(client)
                else:
                    return json.dumps({
                        "status": "error",
                        "message": f"Client '{client_found_name}' does not support external player"
                    })
            else:
                # Normal playback
                client.playMedia(media, offset=offset)
            
            return json.dumps({
                "status": "success",
                "message": f"Started playback of '{formatted_title}' on {client_found_name}",
                "media": {
                    "title": title,
                    "type": media_type,
                    "formatted_title": formatted_title,
                    "rating_key": getattr(media, 'ratingKey', None)
                },
                "client": client_found_name,
                "offset": offset
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Error starting playback: {str(e)}"
            })
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error setting up playback: {str(e)}"
        })

@mcp.tool()
async def client_control_playback(client_name: str, action: str, 
                         parameter: int = None, media_type: str = 'video') -> str:
    """Control playback on a specified client.
    
    Args:
        client_name: Name of the client to control (use machine identifier or title from client_list)
        action: Action to perform (play, pause, stop, skipNext, skipPrevious, 
                stepForward, stepBack, seekTo, seekForward, seekBack, mute, unmute, setVolume)
        parameter: Parameter for actions that require it (like setVolume or seekTo)
        media_type: Type of media being controlled ('video', 'music', or 'photo')
    """
    try:
        plex = connect_to_plex()
        
        # Validate action
        valid_actions = [
            'play', 'pause', 'stop', 'skipNext', 'skipPrevious', 
            'stepForward', 'stepBack', 'seekTo', 'seekForward', 'seekBack',
            'mute', 'unmute', 'setVolume'
        ]
        
        if action not in valid_actions:
            return json.dumps({
                "status": "error",
                "message": f"Invalid action '{action}'. Valid actions are: {', '.join(valid_actions)}"
            })
        
        # Check if parameter is needed but not provided
        actions_needing_parameter = ['seekTo', 'setVolume']
        if action in actions_needing_parameter and parameter is None:
            return json.dumps({
                "status": "error",
                "message": f"Action '{action}' requires a parameter value."
            })
            
        # Validate media type
        valid_media_types = ['video', 'music', 'photo']
        if media_type not in valid_media_types:
            return json.dumps({
                "status": "error",
                "message": f"Invalid media type '{media_type}'. Valid types are: {', '.join(valid_media_types)}"
            })
        
        # Find the client - check multiple sources
        client = None
        session = None
        client_found_name = None
        
        # 1. Try direct client lookup first
        try:
            client = plex.client(client_name)
            client_found_name = client.title
        except (NotFound, Exception):
            pass
        
        # 2. If not found, search in plex.clients() by partial name
        if client is None:
            try:
                all_clients = plex.clients()
                for c in all_clients:
                    if client_name.lower() in c.title.lower() or client_name.lower() == getattr(c, 'machineIdentifier', '').lower():
                        client = c
                        client_found_name = c.title
                        break
            except Exception:
                pass
        
        # 3. If still not found, look in active sessions
        if client is None:
            sessions = plex.sessions()
            for s in sessions:
                if hasattr(s, 'player') and s.player:
                    player = s.player
                    player_title = getattr(player, 'title', '')
                    player_machine_id = getattr(player, 'machineIdentifier', '')
                    
                    if (client_name.lower() in player_title.lower() or 
                        client_name.lower() == player_machine_id.lower()):
                        session = s
                        client_found_name = player_title
                        
                        # Try to get a controllable client from this session's player
                        # The player from session isn't directly controllable, we need to
                        # find the actual client if it exists
                        try:
                            client = plex.client(player_title)
                        except (NotFound, Exception):
                            # Try by machine identifier
                            try:
                                for c in plex.clients():
                                    if getattr(c, 'machineIdentifier', '') == player_machine_id:
                                        client = c
                                        break
                            except Exception:
                                pass
                        break
        
        # If we found a session but no controllable client
        if client is None and session is not None:
            # Limited actions available via session
            if action == 'stop':
                try:
                    session.stop(reason='Stopped via Plex MCP Server')
                    return json.dumps({
                        "status": "success",
                        "message": f"Successfully stopped playback on '{client_found_name}'",
                        "action": action,
                        "client": client_found_name,
                        "note": "Session terminated (client does not support direct playback control)"
                    }, indent=2)
                except Exception as e:
                    return json.dumps({
                        "status": "error",
                        "message": f"Error stopping session: {str(e)}"
                    })
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"Client '{client_found_name}' is playing but does not support direct playback control. Only 'stop' is available for this client.",
                    "available_actions": ["stop"],
                    "note": "This client is visible in sessions but not controllable. It may not be advertising its control endpoint to the server."
                })
        
        # If no client found at all
        if client is None:
            return json.dumps({
                "status": "error",
                "message": f"No client found matching '{client_name}'. Use client_list to see available clients."
            })
        
        # Check if the client has playback control capability
        capabilities = getattr(client, 'protocolCapabilities', []) or []
        if isinstance(capabilities, str):
            capabilities = [capabilities]
        
        # Some clients don't report capabilities but still work
        # So we'll try anyway and catch errors
        
        # Perform the requested action
        try:
            # Transport controls
            if action == 'play':
                client.play(mtype=media_type)
            elif action == 'pause':
                client.pause(mtype=media_type)
            elif action == 'stop':
                client.stop(mtype=media_type)
            elif action == 'skipNext':
                client.skipNext(mtype=media_type)
            elif action == 'skipPrevious':
                client.skipPrevious(mtype=media_type)
            elif action == 'stepForward':
                client.stepForward(mtype=media_type)
            elif action == 'stepBack':
                client.stepBack(mtype=media_type)
            
            # Seeking
            elif action == 'seekTo':
                # Parameter should be milliseconds
                client.seekTo(parameter, mtype=media_type)
            elif action == 'seekForward':
                # Default to 30 seconds if no parameter
                seconds = parameter if parameter is not None else 30
                try:
                    current_time = client.timeline.time if client.timeline else 0
                    client.seekTo(current_time + (seconds * 1000), mtype=media_type)
                except:
                    return json.dumps({
                        "status": "error",
                        "message": "Unable to get current playback position for seeking forward"
                    })
            elif action == 'seekBack':
                # Default to 30 seconds if no parameter
                seconds = parameter if parameter is not None else 30
                try:
                    current_time = client.timeline.time if client.timeline else 0
                    seek_time = max(0, current_time - (seconds * 1000))
                    client.seekTo(seek_time, mtype=media_type)
                except:
                    return json.dumps({
                        "status": "error",
                        "message": "Unable to get current playback position for seeking back"
                    })
            
            # Volume controls
            elif action == 'mute':
                client.setVolume(0, mtype=media_type)
            elif action == 'unmute':
                client.setVolume(100, mtype=media_type)
            elif action == 'setVolume':
                # Parameter should be 0-100
                if parameter < 0 or parameter > 100:
                    return json.dumps({
                        "status": "error",
                        "message": "Volume must be between 0 and 100"
                    })
                client.setVolume(parameter, mtype=media_type)
            
            # Check timeline to confirm the action (may take a moment to update)
            time.sleep(0.5)  # Give a short delay for state to update
            
            # Get updated timeline info
            timeline_data = None
            try:
                timeline = client.timeline
                if timeline:
                    timeline_data = {
                        "state": getattr(timeline, "state", "unknown"),
                        "time": getattr(timeline, "time", 0),
                        "duration": getattr(timeline, "duration", 0),
                        "volume": getattr(timeline, "volume", None),
                        "muted": getattr(timeline, "muted", None)
                    }
            except:
                pass
            
            return json.dumps({
                "status": "success",
                "message": f"Successfully performed action '{action}' on client '{client_found_name}'",
                "action": action,
                "client": client_found_name,
                "parameter": parameter,
                "timeline": timeline_data
            }, indent=2)
            
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Error controlling playback: {str(e)}"
            })
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error setting up playback control: {str(e)}"
        })

@mcp.tool()
async def client_navigate(client_name: str, action: str) -> str:
    """Navigate a Plex client interface.
    
    Args:
        client_name: Name or machineIdentifier of the client to navigate
        action: Navigation action to perform (moveUp, moveDown, moveLeft, moveRight, 
                select, back, home, contextMenu)
    """
    try:
        plex = connect_to_plex()
        
        # Validate action
        valid_actions = [
            'moveUp', 'moveDown', 'moveLeft', 'moveRight',
            'select', 'back', 'home', 'contextMenu'
        ]
        
        if action not in valid_actions:
            return json.dumps({
                "status": "error",
                "message": f"Invalid navigation action '{action}'. Valid actions are: {', '.join(valid_actions)}"
            })
        
        # Find the client
        client, session, client_found_name = _find_client(plex, client_name)
        
        if client is None:
            if session is not None:
                return json.dumps({
                    "status": "error",
                    "message": f"Client '{client_found_name}' does not support navigation control."
                })
            return json.dumps({
                "status": "error",
                "message": f"No client found matching '{client_name}'. Use client_list to see available clients."
            })
        
        # Check if the client has navigation capability
        capabilities = getattr(client, 'protocolCapabilities', []) or []
        if "navigation" not in capabilities:
            return json.dumps({
                "status": "error",
                "message": f"Client '{client_found_name}' does not support navigation control."
            })
        
        # Perform the requested action
        try:
            if action == 'moveUp':
                client.moveUp()
            elif action == 'moveDown':
                client.moveDown()
            elif action == 'moveLeft':
                client.moveLeft()
            elif action == 'moveRight':
                client.moveRight()
            elif action == 'select':
                client.select()
            elif action == 'back':
                client.goBack()
            elif action == 'home':
                client.goToHome()
            elif action == 'contextMenu':
                client.contextMenu()
            
            return json.dumps({
                "status": "success",
                "message": f"Successfully performed navigation action '{action}' on client '{client_found_name}'",
                "action": action,
                "client": client_found_name
            }, indent=2)
            
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Error navigating client: {str(e)}"
            })
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error setting up client navigation: {str(e)}"
        })

@mcp.tool()
async def client_set_streams(client_name: str, audio_stream_id: str = None, 
                    subtitle_stream_id: str = None, video_stream_id: str = None) -> str:
    """Set audio, subtitle, or video streams for current playback on a client.
    
    Args:
        client_name: Name or machineIdentifier of the client to set streams for
        audio_stream_id: ID of the audio stream to switch to
        subtitle_stream_id: ID of the subtitle stream to switch to, use '0' to disable
        video_stream_id: ID of the video stream to switch to
    """
    try:
        plex = connect_to_plex()
        
        # Check if at least one stream ID is provided
        if audio_stream_id is None and subtitle_stream_id is None and video_stream_id is None:
            return json.dumps({
                "status": "error",
                "message": "At least one stream ID (audio, subtitle, or video) must be provided."
            })
        
        # Find the client
        client, session, client_found_name = _find_client(plex, client_name)
        
        if client is None:
            if session is not None:
                return json.dumps({
                    "status": "error",
                    "message": f"Client '{client_found_name}' does not support stream selection."
                })
            return json.dumps({
                "status": "error",
                "message": f"No client found matching '{client_name}'. Use client_list to see available clients."
            })
        
        # Check if client is currently playing
        try:
            timeline = client.timeline
            if timeline is None or not hasattr(timeline, 'state') or timeline.state != 'playing':
                # Check active sessions to see if this client has a session
                sessions = plex.sessions()
                client_session = None
                client_machine_id = getattr(client, 'machineIdentifier', '')
                
                for s in sessions:
                    if (hasattr(s, 'player') and s.player and 
                        getattr(s.player, 'machineIdentifier', '') == client_machine_id):
                        client_session = s
                        break
                
                if not client_session:
                    return json.dumps({
                        "status": "error",
                        "message": f"Client '{client_found_name}' is not currently playing any media."
                    })
        except Exception:
            return json.dumps({
                "status": "error",
                "message": f"Unable to get playback status for client '{client_found_name}'."
            })
        
        # Set streams
        changed_streams = []
        try:
            if audio_stream_id is not None:
                client.setAudioStream(audio_stream_id)
                changed_streams.append(f"audio to {audio_stream_id}")
            
            if subtitle_stream_id is not None:
                client.setSubtitleStream(subtitle_stream_id)
                changed_streams.append(f"subtitle to {subtitle_stream_id}")
            
            if video_stream_id is not None:
                client.setVideoStream(video_stream_id)
                changed_streams.append(f"video to {video_stream_id}")
            
            return json.dumps({
                "status": "success",
                "message": f"Successfully set streams for '{client_found_name}': {', '.join(changed_streams)}",
                "client": client_found_name,
                "changes": {
                    "audio_stream": audio_stream_id if audio_stream_id is not None else None,
                    "subtitle_stream": subtitle_stream_id if subtitle_stream_id is not None else None,
                    "video_stream": video_stream_id if video_stream_id is not None else None
                }
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Error setting streams: {str(e)}"
            })
    
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error setting up stream selection: {str(e)}"
        })