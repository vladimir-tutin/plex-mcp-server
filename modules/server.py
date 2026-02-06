from modules import mcp, connect_to_plex
import os
from typing import Dict, List, Any, Optional
import json
import asyncio
import requests

@mcp.tool()
async def server_get_plex_logs(num_lines: int = 100, log_type: str = "server", start_line: int = None, list_files: bool = False, search_term: str = None) -> str:
    """Get Plex server logs.
    
    Args:
        num_lines: Number of log lines (or matches) to retrieve (default: 100)
        log_type: Type of log to retrieve (server, scanner, transcoder, updater) or specific filename/partial match
        start_line: Starting line number to retrieve (0-indexed). If None, retrieves last num_lines.
        list_files: If True, lists all available log files instead of content.
        search_term: Text to search for in the logs. If provided, returns matching lines with line numbers.
        
    Returns:
        String containing log lines, search results, or file list.
    """
    try:
        import zipfile
        import io
        import tempfile
        import os
        import shutil
        import traceback
        import fnmatch
        
        plex = connect_to_plex()
            
        # Download logs from the Plex server
        # This returns a path to a zip file or raw zip data
        logs_path_or_data = plex.downloadLogs()
        
        # Function to process the zip file
        def process_zip(zip_ref):
            all_files = zip_ref.namelist()
            
            # If list_files is requested, just return the list
            if list_files:
                file_list = sorted(all_files)
                return "Available log files:\n" + "\n".join(f"- {f}" for f in file_list)
                
            # Determine which file to read
            log_file_path = None
            
            # 1. Try mapping for known types
            log_type_map = {
                'server': 'Plex Media Server.log',
                'scanner': 'Plex Media Scanner.log',
                'transcoder': 'Plex Transcoder Statistics.log',
                'updater': 'Plex Update Service.log',
                'tuner': 'Plex Tuner Service.log',
                'scanner-deep-analysis': 'Plex Media Scanner Deep Analysis.log',
                'credits': 'Plex Media Scanner Credits.log',
                'chapter-thumbnails': 'Plex Media Scanner Chapter Thumbnails.log',
                'crash-uploader': 'Plex Crash Uploader.log'
            }
            
            target_name = log_type_map.get(log_type.lower(), log_type)
            
            # 2. Try exact match in zip
            if target_name in all_files:
                log_file_path = target_name
            else:
                # 3. Try case-insensitive exact match
                for f in all_files:
                    if f.lower() == target_name.lower():
                        log_file_path = f
                        break
                
                # 4. Try partial match / suffix (e.g. searching for ".1.log")
                if not log_file_path:
                    candidates = []
                    for f in all_files:
                        if target_name.lower() in f.lower():
                            candidates.append(f)
                    
                    if len(candidates) == 1:
                        log_file_path = candidates[0]
                    elif len(candidates) > 1:
                        # Prefer exact suffix match if possible? Or just return the first/shortest?
                        # Let's try to match if the user provided extension like .1.log
                        for c in candidates:
                            if c.endswith(target_name) or c.lower().endswith(target_name.lower()):
                                log_file_path = c
                                break
                        if not log_file_path:
                            # Default to first candidate
                            log_file_path = candidates[0]

            if not log_file_path:
                return f"Could not find log file matching '{log_type}'. Available files:\n" + "\n".join(all_files[:20]) + ("\n..." if len(all_files) > 20 else "")

            # Read the file
            with zip_ref.open(log_file_path) as f:
                content = f.read().decode('utf-8', errors='ignore')
                
            lines = content.splitlines()
            total_lines = len(lines)
            
            # Handle Search
            if search_term:
                matches = []
                search_lower = search_term.lower()
                for i, line in enumerate(lines):
                    if search_lower in line.lower():
                        matches.append(f"Line {i+1}: {line}")
                        
                # Pagination/Limits for search results
                # Only use start_line if provided, otherwise show first X matches? 
                # Or use num_lines to limit count.
                
                total_matches = len(matches)
                if total_matches == 0:
                    return f"No matches found for '{search_term}' in {log_file_path}."
                
                start_idx = start_line if start_line is not None else 0
                end_idx = min(start_idx + num_lines, total_matches)
                
                result_lines = matches[start_idx:end_idx]
                
                header = f"Search results for '{search_term}' in {log_file_path} (Matches {start_idx+1}-{end_idx} of {total_matches}):\n\n"
                return header + "\n".join(result_lines)

            # Handle Standard Line Reading
            if start_line is not None:
                # Specific range requested
                start_idx = max(0, start_line)
                end_idx = min(start_idx + num_lines, total_lines)
                result_lines = lines[start_idx:end_idx]
                range_desc = f"lines {start_idx+1}-{end_idx}"
            else:
                # Tail requested (default)
                # If num_lines >= total, return all. Else return last num_lines
                if num_lines >= total_lines:
                    result_lines = lines
                    range_desc = f"all {total_lines} lines"
                else:
                    result_lines = lines[-num_lines:]
                    range_desc = f"last {len(result_lines)} lines"

            return f"Log: {log_file_path} ({range_desc} of {total_lines}):\n\n" + "\n".join(result_lines)


        # Handle zipfile content based on what we received
        if isinstance(logs_path_or_data, str) and os.path.exists(logs_path_or_data) and logs_path_or_data.endswith('.zip'):
            # We received a path to a zip file
            try:
                with zipfile.ZipFile(logs_path_or_data, 'r') as zip_ref:
                    return process_zip(zip_ref)
            finally:
                # Clean up the downloaded zip if desired
                try:
                    os.remove(logs_path_or_data)
                except:
                    pass
        else:
            # We received the actual data or path to data - process in memory
            if isinstance(logs_path_or_data, str):
                # Check if it looks like a path but failed previous check?
                # The mock/real connect_to_plex might return bytes or path.
                # If it's a string and not a file, treat as bytes?
                # Actually plexapi.downloadLogs() returns url or content? 
                # Let's assume content if not file.
                logs_path_or_data = logs_path_or_data.encode('utf-8')
                
            try:
                # Create an in-memory zip file
                zip_buffer = io.BytesIO(logs_path_or_data)
                with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                    return process_zip(zip_ref)
            except zipfile.BadZipFile:
                # If it's not a zip, maybe it's just raw text? Unlikely for downloadLogs
                return f"Downloaded data is not a valid zip file. Length: {len(logs_path_or_data)}"
        
    except Exception as e:
        return f"Error getting Plex logs: {str(e)}\n{traceback.format_exc()}"

