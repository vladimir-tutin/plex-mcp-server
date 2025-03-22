from typing import Optional
from modules import mcp, connect_to_plex
from plexapi.exceptions import NotFound # type: ignore
# Functions for sessions and playback
@mcp.tool()
async def get_active_sessions(unused: str = None) -> str:
    """Get information about current playback sessions, including IP addresses.
    
    Args:
        unused: Unused parameter to satisfy the function signature
    """
    try:
        plex = connect_to_plex()
        
        # Get all active sessions
        sessions = plex.sessions()
        
        if not sessions:
            return "No active sessions found."
        
        result = f"Active sessions ({len(sessions)}):\n\n"
        
        for i, session in enumerate(sessions, 1):
            # Basic media information
            item_type = getattr(session, 'type', 'unknown')
            title = getattr(session, 'title', 'Unknown')
            
            # Session information
            player = getattr(session, 'player', None)
            user = getattr(session, 'usernames', ['Unknown User'])[0]
            
            result += f"Session {i}:\n"
            result += f"User: {user}\n"
            
            # Media-specific information
            if item_type == 'episode':
                show_title = getattr(session, 'grandparentTitle', 'Unknown Show')
                season_num = getattr(session, 'parentIndex', '?')
                episode_num = getattr(session, 'index', '?')
                result += f"Content: {show_title} - S{season_num}E{episode_num} - {title} (TV Episode)\n"
            
            elif item_type == 'movie':
                year = getattr(session, 'year', '')
                result += f"Content: {title} ({year}) (Movie)\n"
            
            else:
                result += f"Content: {title} ({item_type})\n"
            
            # Player information
            if player:
                result += f"Player: {player.title}\n"
                result += f"State: {player.state}\n"
                
                # Add IP address if available
                if hasattr(player, 'address'):
                    result += f"IP: {player.address}\n"
                
                # Add platform information if available
                if hasattr(player, 'platform'):
                    result += f"Platform: {player.platform}\n"
                
                # Add product information if available
                if hasattr(player, 'product'):
                    result += f"Product: {player.product}\n"
                
                # Add device information if available
                if hasattr(player, 'device'):
                    result += f"Device: {player.device}\n"
                
                # Add version information if available
                if hasattr(player, 'version'):
                    result += f"Version: {player.version}\n"
            
            # Add playback information
            if hasattr(session, 'viewOffset') and hasattr(session, 'duration'):
                progress = (session.viewOffset / session.duration) * 100
                result += f"Progress: {progress:.1f}%\n"
                
                # Add remaining time if useful
                seconds_remaining = (session.duration - session.viewOffset) / 1000
                minutes_remaining = seconds_remaining / 60
                if minutes_remaining > 1:
                    result += f"Time remaining: {int(minutes_remaining)} minutes\n"
            
            # Add quality information if available
            if hasattr(session, 'media') and session.media:
                media = session.media[0] if isinstance(session.media, list) and session.media else session.media
                bitrate = getattr(media, 'bitrate', None)
                resolution = getattr(media, 'videoResolution', None)
                
                if bitrate:
                    result += f"Bitrate: {bitrate} kbps\n"
                
                if resolution:
                    result += f"Resolution: {resolution}\n"
            
            # Transcoding information
            transcode_session = getattr(session, 'transcodeSessions', None)
            if transcode_session:
                transcode = transcode_session[0] if isinstance(transcode_session, list) else transcode_session
                result += "Transcoding: Yes\n"
                
                # Add source vs target information if available
                if hasattr(transcode, 'sourceVideoCodec') and hasattr(transcode, 'videoCodec'):
                    result += f"Video: {transcode.sourceVideoCodec} → {transcode.videoCodec}\n"
                
                if hasattr(transcode, 'sourceAudioCodec') and hasattr(transcode, 'audioCodec'):
                    result += f"Audio: {transcode.sourceAudioCodec} → {transcode.audioCodec}\n"
                
                if hasattr(transcode, 'sourceResolution') and hasattr(transcode, 'width') and hasattr(transcode, 'height'):
                    result += f"Resolution: {transcode.sourceResolution} → {transcode.width}x{transcode.height}\n"
            else:
                result += "Transcoding: No (Direct Play/Stream)\n"
            
            result += "\n"
        
        return result
    except Exception as e:
        return f"Error getting active sessions: {str(e)}"

@mcp.tool()
async def get_media_playback_history(media_title: str, library_name: str = None) -> str:
    """Get playback history for a specific media item.
    
    Args:
        media_title: Title of the media to get history for
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
            results = plex.search(query=media_title)
        
        if not results:
            return f"No media found matching '{media_title}'."
        
        if len(results) > 1:
            return f"Multiple items found with title '{media_title}'. Please specify a library or use a more specific title."
        
        media = results[0]
        media_type = getattr(media, 'type', 'unknown')
        
        # Format title differently based on media type
        if media_type == 'episode':
            show = getattr(media, 'grandparentTitle', 'Unknown Show')
            season = getattr(media, 'parentTitle', 'Unknown Season')
            formatted_title = f"{show} - {season} - {media.title}"
        else:
            year = getattr(media, 'year', '')
            year_str = f" ({year})" if year else ""
            formatted_title = f"{media.title}{year_str}"
        
        # Get the history using the history() method 
        try:
            history_items = media.history()
            
            if not history_items:
                return f"No playback history found for '{formatted_title}'."
            
            result = f"Playback history for '{formatted_title}' [{media_type}]:\n"
            result += f"Total plays: {len(history_items)}\n\n"
            
            for item in history_items:
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
                
                # Get the timestamp when it was viewed
                viewed_at = getattr(item, 'viewedAt', None)
                viewed_at_str = viewed_at.strftime("%Y-%m-%d %H:%M") if viewed_at else "Unknown time"
                
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
                
                result += f"- {account_name} on {viewed_at_str} [{device_name}]\n"
            
            return result
            
        except AttributeError:
            # Fallback if history() method is not available
            # Get basic view information
            view_count = getattr(media, 'viewCount', 0) or 0
            last_viewed_at = getattr(media, 'lastViewedAt', None)
            
            if view_count == 0:
                return f"No one has watched '{formatted_title}' yet."
            
            # Format the basic results
            result = f"Playback history for '{formatted_title}' [{media_type}]:\n"
            result += f"View count: {view_count}\n"
            
            if last_viewed_at:
                last_viewed_str = last_viewed_at.strftime("%Y-%m-%d %H:%M") if hasattr(last_viewed_at, 'strftime') else str(last_viewed_at)
                result += f"Last viewed: {last_viewed_str}\n"
                
            # Add any additional account info if available
            account_info = getattr(media, 'viewedBy', [])
            if account_info:
                result += "\nWatched by:"
                for account in account_info:
                    result += f"\n- {account.title}"
            
            return result
        
    except Exception as e:
        return f"Error getting media playback history: {str(e)}"