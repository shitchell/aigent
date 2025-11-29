"""Centralized logging configuration for Aigent.

This module provides a unified logging system with verbose debug capabilities
and rotating file handlers.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Constants
ROOT_LOGGER_NAME = "aigent"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
# Verbose debug format including file/line for precise tracing
LOG_FORMAT_DEBUG = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Default Log Path
DEFAULT_LOG_DIR = Path.home() / ".aigent" / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "aigent.log"

def get_logger(name: str) -> logging.Logger:
    """Get a logger for the specified module.

    Args:
        name: The module name (typically __name__).

    Returns:
        A configured logger instance.
    """
    if not name.startswith(ROOT_LOGGER_NAME):
        name = f"{ROOT_LOGGER_NAME}.{name}"
    return logging.getLogger(name)

def configure_logging(
    level_str: str = "INFO",
    log_file: Optional[Path] = None,
    verbose: bool = False
) -> None:
    """Configure the root logger.

    Args:
        level_str: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_file: Path to the log file. Defaults to ~/.aigent/logs/aigent.log.
        verbose: If True, forces DEBUG level and verbose formatting.
    """
    root_logger = logging.getLogger(ROOT_LOGGER_NAME)
    root_logger.handlers.clear()
    
    # Determine Level
    if verbose:
        level = logging.DEBUG
    else:
        level = getattr(logging, level_str.upper(), logging.INFO)
    
    root_logger.setLevel(level)
    
    # Determine Format
    formatter = logging.Formatter(
        LOG_FORMAT_DEBUG if level == logging.DEBUG else LOG_FORMAT,
        datefmt=DATE_FORMAT
    )

    # 1. Console Handler (Stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. File Handler (Rotating)
    target_file = log_file or DEFAULT_LOG_FILE
    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            target_file,
            maxBytes=10 * 1024 * 1024, # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
    except Exception as e:
        # Fallback if we can't write to disk
        console_handler.setFormatter(formatter) 
        root_logger.warning(f"Failed to setup file logging at {target_file}: {e}")

    # Prevent propagation to avoid double logging if root handlers are set elsewhere
    root_logger.propagate = False