@mcp.tool()
async def server_get_info() -> str:
    """Get detailed information about the Plex server.
    
    Returns:
        Dictionary containing server details including version, platform, etc.
    """
    try:
        plex = connect_to_plex()
        server_info = {
            "version": plex.version,
            "platform": plex.platform,
            "platform_version": plex.platformVersion,
            "updated_at": str(plex.updatedAt) if hasattr(plex, 'updatedAt') else None,
            "server_name": plex.friendlyName,
            "machine_identifier": plex.machineIdentifier,
            "my_plex_username": plex.myPlexUsername,
            "my_plex_mapping_state": plex.myPlexMappingState if hasattr(plex, 'myPlexMappingState') else None,
            "certificate": plex.certificate if hasattr(plex, 'certificate') else None,
            "sync": plex.sync if hasattr(plex, 'sync') else None,
            "transcoder_active_video_sessions": plex.transcoderActiveVideoSessions,
            "transcoder_audio": plex.transcoderAudio if hasattr(plex, 'transcoderAudio') else None,
            "transcoder_video_bitrates": plex.transcoderVideoBitrates,
            "transcoder_video_qualities": plex.transcoderVideoQualities,
            "transcoder_video_resolutions": plex.transcoderVideoResolutions,
            "streaming_brain_version": plex.streamingBrainVersion if hasattr(plex, 'streamingBrainVersion') else None,
            "owner_features": plex.ownerFeatures if hasattr(plex, 'ownerFeatures') else None
        }
        
        # Format server information as JSON
        return json.dumps({"status": "success", "data": server_info}, indent=4)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=4)

