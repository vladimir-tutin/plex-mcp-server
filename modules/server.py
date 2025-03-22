from modules import mcp, connect_to_plex
import os
from typing import Dict, List, Any, Optional

# Functions for logs
@mcp.tool()
async def get_plex_logs(num_lines: int = 100, log_type: str = "server") -> str:
    """Get Plex server logs.
    
    Args:
        num_lines: Number of log lines to retrieve
        log_type: Type of log to retrieve (server, scanner, transcoder, updater)
    """
    try:
        import zipfile
        import io
        import tempfile
        import os
        import shutil
        import traceback
        
        plex = connect_to_plex()
        
        # Map common log type names to the actual file names
        log_type_map = {
            'server': 'Plex Media Server.log',
            'scanner': 'Plex Media Scanner.log',
            'transcoder': 'Plex Transcoder.log',
            'updater': 'Plex Update Service.log'
        }
        
        log_file_name = log_type_map.get(log_type.lower(), log_type)
        
        # Download logs from the Plex server
        logs_path_or_data = plex.downloadLogs()
        
        # Handle zipfile content based on what we received
        if isinstance(logs_path_or_data, str) and os.path.exists(logs_path_or_data) and logs_path_or_data.endswith('.zip'):
            # We received a path to a zip file
            with zipfile.ZipFile(logs_path_or_data, 'r') as zip_ref:
                log_content = extract_log_from_zip(zip_ref, log_file_name)
                
            # Clean up the downloaded zip if desired
            try:
                os.remove(logs_path_or_data)
            except:
                pass  # Ignore errors in cleanup
        else:
            # We received the actual data - process in memory
            if isinstance(logs_path_or_data, str):
                logs_path_or_data = logs_path_or_data.encode('utf-8')
                
            try:
                # Create an in-memory zip file
                zip_buffer = io.BytesIO(logs_path_or_data)
                with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                    log_content = extract_log_from_zip(zip_ref, log_file_name)
            except zipfile.BadZipFile:
                return f"Downloaded data is not a valid zip file. First 100 bytes: {logs_path_or_data[:100]}"
        
        # Extract the last num_lines from the log content
        log_lines = log_content.splitlines()
        log_lines = log_lines[-num_lines:] if len(log_lines) > num_lines else log_lines
        
        result = f"Last {len(log_lines)} lines of {log_file_name}:\n\n"
        result += '\n'.join(log_lines)
        
        return result
    except Exception as e:
        return f"Error getting Plex logs: {str(e)}\n{traceback.format_exc()}"

def extract_log_from_zip(zip_ref, log_file_name):
    """Extract the requested log file content from a zip file object."""
    # List all files in the zip
    all_files = zip_ref.namelist()
    
    # Find the requested log file
    log_file_path = None
    for file in all_files:
        if log_file_name.lower() in os.path.basename(file).lower():
            log_file_path = file
            break
    
    if not log_file_path:
        raise ValueError(f"Could not find log file for type: {log_file_name}. Available files: {', '.join(all_files)}")
    
    # Read the log file content
    with zip_ref.open(log_file_path) as f:
        log_content = f.read().decode('utf-8', errors='ignore')
    
    return log_content

# Server monitoring functions

