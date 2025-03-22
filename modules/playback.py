from modules import mcp, connect_to_plex

@mcp.tool()
async def start_playback(media_title: str, client_name: str = None, use_external_player: bool = False) -> str:
    """Start playback of a media item on a specified client or in the default video player.
    
    Args:
        media_title: Title of the media to play
        client_name: Name of the client to play on (optional)
        use_external_player: If True, open in system's default video player instead of Plex
    """
    try:
        plex = connect_to_plex()
        
        # Search for the media
        results = plex.search(query=media_title)
        if not results:
            return f"No media found matching '{media_title}'."
        
        media = results[0]
        
        # If using external player, find the file path and open it
        if use_external_player:
            # Get the file path
            file_path = None
            
            # For movies and episodes, we need to access the media parts
            try:
                if hasattr(media, 'media') and media.media:
                    for media_item in media.media:
                        if hasattr(media_item, 'parts') and media_item.parts:
                            for part in media_item.parts:
                                if hasattr(part, 'file') and part.file:
                                    file_path = part.file
                                    break
                            if file_path:
                                break
                        if file_path:
                            break
            except Exception as e:
                return f"Error finding file path: {str(e)}"
            
            if not file_path:
                return f"Could not find file path for '{media_title}'."
            
            # Check if the file is accessible
            import os
            if not os.path.exists(file_path):
                # Try to get a direct play URL
                try:
                    # Get server connection info
                    server_url = plex._baseurl
                    token = plex._token
                    
                    # Find the direct play part ID
                    part_id = None
                    if hasattr(media, 'media') and media.media:
                        for media_item in media.media:
                            if hasattr(media_item, 'parts') and media_item.parts:
                                for part in media_item.parts:
                                    if hasattr(part, 'id'):
                                        part_id = part.id
                                        break
                                if part_id:
                                    break
                            if part_id:
                                break
                    
                    if part_id:
                        # Construct a direct streaming URL
                        stream_url = f"{server_url}/library/parts/{part_id}/file.mp4?X-Plex-Token={token}"
                        
                        # Try to detect VLC or launch the default video player
                        import subprocess
                        import shutil
                        
                        if os.name == 'nt':  # Windows
                            # Try to find VLC in common install locations
                            vlc_paths = [
                                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
                            ]
                            
                            vlc_path = None
                            for path in vlc_paths:
                                if os.path.exists(path):
                                    vlc_path = path
                                    break
                            
                            if vlc_path:
                                # Launch VLC with the URL
                                subprocess.Popen([vlc_path, stream_url])
                                return f"Opening '{media_title}' in VLC Player."
                            else:
                                # Try to check if VLC is in PATH
                                vlc_in_path = shutil.which("vlc")
                                if vlc_in_path:
                                    subprocess.Popen([vlc_in_path, stream_url])
                                    return f"Opening '{media_title}' in VLC Player."
                                else:
                                    # If VLC is not found, try launching with the system's default URL handler
                                    # but add a parameter that hints this is a media file
                                    import webbrowser
                                    webbrowser.open(stream_url)
                                    return f"Opening '{media_title}' streaming URL. If it opens in a browser, you may need to copy the URL and open it in your media player manually."
                        else:  # macOS/Linux
                            # Try to find VLC
                            vlc_in_path = shutil.which("vlc")
                            if vlc_in_path:
                                subprocess.Popen([vlc_in_path, stream_url])
                                return f"Opening '{media_title}' in VLC Player."
                            else:
                                # Fallback to the system's default open command
                                if os.name == 'posix':  # macOS/Linux
                                    subprocess.call(('open', stream_url))
                                
                                return f"Opening '{media_title}' streaming URL."
                    else:
                        return f"Could not find a direct URL for '{media_title}'."
                except Exception as url_error:
                    return f"Error getting direct URL: {str(url_error)}"
            
            # Open the file in the default video player if it exists
            import subprocess
            
            try:
                if os.name == 'nt':  # Windows
                    os.startfile(file_path)
                else:  # macOS and Linux
                    subprocess.call(('open', file_path))
                
                return f"Opening '{media_title}' in your default video player. File: {file_path}"
            except Exception as e:
                return f"Error opening file in external player: {str(e)}"
        
        else:
            # Original functionality: play on Plex client
            # Get available clients
            clients = plex.clients()
            if not clients:
                return "No Plex clients available for playback. If you want to play this media on your local device, try setting use_external_player=True."
            
            # Find the requested client or use the first available one
            target_client = None
            if client_name:
                for client in clients:
                    if client.title.lower() == client_name.lower():
                        target_client = client
                        break
                
                if target_client is None:
                    client_list = ", ".join([c.title for c in clients])
                    return f"Client '{client_name}' not found. Available clients: {client_list}"
            else:
                target_client = clients[0]
            
            # Start playback
            target_client.playMedia(media)
            return f"Started playback of '{media.title}' on '{target_client.title}'."
    except Exception as e:
        return f"Error starting playback: {str(e)}"