@mcp.tool()
async def server_get_bandwidth(timespan: str = None, lan: str = None) -> str:
    """Get bandwidth statistics from the Plex server.
    
    Args:
        timespan: Time span for bandwidth data (months, weeks, days, hours, seconds)
        lan: Filter by local network (true/false)
    
    Returns:
        Dictionary containing bandwidth statistics
    """
    try:
        plex = connect_to_plex()
        
        # Get bandwidth information
        bandwidth_stats = []
        
        if hasattr(plex, 'bandwidth'):
            # Prepare kwargs for bandwidth() call
            kwargs = {}
            
            # Add timespan if provided
            if timespan:
                valid_timespans = ['months', 'weeks', 'days', 'hours', 'seconds']
                if timespan.lower() in valid_timespans:
                    kwargs['timespan'] = timespan.lower()
            
            # Add lan filter if provided
            if lan is not None:
                if lan.lower() == 'true':
                    kwargs['lan'] = True
                elif lan.lower() == 'false':
                    kwargs['lan'] = False
            
            # Call bandwidth with the constructed kwargs
            bandwidth_data = plex.bandwidth(**kwargs)
            
            for bandwidth in bandwidth_data:
                # Each bandwidth object has properties like accountID, at, bytes, deviceID, lan, timespan
                stats = {
                    "account": bandwidth.account().name if bandwidth.account() and hasattr(bandwidth.account(), 'name') else None,
                    "device_id": bandwidth.deviceID if hasattr(bandwidth, 'deviceID') else None,
                    "device_name": bandwidth.device().name if bandwidth.device() and hasattr(bandwidth.device(), 'name') else None,
                    "platform": bandwidth.device().platform if bandwidth.device() and hasattr(bandwidth.device(), 'platform') else None,
                    "client_identifier": bandwidth.device().clientIdentifier if bandwidth.device() and hasattr(bandwidth.device(), 'clientIdentifier') else None,
                    "at": str(bandwidth.at) if hasattr(bandwidth, 'at') else None,
                    "bytes": bandwidth.bytes if hasattr(bandwidth, 'bytes') else None,
                    "is_local": bandwidth.lan if hasattr(bandwidth, 'lan') else None,
                    "timespan (seconds)": bandwidth.timespan if hasattr(bandwidth, 'timespan') else None
                }
                bandwidth_stats.append(stats)
        
        # Format bandwidth information as JSON
        return json.dumps({"status": "success", "data": bandwidth_stats}, indent=4)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=4)

@mcp.tool()
async def server_get_current_resources() -> str:
    """Get resource usage information from the Plex server.
    
    Returns:
        Dictionary containing resource usage statistics
    """
    try:
        plex = connect_to_plex()
        
        # Get resource information
        resources_data = []
        
        if hasattr(plex, 'resources'):
            server_resources = plex.resources()
            
            for resource in server_resources:
                # Create an entry for each resource timepoint
                resource_entry = {
                    "timestamp": str(resource.at) if hasattr(resource, 'at') else None,
                    "host_cpu_utilization": resource.hostCpuUtilization if hasattr(resource, 'hostCpuUtilization') else None,
                    "host_memory_utilization": resource.hostMemoryUtilization if hasattr(resource, 'hostMemoryUtilization') else None,
                    "process_cpu_utilization": resource.processCpuUtilization if hasattr(resource, 'processCpuUtilization') else None,
                    "process_memory_utilization": resource.processMemoryUtilization if hasattr(resource, 'processMemoryUtilization') else None,
                    "timespan": resource.timespan if hasattr(resource, 'timespan') else None
                }
                resources_data.append(resource_entry)
        
        # Format resource information as JSON
        return json.dumps({"status": "success", "data": resources_data}, indent=4)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=4)

@mcp.tool()
async def server_get_butler_tasks() -> str:
    """Get information about Plex Butler tasks.
    
    Returns:
        Dictionary containing information about scheduled and running butler tasks
    """
    try:
        plex = connect_to_plex()
        
        # Get the base URL and token from the Plex connection
        base_url = plex._baseurl
        token = plex._token
        
        # Make a direct API call to the butler endpoint
        url = f"{base_url}/butler"
        headers = {'X-Plex-Token': token, 'Accept': 'application/xml'}
        
        # Disable SSL verification if using https
        verify = False if base_url.startswith('https') else True
        
        response = requests.get(url, headers=headers, verify=verify)
        
        if response.status_code == 200:
            # Parse the XML response
            import xml.etree.ElementTree as ET
            from xml.dom import minidom
            
            try:
                # Try to parse as XML first
                root = ET.fromstring(response.text)
                
                # Extract butler tasks
                butler_tasks = []
                for task_elem in root.findall('.//ButlerTask'):
                    task = {}
                    for attr, value in task_elem.attrib.items():
                        # Convert boolean attributes
                        if value.lower() in ['true', 'false']:
                            task[attr] = value.lower() == 'true'
                        # Convert numeric attributes
                        elif value.isdigit():
                            task[attr] = int(value)
                        else:
                            task[attr] = value
                    butler_tasks.append(task)
                
                # Return the butler tasks directly in the data field
                return json.dumps({"status": "success", "data": butler_tasks}, indent=4)
            except ET.ParseError:
                # Return the raw response if XML parsing fails
                return json.dumps({
                    "status": "error", 
                    "message": "Failed to parse XML response",
                    "raw_response": response.text
                }, indent=4)
        else:
            return json.dumps({
                "status": "error", 
                "message": f"Failed to fetch butler tasks. Status code: {response.status_code}",
                "response": response.text
            }, indent=4)
            
    except Exception as e:
        import traceback
        return json.dumps({
            "status": "error", 
            "message": str(e),
            "traceback": traceback.format_exc()
        }, indent=4)