@mcp.tool()
async def get_server_info() -> Dict[str, Any]:
    """Get detailed information about the Plex server.
    
    Returns:
        Dictionary containing server details including version, platform, etc.
    """
    try:
        plex = connect_to_plex()
        
        return {
            "version": plex.version,
            "platform": plex.platform,
            "platform_version": plex.platformVersion,
            "updated_at": plex.updatedAt,
            "server_name": plex.friendlyName,
            "machine_identifier": plex.machineIdentifier,
            "server_address": plex._baseurl,
            "server_token": "***" if plex._token else None,
            "myplex_username": getattr(plex, 'myPlexUsername', None),
            "transcoder_video": getattr(plex, 'transcoderVideo', False),
            "transcoder_audio": getattr(plex, 'transcoderAudio', False),
            "transcoder_active_video_sessions": getattr(plex, 'transcoderActiveVideoSessions', 0),
            "allow_media_deletion": getattr(plex, 'allowMediaDeletion', False),
            "sync_enabled": getattr(plex, 'sync', False),
            "multiuser": getattr(plex, 'multiuser', False),
            "hub_search": getattr(plex, 'hubSearch', False),
            "certificate": getattr(plex, 'certificate', False),
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_server_activities() -> Dict[str, Any]:
    """Get information about current server activities.
    
    Returns:
        Dictionary of all current server activities
    """
    try:
        plex = connect_to_plex()
        
        activities = []
        activities_list = plex.activities
        
        # Check if activities is callable (method) or a property
        if callable(activities_list):
            activities_list = activities_list()
            
        # Now iterate through the list
        if isinstance(activities_list, list):
            for activity in activities_list:
                activities.append({
                    "uuid": getattr(activity, "uuid", "Unknown"),
                    "type": getattr(activity, "type", "Unknown"),
                    "cancellable": getattr(activity, "cancellable", False),
                    "title": getattr(activity, "title", "Unknown"),
                    "subtitle": getattr(activity, "subtitle", ""),
                    "progress": getattr(activity, "progress", 0),
                    "context": getattr(activity, "context", ""),
                    "state": getattr(activity, "state", "unknown"),
                })
        
        return {
            "activities": activities,
            "count": len(activities)
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_server_bandwidth() -> Dict[str, Any]:
    """Get bandwidth statistics from the Plex server.
    
    Returns:
        Dictionary containing bandwidth statistics
    """
    try:
        plex = connect_to_plex()
        
        # The bandwidth() method might not directly return data as a dict
        # with timespan keys. Let's handle different possible formats.
        bandwidth_data = plex.bandwidth()
        
        result = {
            "bandwidth_data": [],
            "error": None
        }
        
        # Try to determine the structure of the bandwidth data
        if hasattr(bandwidth_data, "__iter__") and not isinstance(bandwidth_data, (str, bytes)):
            # If it's an iterable object
            if isinstance(bandwidth_data, dict):
                # If it's a dictionary, process as originally intended
                for timespan, data in bandwidth_data.items():
                    if isinstance(data, dict):
                        timespan_data = {
                            "timespan": timespan,
                            "metrics": []
                        }
                        for bandwidth_type, value in data.items():
                            timespan_data["metrics"].append({
                                "type": bandwidth_type,
                                "value": value
                            })
                        result["bandwidth_data"].append(timespan_data)
            else:
                # If it's a list or other iterable
                for item in bandwidth_data:
                    # Try to extract relevant attributes from each item
                    if hasattr(item, "__dict__"):
                        item_data = {}
                        for attr_name in dir(item):
                            if not attr_name.startswith("_") and not callable(getattr(item, attr_name)):
                                item_data[attr_name] = getattr(item, attr_name)
                        result["bandwidth_data"].append(item_data)
                    else:
                        # If it's a simple value, add it directly
                        result["bandwidth_data"].append(item)
        else:
            # If it's not iterable, just return the raw data
            result["bandwidth_data"] = str(bandwidth_data)
            
        return result
    except Exception as e:
        return {"error": str(e), "bandwidth_data": []}

@mcp.tool()
async def get_server_resources() -> Dict[str, Any]:
    """Get resource usage information from the Plex server.
    
    Returns:
        Dictionary containing resource usage statistics
    """
    try:
        plex = connect_to_plex()
        
        resources = plex.resources()
        result = {
            "cpu": [],
            "memory": [],
            "process": []
        }
        
        for timespan, data in resources.get("cpu", {}).items():
            result["cpu"].append({
                "timespan": timespan,
                "value": data
            })
            
        for timespan, data in resources.get("memory", {}).items():
            result["memory"].append({
                "timespan": timespan,
                "value": data
            })
        
        # Process-specific resource data
        process_data = resources.get("process", {})
        for key, value in process_data.items():
            result["process"].append({
                "metric": key,
                "value": value
            })
        
        return result
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_server_butler_tasks() -> Dict[str, Any]:
    """Get information about Plex Butler tasks.
    
    Returns:
        Dictionary containing information about scheduled and running butler tasks
    """
    try:
        plex = connect_to_plex()
        
        tasks = []
        
        butler_tasks = plex.butlerTasks()
        if butler_tasks:
            for task in butler_tasks:
                task_info = {
                    "name": getattr(task, "title", "Unknown"),
                    "description": getattr(task, "description", ""),
                    "enabled": getattr(task, "enabled", False),
                    "schedule": {}
                }
                
                # Add schedule information if available
                schedule = task_info["schedule"]
                for attr in ["interval", "frequency", "time", "days"]:
                    if hasattr(task, attr):
                        schedule[attr] = getattr(task, attr)
                
                tasks.append(task_info)
        
        # Add currently running Butler tasks if available
        running_tasks = []
        try:
            activities = plex.activities
            if callable(activities):
                activities = activities()
                
            if activities:
                for activity in activities:
                    if hasattr(activity, "type") and "butler" in activity.type.lower():
                        running_tasks.append({
                            "type": getattr(activity, "type", "Unknown"),
                            "title": getattr(activity, "title", "Unknown"),
                            "subtitle": getattr(activity, "subtitle", ""),
                            "progress": getattr(activity, "progress", 0),
                            "state": getattr(activity, "state", "unknown")
                        })
        except Exception as e:
            running_tasks.append({"error": f"Error getting running tasks: {str(e)}"})
        
        return {
            "tasks": tasks,
            "running_tasks": running_tasks
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_server_sessions_stats() -> Dict[str, Any]:
    """Get statistics on current and historical Plex sessions.
    
    Returns:
        Dictionary containing session statistics including bandwidth, transcoding info, etc.
    """
    try:
        plex = connect_to_plex()
        
        # Get current sessions
        current_sessions = plex.sessions()
        
        # Aggregate current stats
        active_streams = len(current_sessions)
        direct_play = 0
        transcoding = 0
        total_bandwidth = 0
        
        sessions_details = []
        
        for session in current_sessions:
            session_info = {
                "user": session.usernames[0] if hasattr(session, 'usernames') and session.usernames else "Unknown",
                "title": session.title,
                "bandwidth": getattr(session, "bitrate", 0),
                "player": getattr(session.player, "title", "Unknown") if hasattr(session, "player") else "Unknown",
                "state": getattr(session.player, "state", "Unknown") if hasattr(session, "player") else "Unknown",
                "transcoding_info": {}
            }
            
            # Check if transcoding
            is_transcoding = False
            media_info = {}
            
            # Check media streams and transcoding status
            for media in session.media:
                if media:
                    media_info = {
                        "videoResolution": getattr(media, "videoResolution", "Unknown"),
                        "audioChannels": getattr(media, "audioChannels", "Unknown"),
                        "bitrate": getattr(media, "bitrate", 0)
                    }
                    
                    for part in media.parts:
                        for stream in part.streams:
                            if hasattr(stream, "decision") and stream.decision not in [None, "direct play"]:
                                is_transcoding = True
                                session_info["transcoding_info"][stream.streamType] = stream.decision
            
            if is_transcoding:
                transcoding += 1
            else:
                direct_play += 1
                
            # Add bandwidth to total
            if hasattr(session, "bitrate") and session.bitrate:
                total_bandwidth += session.bitrate
                
            session_info.update(media_info)
            sessions_details.append(session_info)
        
        # Return the aggregated statistics and details
        return {
            "active_streams": active_streams,
            "direct_play": direct_play,
            "transcoding": transcoding,
            "total_bandwidth_kbps": total_bandwidth,
            "sessions": sessions_details
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_server_alerts() -> Dict[str, Any]:
    """Get current alerts from the Plex server.
    
    Returns:
        Dictionary containing server alerts and their details
    """
    try:
        plex = connect_to_plex()
        
        # Check if the alerts attribute/method exists
        if not hasattr(plex, 'alerts'):
            return {
                "alert_count": 0,
                "alerts": [],
                "error": "Server does not support alerts API or no alerts feature available"
            }
        
        alerts_data = plex.alerts
        # Check if it's a method or attribute
        if callable(alerts_data):
            alerts_data = alerts_data()
            
        # Handle the alerts data
        alerts = []
        if alerts_data and isinstance(alerts_data, list):
            for alert in alerts_data:
                alerts.append({
                    "id": getattr(alert, "id", "Unknown"),
                    "title": getattr(alert, "title", "Unknown"),
                    "description": getattr(alert, "description", ""),
                    "severity": getattr(alert, "severity", "unknown"),
                    "timestamp": getattr(alert, "timestamp", "")
                })
        
        return {
            "alert_count": len(alerts),
            "alerts": alerts
        }
    except Exception as e:
        return {"error": str(e), "alert_count": 0, "alerts": []}

@mcp.tool()
async def toggle_butler_task(task_name: str, enable: bool) -> str:
    """Enable or disable a specific Plex Butler task.
    
    Args:
        task_name: Name of the butler task to modify
        enable: Whether to enable or disable the task
    
    Returns:
        Success or error message
    """
    try:
        plex = connect_to_plex()
        
        # Get all butler tasks
        tasks = plex.butlerTasks()
        
        # Find the task that matches the name
        target_task = None
        for task in tasks:
            task_title = getattr(task, "title", "")
            if task_title and task_name.lower() in task_title.lower():
                target_task = task
                break
        
        if not target_task:
            return f"No butler task found matching '{task_name}'"
        
        # Set the task state
        if enable:
            if hasattr(target_task, "enable") and callable(target_task.enable):
                target_task.enable()
                return f"Successfully enabled butler task: {getattr(target_task, 'title', 'Unknown')}"
            else:
                return f"The butler task does not support the enable operation"
        else:
            if hasattr(target_task, "disable") and callable(target_task.disable):
                target_task.disable()
                return f"Successfully disabled butler task: {getattr(target_task, 'title', 'Unknown')}"
            else:
                return f"The butler task does not support the disable operation"
            
    except Exception as e:
        return f"Error toggling butler task: {str(e)}"

@mcp.tool()
async def run_butler_task(task_name: str) -> str:
    """Manually run a specific Plex Butler task now.
    
    Args:
        task_name: Name of the butler task to run
    
    Returns:
        Success or error message
    """
    try:
        plex = connect_to_plex()
        
        # Get all butler tasks
        tasks = plex.butlerTasks()
        
        # Find the task that matches the name
        target_task = None
        for task in tasks:
            task_title = getattr(task, "title", "")
            if task_title and task_name.lower() in task_title.lower():
                target_task = task
                break
        
        if not target_task:
            return f"No butler task found matching '{task_name}'"
        
        # Run the task
        if hasattr(target_task, "run") and callable(target_task.run):
            target_task.run()
            return f"Successfully started butler task: {getattr(target_task, 'title', 'Unknown')}"
        else:
            return f"The butler task does not support the run operation"
            
    except Exception as e:
        return f"Error running butler task: {str(e)}"