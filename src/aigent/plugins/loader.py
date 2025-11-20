import importlib.util
import sys
import os
from pathlib import Path
from typing import List, Dict, Any
from langchain_core.tools import BaseTool
from aigent.core.schemas import AgentConfig

class PluginLoader:
    def __init__(self, plugin_dir: str = "~/.aigent/tools"):
        self.plugin_dir = Path(plugin_dir).expanduser()
        self.loaded_tools: Dict[str, BaseTool] = {}

    def load_plugins(self, allowed_tools: List[str]) -> List[BaseTool]:
        """
        Scans the plugin directory and loads tools.
        :param allowed_tools: List of tool names to allow, or ["*"] for all.
        """
        if not self.plugin_dir.exists():
            return []

        # Iterate over subdirectories in ~/.aigent/tools/
        for item in self.plugin_dir.iterdir():
            if item.is_dir():
                self._load_plugin_from_dir(item)

        # Filter tools based on allowed list
        if "*" in allowed_tools:
            final_tools = list(self.loaded_tools.values())
        else:
            final_tools = [
                tool for name, tool in self.loaded_tools.items() 
                if name in allowed_tools
            ]
            
        print(f"  - Loaded {len(final_tools)} tools from {self.plugin_dir}")
        return final_tools

    def _load_plugin_from_dir(self, plugin_path: Path) -> None:
        main_file = plugin_path / "main.py"
        if not main_file.exists():
            return

        plugin_name = plugin_path.name
        
        # Dynamic import logic
        spec = importlib.util.spec_from_file_location(
            f"aigent.plugins.dynamic.{plugin_name}", 
            main_file
        )
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"aigent.plugins.dynamic.{plugin_name}"] = module
        
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Error loading plugin '{plugin_name}': {e}")
            return

        # Scan module for LangChain tools
        # We look for objects that are instances of BaseTool (which @tool produces)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, BaseTool):
                # We found a tool!
                # Use the function name or the tool's name as the key
                self.loaded_tools[attr.name] = attr