@mcp.tool()
async def server_get_alerts(timeout: int = 15) -> str:
    """Get real-time alerts from the Plex server by listening on a websocket.
    
    Args:
        timeout: Number of seconds to listen for alerts (default: 15)
    
    Returns:
        Dictionary containing server alerts and their details
    """
    try:
        plex = connect_to_plex()
        
        # Collection for alerts
        alerts_data = []
        
        # Define callback function to process alerts
        def alert_callback(data):
            # Print the raw data to help with debugging
            print(f"Raw alert data received: {data}")
            
            try:
                # Extract alert information from the raw notification data
                # Assuming data is a list/tuple with at least 3 elements as indicated by the log statement
                # Format is likely [type, title, description] or similar
                alert_type = data[0] if len(data) > 0 else "Unknown"
                alert_title = data[1] if len(data) > 1 else "Unknown"
                alert_description = data[2] if len(data) > 2 else "No description"
                
                # Create a simplified single-line text representation of the alert
                alert_text = f"ALERT: {alert_type} - {alert_title} - {alert_description}"
                
                # Print to console in real-time
                print(alert_text)
                
                # Store alert info for JSON response
                alert_info = {
                    "type": alert_type,
                    "title": alert_title,
                    "description": alert_description,
                    "text": alert_text,
                    "raw_data": data  # Include the raw data for complete information
                }
                alerts_data.append(alert_info)
            except Exception as e:
                print(f"Error processing alert data: {e}")
                # Still try to store some information even if processing fails
                alerts_data.append({
                    "error": str(e),
                    "raw_data": str(data)
                })
        
        print(f"Starting alert listener for {timeout} seconds...")
        
        # Start the alert listener
        listener = plex.startAlertListener(alert_callback)
        
        # Wait for the specified timeout period
        await asyncio.sleep(timeout)
        
        # Stop the listener
        listener.stop()
        print(f"Alert listener stopped after {timeout} seconds.")
        
        # Format alerts as JSON
        return json.dumps({"status": "success", "data": alerts_data}, indent=4)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=4)

@mcp.tool()
async def server_run_butler_task(task_name: str) -> str:
    """Manually run a specific Plex Butler task now.
    
    Args:
        task_name: Name of the butler task to run
    
    Returns:
        Success or error message
    """
    try:
        plex = connect_to_plex()
        
        # Call the runButlerTask method directly on the PlexServer object
        # Valid task names: 'BackupDatabase', 'CheckForUpdates', 'CleanOldBundles', 
        # 'DeepMediaAnalysis', 'GarbageCollection', 'GenerateAutoTags', 
        # 'OptimizeDatabase', 'RefreshLocalMedia', 'RefreshPeriodicMetadata', 
        # 'RefreshLibraries', 'UpgradeMediaAnalysis'
        
        # Make a direct API call to run the butler task
        base_url = plex._baseurl
        token = plex._token
        
        # Use the correct URL structure: /butler/{taskName}
        url = f"{base_url}/butler/{task_name}"
        headers = {'X-Plex-Token': token}
        
        # Disable SSL verification if using https
        verify = False if base_url.startswith('https') else True
        
        print(f"Running butler task: {task_name}")
        response = requests.post(url, headers=headers, verify=verify)
        
        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text}")
        
        # Add 202 Accepted to the list of successful status codes
        if response.status_code in [200, 201, 202, 204]:
            return json.dumps({"status": "success", "message": f"Butler task '{task_name}' started successfully"}, indent=4)
        else:
            # For error responses, extract the status code and response text in a more readable format
            error_message = f"Failed to run butler task. Status code: {response.status_code}"
            
            # Try to extract a cleaner error message from the HTML response if possible
            if "<html>" in response.text:
                import re
                # Try to extract the status message from an HTML response (like "404 Not Found")
                title_match = re.search(r'<title>(.*?)</title>', response.text)
                if title_match and title_match.group(1):
                    error_message = f"Failed to run butler task: {title_match.group(1)}"
                    
                # Or try to extract from an h1 tag
                h1_match = re.search(r'<h1>(.*?)</h1>', response.text)
                if h1_match and h1_match.group(1):
                    error_message = f"Failed to run butler task: {h1_match.group(1)}"
            
            return json.dumps({
                "status": "error", 
                "message": error_message
            }, indent=4)
            
    except Exception as e:
        import traceback
        return json.dumps({
            "status": "error", 
            "message": str(e),
            "traceback": traceback.format_exc()
        }, indent=4)