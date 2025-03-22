from modules import mcp, connect_to_plex
import os

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