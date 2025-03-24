import time
import os
import sys
import subprocess
import argparse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Default paths and configuration
SERVER_PATH = os.getcwd()  # Current working directory
MODULES_PATH = os.path.join(SERVER_PATH, "modules")  # Modules subdirectory
SERVER_MODULE = "plex_mcp_server"  # Correct module name

class MCPServerHandler(FileSystemEventHandler):
    def __init__(self, transport=None, host=None, port=None):
        self.process = None
        self.transport = transport
        self.host = host
        self.port = port
        self.start_server()
    
    def start_server(self):
        if self.process:
            print("Forcefully stopping server...")
            try:
                # First try SIGTERM
                self.process.terminate()
                
                # Give it a short time to terminate
                for _ in range(3):
                    if self.process.poll() is not None:
                        break  # Process terminated
                    time.sleep(0.1)
                
                # If still running, force kill
                if self.process.poll() is None:
                    print("Server still running, killing forcefully...")
                    self.process.kill()
                    
                # Wait for process to be fully killed
                self.process.wait()
            except Exception as e:
                print(f"Error stopping server: {e}")
                
            # In case the process is still running, try one more approach (platform specific)
            try:
                if self.process.poll() is None and hasattr(os, 'killpg'):
                    import signal
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except Exception:
                pass
        
        command = [sys.executable, "-m", SERVER_MODULE]
        
        # Add command line arguments if provided
        if self.transport:
            command.extend(["--transport", self.transport])
        if self.host:
            command.extend(["--host", self.host])
        if self.port:
            command.extend(["--port", str(self.port)])
        
        print(f"Starting server with command: {' '.join(command)}")
        # Create the process in its own process group so we can kill it and all its children
        if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') and sys.platform == 'win32':
            # Windows-specific flag
            self.process = subprocess.Popen(
                command, 
                cwd=SERVER_PATH, 
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            # Unix-based systems
            self.process = subprocess.Popen(
                command, 
                cwd=SERVER_PATH, 
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
    
    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f"Change detected in {event.src_path}")
            self.start_server()

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Watch for changes in MCP server files and restart the server")
    parser.add_argument("--transport", help="Transport type (e.g., http, websocket)")
    parser.add_argument("--host", help="Host address to bind to")
    parser.add_argument("--port", help="Port to bind to")
    args = parser.parse_args()
    
    # Create event handler with provided arguments
    event_handler = MCPServerHandler(
        transport=args.transport,
        host=args.host,
        port=args.port
    )
    
    # Set up observers for both main directory and modules subdirectory
    observer = Observer()
    observer.schedule(event_handler, SERVER_PATH, recursive=False)
    
    # Make sure modules directory exists before watching it
    if os.path.exists(MODULES_PATH) and os.path.isdir(MODULES_PATH):
        observer.schedule(event_handler, MODULES_PATH, recursive=True)
    else:
        print(f"Warning: Modules directory {MODULES_PATH} not found, only watching main directory")
    
    observer.start()
    
    print(f"Watching for changes in {SERVER_PATH} and {MODULES_PATH} (if exists)")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping watcher...")
        observer.stop()
        if event_handler.process:
            print("Forcefully stopping server...")
            try:
                # Try SIGTERM first
                event_handler.process.terminate()
                
                # Give it a short time to terminate
                for _ in range(3):
                    if event_handler.process.poll() is not None:
                        break
                    time.sleep(0.1)
                
                # If still running, force kill
                if event_handler.process.poll() is None:
                    print("Server still running, killing forcefully...")
                    event_handler.process.kill()
                    
                # Try process group kill as a last resort
                if event_handler.process.poll() is None and hasattr(os, 'killpg'):
                    import signal
                    os.killpg(os.getpgid(event_handler.process.pid), signal.SIGKILL)
            except Exception as e:
                print(f"Error while stopping server: {e}")
    observer.join()