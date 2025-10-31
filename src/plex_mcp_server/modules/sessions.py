import json
from typing import Optional
from . import mcp, connect_to_plex

# Functions for sessions and playback
@mcp.tool()
async def sessions_get_active(unused: str = None) -> str:
    """Get information about current playback sessions, including IP addresses.
    
    Args:
        unused: Unused parameter to satisfy the function signature
    """
    try:
        plex = connect_to_plex()
        
        # Get all active sessions
        sessions = plex.sessions()
        
        if not sessions:
            return json.dumps({
                "status": "success",
                "message": "No active sessions found.",
                "sessions_count": 0,
                "sessions": []
            })
        
        sessions_data = []
        transcode_count = 0
        direct_play_count = 0
        total_bitrate = 0
        
        for session in enumerate(sessions, 1):
            i, session = session
            # Basic media information
            item_type = getattr(session, 'type', 'unknown')
            title = getattr(session, 'title', 'Unknown')
            
            # Session information
            player = getattr(session, 'player', None)
            user = getattr(session, 'usernames', ['Unknown User'])[0]
            
            session_info = {
                "session_id": i,
                "state": player.state,
                "player_name": player.title,
                "user": user,
                "content_type": item_type, 
                "player": {},
                "progress": {}
            }
            
            # Media-specific information
            if item_type == 'episode':
                show_title = getattr(session, 'grandparentTitle', 'Unknown Show')
                season_num = getattr(session, 'parentIndex', '?')
                episode_num = getattr(session, 'index', '?')
                session_info["content_description"] = f"{show_title} - S{season_num}E{episode_num} - {title} (TV Episode)"
            
            elif item_type == 'movie':
                year = getattr(session, 'year', '')
                session_info["year"] = year
                session_info["content_description"] = f"{title} ({year}) (Movie)"
            
            else:
                session_info["content_description"] = f"{title} ({item_type})"
            
            # Player information
            if player:
                player_info = {
                }
                
                # Add IP address if available
                if hasattr(player, 'address'):
                    player_info["ip"] = player.address
                
                # Add platform information if available
                if hasattr(player, 'platform'):
                    player_info["platform"] = player.platform
                
                # Add product information if available
                if hasattr(player, 'product'):
                    player_info["product"] = player.product
                
                # Add device information if available
                if hasattr(player, 'device'):
                    player_info["device"] = player.device
                
                # Add version information if available
                if hasattr(player, 'version'):
                    player_info["version"] = player.version
                
                session_info["player"] = player_info
            
            # Add playback information
            if hasattr(session, 'viewOffset') and hasattr(session, 'duration'):
                progress = (session.viewOffset / session.duration) * 100
                seconds_remaining = (session.duration - session.viewOffset) / 1000
                minutes_remaining = seconds_remaining / 60
                
                session_info["progress"] = {
                    "percent": round(progress, 1),
                    "minutes_remaining": int(minutes_remaining) if minutes_remaining > 1 else 0
                }
            
            # Add quality information if available
            if hasattr(session, 'media') and session.media:
                media = session.media[0] if isinstance(session.media, list) and session.media else session.media
                media_info = {}
                
                bitrate = getattr(media, 'bitrate', None)
                if bitrate:
                    media_info["bitrate"] = f"{bitrate} kbps"
                    # Add to total bitrate
                    try:
                        total_bitrate += int(bitrate)
                    except (TypeError, ValueError):
                        pass
                
                resolution = getattr(media, 'videoResolution', None)
                if resolution:
                    media_info["resolution"] = resolution
                
                if media_info:
                    session_info["media_info"] = media_info
            
            # Transcoding information
            transcode_session = getattr(session, 'transcodeSessions', None)
            if transcode_session:
                transcode = transcode_session[0] if isinstance(transcode_session, list) else transcode_session
                
                transcode_info = {"active": True}
                
                # Add source vs target information if available
                if hasattr(transcode, 'sourceVideoCodec') and hasattr(transcode, 'videoCodec'):
                    transcode_info["video"] = f"{transcode.sourceVideoCodec} → {transcode.videoCodec}"
                
                if hasattr(transcode, 'sourceAudioCodec') and hasattr(transcode, 'audioCodec'):
                    transcode_info["audio"] = f"{transcode.sourceAudioCodec} → {transcode.audioCodec}"
                
                if hasattr(transcode, 'sourceResolution') and hasattr(transcode, 'width') and hasattr(transcode, 'height'):
                    transcode_info["resolution"] = f"{transcode.sourceResolution} → {transcode.width}x{transcode.height}"
                
                session_info["transcoding"] = transcode_info
                transcode_count += 1
            else:
                session_info["transcoding"] = {"active": False, "mode": "Direct Play/Stream"}
                direct_play_count += 1
            
            sessions_data.append(session_info)
        
        return json.dumps({
            "status": "success",
            "message": f"Found {len(sessions)} active sessions",
            "sessions_count": len(sessions),
            "transcode_count": transcode_count,
            "direct_play_count": direct_play_count,
            "total_bitrate_kbps": total_bitrate,
            "sessions": sessions_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error getting active sessions: {str(e)}"
        })

