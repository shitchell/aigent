"""Plugin Loader.

Scans and imports plugins to register their event handlers.
"""

import importlib.util
import os
import sys
from pathlib import Path

from aigent.core.logging import get_logger
from aigent.core.profiles import profiles

logger = get_logger(__name__)

def load_plugins() -> None:
    """Load plugins from the configured directory."""
    # Ensure config is loaded
    if not profiles.loaded:
        profiles.load()
        
    plugin_dir_str = profiles.config.settings.plugin_dir
    plugin_dir = Path(plugin_dir_str).expanduser()
    
    if not plugin_dir.exists():
        logger.debug(f"Plugin directory {plugin_dir} does not exist.")
        return

    logger.info(f"Loading plugins from {plugin_dir}")
    
    for item in plugin_dir.iterdir():
        if item.suffix == ".py":
            _load_module(item)
        elif item.is_dir():
            # Check for __init__.py or main.py
            if (item / "main.py").exists():
                _load_module(item / "main.py")
            elif (item / "__init__.py").exists():
                _load_module(item / "__init__.py")

def _load_module(path: Path) -> None:
    try:
        module_name = f"aigent.plugins.{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            logger.info(f"Loaded plugin: {path.name}")
    except Exception as e:
        logger.error(f"Failed to load plugin {path}: {e}")
