import os
import signal
from pathlib import Path
import httpx

# Deprecated but kept for cleanup
PID_FILE = Path.home() / ".aigent" / "server.pid"

def kill_server_process(host: str = "127.0.0.1", port: int = 8000) -> bool:
    """
    Terminates the running Aigent server process.
    Strategy:
    1. Query API for PID.
    2. Send SIGTERM.
    3. Cleanup (PID file if exists).
    """
    pid = None
    
    # 1. Try API Discovery
    try:
        url = f"http://{host}:{port}/api/stats"
        resp = httpx.get(url, timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            pid = data.get("pid")
    except Exception:
        pass

    # 2. Try PID File (Legacy/Fallback)
    if not pid and PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except ValueError:
            pass

    if not pid:
        return False

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to server (PID {pid}).")
    except ProcessLookupError:
        print(f"Server process {pid} not found.")
        # Cleanup stale file if we found it there
        if PID_FILE.exists():
            try:
                current_file_pid = int(PID_FILE.read_text().strip())
                if current_file_pid == pid:
                    PID_FILE.unlink()
            except:
                pass
        return False
    except Exception as e:
        print(f"Error killing server: {e}")
        return False
        
    # Cleanup
    if PID_FILE.exists():
        try:
            # Only remove if it matches the PID we just killed
            current_file_pid = int(PID_FILE.read_text().strip())
            if current_file_pid == pid:
                PID_FILE.unlink()
        except:
            pass
            
    return True
