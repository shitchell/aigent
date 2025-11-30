"""Core Tool Definitions.

Defines the standard tools available to the Agent.
"""

import asyncio
import difflib
import os
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

# Reuse the validation logic from V1 (re-typed for strictness)
# Note: ProfileManager is needed for allowed_work_dirs.
# I'll create a minimal config/profile access later.
# For now, hardcode "." or read env?
# Let's rebuild ProfileManager quickly in core/profiles.py?
# Yes, we need config.


def validate_path(p: Path) -> Optional[str]:
    # Placeholder for Config-based validation
    # For V2 MVP, we default to CWD restriction
    try:
        abs_path = p.resolve()
        cwd = Path.cwd().resolve()
        if not abs_path.is_relative_to(cwd):
            return f"Error: Access Denied. Path '{p}' is outside CWD."
        return None
    except Exception as e:
        return f"Error validating path: {e}"


@tool("fs_read")
def fs_read(path: str) -> str:
    """Reads the content of a file from the local filesystem."""
    try:
        p = Path(path).expanduser()
        if err := validate_path(p):
            return err
        if not p.exists():
            return f"Error: File {path} does not exist."
        return p.read_text()
    except Exception as e:
        return f"Error reading file: {e}"


@tool("fs_write")
def fs_write(path: str, content: str, append: bool = False) -> str:
    """Writes content to a file in the local filesystem."""
    try:
        p = Path(path).expanduser()
        if err := validate_path(p):
            return err
        mode = "a" if append else "w"
        with open(p, mode) as f:
            f.write(content)
        return f"Successfully wrote to {path} (mode={mode})"
    except Exception as e:
        return f"Error writing file: {e}"


@tool("fs_patch")
def fs_patch(path: str, target: str, replacement: str) -> str:
    """Replaces specific text in a file."""
    try:
        p = Path(path).expanduser()
        if err := validate_path(p):
            return err
        if not p.exists():
            return f"Error: File {path} not found."

        content = p.read_text()
        if target not in content:
            return "Error: Target text not found in file."

        new_content = content.replace(target, replacement, 1)
        p.write_text(new_content)

        # Diff
        diff = difflib.unified_diff(
            content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
        return "\n".join([line for line in diff if not line.startswith(("---", "+++"))])
    except Exception as e:
        return f"Error patching file: {e}"


@tool("bash_execute")
async def bash_execute(command: str) -> str:
    """Executes a bash command asynchronously."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode() if stdout else ""
            if stderr:
                output += f"\nSTDERR:\n{stderr.decode()}"
            return output
        except asyncio.TimeoutError:
            proc.kill()
            return "Error: Command timed out."
    except Exception as e:
        return f"Error executing command: {e}"
