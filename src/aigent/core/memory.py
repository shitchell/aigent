import aiofiles
from pathlib import Path
from typing import List

class MemoryLoader:
    """
    Responsible for loading the static context files (system prompts) 
    from the three standard locations.
    """
    
    def __init__(self, agent_name: str = "MYAGENT"):
        # 1. Local directory ./.aigent/MYAGENT.md
        self.local_path = Path.cwd() / ".aigent" / f"{agent_name}.md"
        
        # 2. User home ~/.aigent/MYAGENT.md
        self.user_path = Path.home() / ".aigent" / f"{agent_name}.md"
        
        # 3. System /etc/aigent/MYAGENT.md
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
