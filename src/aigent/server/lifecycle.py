import os
import signal
from pathlib import Path

PID_FILE = Path.home() / ".aigent" / "server.pid"

def kill_server_process() -> bool:
    """
    Terminates the running Aigent server process if PID file exists.
    Returns True if a process was killed or file cleaned up.
    """
    if not PID_FILE.exists():
        return False
    
    try:
        pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to server (PID {pid}).")
        except ProcessLookupError:
            print(f"Server process {pid} not found.")
        except Exception as e:
            print(f"Error killing server: {e}")
            return False
            
        # Cleanup
        if PID_FILE.exists():
            PID_FILE.unlink()
        return True
        
    except Exception as e:
        print(f"Error reading PID file: {e}")
        return False
