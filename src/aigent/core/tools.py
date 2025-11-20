from langchain_core.tools import tool
import subprocess
import os
from pathlib import Path
import difflib
from typing import Optional
from aigent.core.profiles import ProfileManager

def validate_path(p: Path) -> Optional[str]:
    """
    Validates that the path is within allowed working directories.
    Returns Error string if invalid, None if valid.
    """
    try:
        # Resolve absolute path of target
        abs_path = p.resolve()
        
        # Get allowed dirs from config
        # Note: ProfileManager is a singleton-ish (loads from same config file)
        pm = ProfileManager()
        # Ensure loaded (might duplicate load if not careful, but ProfileManager handles it gracefully usually)
        # Actually ProfileManager logic: if not loaded, returns empty config?
        # We assume it's initialized by the time tools run.
        # If config not loaded, fallback to CWD (safe default).
        
        allowed_dirs = pm.config.allowed_work_dirs or ["."]
        
        # Check if path matches ANY allowed root
        is_allowed = False
        for allowed in allowed_dirs:
            root = Path(allowed).expanduser().resolve()
            if abs_path.is_relative_to(root):
                is_allowed = True
                break
        
        if not is_allowed:
            return f"Error: Access Denied. Path '{p}' is outside the allowed working directories: {allowed_dirs}"
            
        return None
    except Exception as e:
        return f"Error validating path: {e}"

@tool
def fs_read(path: str) -> str:
    """
    Reads the content of a file from the local filesystem.

    Args:
        path (str): The relative or absolute path to the file to read.

    Returns:
        str: The text content of the file.

    Raises:
        Exception: If the file does not exist or cannot be read.
    """
    try:
        p = Path(path).expanduser()
        
        # Security Check
        error = validate_path(p)
        if error:
            return error

        if not p.exists():
            return f"Error: File {path} does not exist."
        return p.read_text()
    except Exception as e:
        return f"Error reading file: {e}"

@tool
def fs_write(path: str, content: str, append: bool = False) -> str:
    """
    Writes content to a file in the local filesystem.

    Args:
        path (str): The destination file path.
        content (str): The text content to write.
        append (bool): If True, appends to the file instead of overwriting. Defaults to False.

    Returns:
        str: A success message indicating the write mode.

    Raises:
        Exception: If the file cannot be written to.
    """
    try:
        p = Path(path).expanduser()
        
        # Security Check
        error = validate_path(p)
        if error:
            return error

        mode = "a" if append else "w"
        with open(p, mode) as f:
            f.write(content)
        return f"Successfully wrote to {path} (mode={mode})"
    except Exception as e:
        return f"Error writing file: {e}"

@tool
def fs_patch(
    path: str, 
    target: str, 
    replacement: str, 
    start_line: int = 1, 
    end_line: int = -1
) -> str:
    """
    Replaces specific text in a file, optionally scoped to a line range, and returns a diff.

    Args:
        path (str): The file to modify.
        target (str): The exact text content to be replaced. Must match exactly.
        replacement (str): The new text content.
        start_line (int): The 1-based line number to start searching from. Defaults to 1.
        end_line (int): The 1-based line number to stop searching at. Defaults to -1 (end of file).

    Returns:
        str: A success message including a unified diff of the changes.

    Raises:
        Exception: If the target text is not found within the specified range.
    """
    try:
        p = Path(path).expanduser()
        
        # Security Check
        error = validate_path(p)
        if error:
            return error

        if not p.exists():
            return f"Error: File {path} not found."
            
        original_content = p.read_text()
        lines = original_content.splitlines(keepends=True)
        
        # Calculate line indices (0-based)
        start_idx = max(0, start_line - 1)
        end_idx = len(lines) if end_line == -1 else end_line
        
        # Extract the segment to search within
        segment_lines = lines[start_idx:end_idx]
        segment_text = "".join(segment_lines)
        
        if target not in segment_text:
            return (
                f"Error: Target text not found in lines {start_line}-{end_line} of {path}. "
                "Please ensure exact match (whitespace matters)."
            )
            
        # Perform replacement on the segment only
        # We only replace the FIRST occurrence within the scope to be safe
        new_segment_text = segment_text.replace(target, replacement, 1)
        
        # Reconstruct full file content
        new_lines = lines[:start_idx] + new_segment_text.splitlines(keepends=True) + lines[end_idx:]
        new_content = "".join(new_lines)
        
        p.write_text(new_content)
        
        # Generate Diff
        diff = difflib.unified_diff(
            original_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=""
        )
        
        diff_text = "\n".join(list(diff))
        return f"Successfully patched {path}.\n\nDiff:\n{diff_text}"
        
    except Exception as e:
        return f"Error patching file: {e}"

@tool
def bash_execute(command: str) -> str:
    """
    Executes a bash command on the local system.

    Args:
        command (str): The bash command to execute.

    Returns:
        str: The combined STDOUT and STDERR of the command.

    Raises:
        Exception: If the command fails or times out.
    """
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=30
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error executing command: {e}"