@mcp.tool()
async def sessions_get_media_playback_history(media_title: str = None, library_name: str = None, media_id: int = None) -> str:
    """Get playback history for a specific media item.
    
    Args:
        media_title: Title of the media to get history for (optional if media_id is provided)
        library_name: Optional library name to limit search to
        media_id: Plex media ID/rating key to directly fetch the item (optional if media_title is provided)
    """
    try:
        plex = connect_to_plex()
        
        # Check if we have at least one identifier
        if not media_title and not media_id:
            return json.dumps({
                "status": "error",
                "message": "Either media_title or media_id must be provided."
            })
        
        media = None
        results = []
        
        # If media_id is provided, try to fetch the item directly
        if media_id:
            try:
                # fetchItem takes a rating key and returns the media object
                media = plex.fetchItem(media_id)
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "message": f"Media with ID '{media_id}' not found: {str(e)}"
                })
        # Otherwise search by title
        elif media_title:
            if library_name:
                try:
                    library = plex.library.section(library_name)
                    results = library.search(title=media_title)
                except Exception:
                    return json.dumps({
                        "status": "error",
                        "message": f"Library '{library_name}' not found."
                    })
            else:
                results = plex.search(media_title)
            
            if not results:
                return json.dumps({
                    "status": "error",
                    "message": f"No media found matching '{media_title}'."
                })
            
            # If we have multiple results, provide details about each match
            if len(results) > 1:
                matches = []
                for item in results:
                    item_info = {
                        "media_id": item.ratingKey,
                        "type": getattr(item, 'type', 'unknown'),
                        "title": item.title
                    }
                    
                    # Add type-specific info
                    if item.type == 'episode':
                        item_info["show_title"] = getattr(item, 'grandparentTitle', 'Unknown Show')
                        item_info["season"] = getattr(item, 'parentTitle', 'Unknown Season')
                        item_info["season_number"] = getattr(item, 'parentIndex', '?')
                        item_info["episode_number"] = getattr(item, 'index', '?')
                        item_info["formatted_title"] = f"{item_info['show_title']} - S{item_info['season_number']}E{item_info['episode_number']} - {item.title}"
                    elif item.type == 'movie':
                        year = getattr(item, 'year', '')
                        if year:
                            item_info["year"] = year
                        item_info["formatted_title"] = f"{item.title} ({year})" if year else item.title
                    
                    matches.append(item_info)
                
                return json.dumps({
                    "status": "multiple_matches",
                    "message": f"Multiple items found with title '{media_title}'. Please specify a library, use a more specific title, or use one of the media_id values below.",
                    "matches": matches
                }, indent=2)
            
            media = results[0]
        
        media_type = getattr(media, 'type', 'unknown')
        
        # Format title differently based on media type
        media_info = {
            "media_id": media.ratingKey,
            "key": media.key
        }
        
        if media_type == 'episode':
            show = getattr(media, 'grandparentTitle', 'Unknown Show')
            season = getattr(media, 'parentTitle', 'Unknown Season')
            formatted_title = f"{show} - {season} - {media.title}"
            media_info["show_title"] = show
            media_info["season_title"] = season
            media_info["episode_title"] = media.title
        else:
            year = getattr(media, 'year', '')
            year_str = f" ({year})" if year else ""
            formatted_title = f"{media.title}{year_str}"
            media_info["title"] = media.title
            if year:
                media_info["year"] = year
        
        media_info["type"] = media_type
        media_info["formatted_title"] = formatted_title
        
        # Get the history using the history() method 
        try:
            history_items = media.history()
            
            if not history_items:
                return json.dumps({
                    "status": "success",
                    "message": f"No playback history found for '{formatted_title}'.",
                    "media": media_info,
                    "play_count": 0,
                    "history": []
                })
            
            history_data = []
            
            for item in history_items:
                history_entry = {}
                
                # Get the username if available
                account_id = getattr(item, 'accountID', None)
                account_name = "Unknown User"
                
                # Try to get the account name from the accountID
                if account_id:
                    try:
                        # This may not work unless we have admin privileges
                        account = plex.myPlexAccount()
                        if account.id == account_id:
                            account_name = account.title
                        else:
                            for user in account.users():
                                if user.id == account_id:
                                    account_name = user.title
                                    break
                    except:
                        # If we can't get the account name, just use the ID
                        account_name = f"User ID: {account_id}"
                
                history_entry["user"] = account_name
                
                # Get the timestamp when it was viewed
                viewed_at = getattr(item, 'viewedAt', None)
                viewed_at_str = viewed_at.strftime("%Y-%m-%d %H:%M") if viewed_at else "Unknown time"
                history_entry["viewed_at"] = viewed_at_str
                
                # Device information if available
                device_id = getattr(item, 'deviceID', None)
                device_name = "Unknown Device"
                
                # Try to resolve device name using systemDevice method
                if device_id:
                    try:
                        device = plex.systemDevice(device_id)
                        if device and hasattr(device, 'name'):
                            device_name = device.name
                    except Exception:
                        # If we can't resolve the device name, just use the ID
                        device_name = f"Device ID: {device_id}"
                
                history_entry["device"] = device_name
                history_data.append(history_entry)
            
            return json.dumps({
                "status": "success",
                "media": media_info,
                "play_count": len(history_items),
                "history": history_data
            }, indent=2)
            
        except AttributeError:
            # Fallback if history() method is not available
            # Get basic view information
            view_count = getattr(media, 'viewCount', 0) or 0
            last_viewed_at = getattr(media, 'lastViewedAt', None)
            
            if view_count == 0:
                return json.dumps({
                    "status": "success", 
                    "message": f"No one has watched '{formatted_title}' yet.",
                    "media": media_info,
                    "play_count": 0
                })
            
            result = {
                "status": "success",
                "media": media_info,
                "play_count": view_count,
            }
            
            if last_viewed_at:
                last_viewed_str = last_viewed_at.strftime("%Y-%m-%d %H:%M") if hasattr(last_viewed_at, 'strftime') else str(last_viewed_at)
                result["last_viewed"] = last_viewed_str
                
            # Add any additional account info if available
            account_info = getattr(media, 'viewedBy', [])
            if account_info:
                result["viewed_by"] = [account.title for account in account_info]
            
            return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error getting media playback history: {str(e)}"
        })