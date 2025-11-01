import asyncio
import contextlib
import json
import os

import requests

from . import connect_to_plex, mcp


@mcp.tool()
async def server_get_plex_logs(num_lines: int = 100, log_type: str = "server") -> str:
    """Get Plex server logs.

    Args:
        num_lines: Number of log lines to retrieve
        log_type: Type of log to retrieve (server, scanner, transcoder, updater)
    """
    try:
        import io
        import os
        import traceback
        import zipfile

        plex = connect_to_plex()

        # Map common log type names to the actual file names
        log_type_map = {
            "server": "Plex Media Server.log",
            "scanner": "Plex Media Scanner.log",
            "transcoder": "Plex Transcoder.log",
            "updater": "Plex Update Service.log",
        }

        log_file_name = log_type_map.get(log_type.lower(), log_type)

        # Download logs from the Plex server
        logs_path_or_data = plex.downloadLogs()

        # Handle zipfile content based on what we received
        if (
            isinstance(logs_path_or_data, str)
            and os.path.exists(logs_path_or_data)
            and logs_path_or_data.endswith(".zip")
        ):
            # We received a path to a zip file
            with zipfile.ZipFile(logs_path_or_data, "r") as zip_ref:
                log_content = extract_log_from_zip(zip_ref, log_file_name)

            # Clean up the downloaded zip if desired
            # Ignore errors in cleanup
            with contextlib.suppress(Exception):
                os.remove(logs_path_or_data)
        else:
            # We received the actual data - process in memory
            if isinstance(logs_path_or_data, str):
                logs_path_or_data = logs_path_or_data.encode("utf-8")

            try:
                # Create an in-memory zip file
                zip_buffer = io.BytesIO(logs_path_or_data)
                with zipfile.ZipFile(zip_buffer, "r") as zip_ref:
                    log_content = extract_log_from_zip(zip_ref, log_file_name)
            except zipfile.BadZipFile:
                return f"Downloaded data is not a valid zip file. First 100 bytes: {logs_path_or_data[:100]}"

        # Extract the last num_lines from the log content
        log_lines = log_content.splitlines()
        log_lines = log_lines[-num_lines:] if len(log_lines) > num_lines else log_lines

        result = f"Last {len(log_lines)} lines of {log_file_name}:\n\n"
        result += "\n".join(log_lines)

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
                raise ValueError(
                    f"Could not find log file for type: {log_file_name}. Available files: {', '.join(all_files)}"
                )

    # Read the log file content
    with zip_ref.open(log_file_path) as f:
        log_content = f.read().decode("utf-8", errors="ignore")

    return log_content


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
            "updated_at": str(plex.updatedAt) if hasattr(plex, "updatedAt") else None,
            "server_name": plex.friendlyName,
            "machine_identifier": plex.machineIdentifier,
            "my_plex_username": plex.myPlexUsername,
            "my_plex_mapping_state": plex.myPlexMappingState
            if hasattr(plex, "myPlexMappingState")
            else None,
            "certificate": plex.certificate if hasattr(plex, "certificate") else None,
            "sync": plex.sync if hasattr(plex, "sync") else None,
            "transcoder_active_video_sessions": plex.transcoderActiveVideoSessions,
            "transcoder_audio": plex.transcoderAudio if hasattr(plex, "transcoderAudio") else None,
            "transcoder_video_bitrates": plex.transcoderVideoBitrates,
            "transcoder_video_qualities": plex.transcoderVideoQualities,
            "transcoder_video_resolutions": plex.transcoderVideoResolutions,
            "streaming_brain_version": plex.streamingBrainVersion
            if hasattr(plex, "streamingBrainVersion")
            else None,
            "owner_features": plex.ownerFeatures if hasattr(plex, "ownerFeatures") else None,
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

        if hasattr(plex, "bandwidth"):
            # Prepare kwargs for bandwidth() call
            kwargs = {}

            # Add timespan if provided
            if timespan:
                valid_timespans = ["months", "weeks", "days", "hours", "seconds"]
                if timespan.lower() in valid_timespans:
                    kwargs["timespan"] = timespan.lower()

            # Add lan filter if provided
            if lan is not None:
                if lan.lower() == "true":
                    kwargs["lan"] = True
                elif lan.lower() == "false":
                    kwargs["lan"] = False

            # Call bandwidth with the constructed kwargs
            bandwidth_data = plex.bandwidth(**kwargs)

            for bandwidth in bandwidth_data:
                # Each bandwidth object has properties like accountID, at, bytes, deviceID, lan, timespan
                stats = {
                    "account": bandwidth.account().name
                    if bandwidth.account() and hasattr(bandwidth.account(), "name")
                    else None,
                    "device_id": bandwidth.deviceID if hasattr(bandwidth, "deviceID") else None,
                    "device_name": bandwidth.device().name
                    if bandwidth.device() and hasattr(bandwidth.device(), "name")
                    else None,
                    "platform": bandwidth.device().platform
                    if bandwidth.device() and hasattr(bandwidth.device(), "platform")
                    else None,
                    "client_identifier": bandwidth.device().clientIdentifier
                    if bandwidth.device() and hasattr(bandwidth.device(), "clientIdentifier")
                    else None,
                    "at": str(bandwidth.at) if hasattr(bandwidth, "at") else None,
                    "bytes": bandwidth.bytes if hasattr(bandwidth, "bytes") else None,
                    "is_local": bandwidth.lan if hasattr(bandwidth, "lan") else None,
                    "timespan (seconds)": bandwidth.timespan
                    if hasattr(bandwidth, "timespan")
                    else None,
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

        if hasattr(plex, "resources"):
            server_resources = plex.resources()

            for resource in server_resources:
                # Create an entry for each resource timepoint
                resource_entry = {
                    "timestamp": str(resource.at) if hasattr(resource, "at") else None,
                    "host_cpu_utilization": resource.hostCpuUtilization
                    if hasattr(resource, "hostCpuUtilization")
                    else None,
                    "host_memory_utilization": resource.hostMemoryUtilization
                    if hasattr(resource, "hostMemoryUtilization")
                    else None,
                    "process_cpu_utilization": resource.processCpuUtilization
                    if hasattr(resource, "processCpuUtilization")
                    else None,
                    "process_memory_utilization": resource.processMemoryUtilization
                    if hasattr(resource, "processMemoryUtilization")
                    else None,
                    "timespan": resource.timespan if hasattr(resource, "timespan") else None,
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
        headers = {"X-Plex-Token": token, "Accept": "application/xml"}

        # Disable SSL verification if using https
        verify = not base_url.startswith("https")

        response = requests.get(url, headers=headers, verify=verify)

        if response.status_code == 200:
            # Parse the XML response
            import xml.etree.ElementTree as ET

            try:
                # Try to parse as XML first
                root = ET.fromstring(response.text)

                # Extract butler tasks
                butler_tasks = []
                for task_elem in root.findall(".//ButlerTask"):
                    task = {}
                    for attr, value in task_elem.attrib.items():
                        # Convert boolean attributes
                        if value.lower() in ["true", "false"]:
                            task[attr] = value.lower() == "true"
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
                return json.dumps(
                    {
                        "status": "error",
                        "message": "Failed to parse XML response",
                        "raw_response": response.text,
                    },
                    indent=4,
                )
        else:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Failed to fetch butler tasks. Status code: {response.status_code}",
                    "response": response.text,
                },
                indent=4,
            )

    except Exception as e:
        import traceback

        return json.dumps(
            {"status": "error", "message": str(e), "traceback": traceback.format_exc()}, indent=4
        )


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
                    "raw_data": data,  # Include the raw data for complete information
                }
                alerts_data.append(alert_info)
            except Exception as e:
                print(f"Error processing alert data: {e}")
                # Still try to store some information even if processing fails
                alerts_data.append({"error": str(e), "raw_data": str(data)})

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
        headers = {"X-Plex-Token": token}

        # Disable SSL verification if using https
        verify = not base_url.startswith("https")

        print(f"Running butler task: {task_name}")
        response = requests.post(url, headers=headers, verify=verify)

        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text}")

        # Add 202 Accepted to the list of successful status codes
        if response.status_code in [200, 201, 202, 204]:
            return json.dumps(
                {"status": "success", "message": f"Butler task '{task_name}' started successfully"},
                indent=4,
            )
        else:
            # For error responses, extract the status code and response text in a more readable format
            error_message = f"Failed to run butler task. Status code: {response.status_code}"

            # Try to extract a cleaner error message from the HTML response if possible
            if "<html>" in response.text:
                import re

                # Try to extract the status message from an HTML response (like "404 Not Found")
                title_match = re.search(r"<title>(.*?)</title>", response.text)
                if title_match and title_match.group(1):
                    error_message = f"Failed to run butler task: {title_match.group(1)}"

                # Or try to extract from an h1 tag
                h1_match = re.search(r"<h1>(.*?)</h1>", response.text)
                if h1_match and h1_match.group(1):
                    error_message = f"Failed to run butler task: {h1_match.group(1)}"

            return json.dumps({"status": "error", "message": error_message}, indent=4)

    except Exception as e:
        import traceback

        return json.dumps(
            {"status": "error", "message": str(e), "traceback": traceback.format_exc()}, indent=4
        )
