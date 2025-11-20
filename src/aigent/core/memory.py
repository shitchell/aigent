import aiofiles
from pathlib import Path
from typing import List

class MemoryLoader:
    """
    Responsible for loading the static context files (system prompts) 
    from the three standard locations.
    """
    
    def __init__(self, agent_name: str = "AIGENT"):
        # 1. Local directory ./.aigent/AIGENT.md
        self.local_path = Path.cwd() / ".aigent" / f"{agent_name}.md"
        
        # 2. User home ~/.aigent/AIGENT.md
        self.user_path = Path.home() / ".aigent" / f"{agent_name}.md"
        
        # 3. System /etc/aigent/AIGENT.md
        self.system_path = Path("/etc/aigent") / f"{agent_name}.md"

    async def load_context(self) -> str:
        """
        Asynchronously reads all exists context files and concatenates them.
        Order: System -> User -> Local (Local overrides/appends to others)
        """
        contents: List[str] = []
        
        # We load in specific order: System (General) -> User (Personal) -> Local (Project specific)
        paths = [self.system_path, self.user_path, self.local_path]
        
        for path in paths:
            if path.exists() and path.is_file():
                try:
                    async with aiofiles.open(path, mode='r') as f:
                        content = await f.read()
                        if content.strip():
                            contents.append(f"--- Context from {path} ---\n{content}\n")
                except Exception as e:
                    # We log but don't crash if a file is unreadable
                    contents.append(f"!--- Error reading {path}: {e} ---!\n")

        return "\n".join(contents)

    async def read_file_content(self, path: str, base_path: Path) -> str:
        """
        Reads a single file, resolving path relative to base_path or home dir.
        """
        try:
            p = Path(path)
            if path.startswith("~"):
                p = p.expanduser()
            elif not p.is_absolute():
                p = base_path / p
            
            if not p.exists():
                return f"!--- Warning: File not found: {p} ---!\n"

            async with aiofiles.open(p, mode='r') as f:
                return await f.read()
        except Exception as e:
            return f"!--- Error reading {path}: {e} ---!\n"

    async def load_from_paths(self, paths: List[str], base_path: Path) -> str:
        """
        Loads multiple files and concatenates content.
        """
        contents = []
        for path in paths:
            content = await self.read_file_content(path, base_path)
            if content.strip():
                contents.append(f"--- Context from {path} ---\n{content}\n")
        return "\n".join(contents)
