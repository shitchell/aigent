"""Centralized logging configuration for Aigent.

This module provides a unified logging system for all Aigent components.
Loggers are organized hierarchically under the 'aigent' namespace.

Usage:
    from aigent.core.logging import get_logger

    logger = get_logger(__name__)  # e.g., 'aigent.interfaces.tui.app'
    logger.debug("Processing event: %s", event_type)
    logger.info("Connected to server")
    logger.warning("Widget not found, skipping update")
    logger.error("Failed to send message: %s", error)

Configuration (in order of precedence):
    1. CLI arguments: --log-level, --log-file
    2. Environment variables: AIGENT_LOG_LEVEL, AIGENT_LOG_FILE
    3. Config file (settings.yaml): log.level, log.file

Log levels:
    - DEBUG: Verbose debugging information
    - INFO: General operational messages (default)
    - WARNING: Potential issues that don't prevent operation
    - ERROR: Errors that affect functionality
    - CRITICAL: Fatal errors
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Root logger name for all Aigent components
ROOT_LOGGER_NAME = "aigent"

# Default log format
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FORMAT_DEBUG = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"

# Date format
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Track if we've already configured the root logger
_configured = False

# Store CLI overrides (set by configure_from_args before config is loaded)
_cli_log_level: Optional[str] = None
_cli_log_file: Optional[str] = None

# Store config file settings (set by configure_from_config after config is loaded)
_config_log_level: Optional[str] = None
_config_log_file: Optional[str] = None


def configure_from_config(log_level: Optional[str] = None, log_file: Optional[str] = None) -> None:
    """Set logging configuration from config file.

    This should be called after config is loaded but before loggers are heavily used.
    Config file settings have lower precedence than CLI args and environment variables.

    Args:
        log_level: Log level string from config (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file from config.
    """
    global _config_log_level, _config_log_file, _configured

    if log_level:
        _config_log_level = log_level.upper()
    if log_file:
        _config_log_file = log_file

    # If already configured, reconfigure with new settings
    if _configured:
        _configured = False
        configure_root_logger()


def configure_from_args(log_level: Optional[str] = None, log_file: Optional[str] = None) -> None:
    """Set logging configuration from CLI arguments.

    This should be called early in main() before any loggers are used.
    CLI args take precedence over environment variables and config file.

    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file.
    """
    global _cli_log_level, _cli_log_file, _configured

    if log_level:
        _cli_log_level = log_level.upper()
    if log_file:
        _cli_log_file = log_file

    # If already configured, reconfigure with new settings
    if _configured:
        _configured = False
        configure_root_logger()


def get_log_level() -> int:
    """Get the configured log level.

    Precedence: CLI args > environment > config file > default (INFO).

    Returns:
        The logging level constant (e.g., logging.DEBUG).
    """
    # CLI args take highest precedence
    if _cli_log_level:
        return getattr(logging, _cli_log_level, logging.INFO)

    # Then environment variable
    env_level = os.environ.get("AIGENT_LOG_LEVEL")
    if env_level:
        return getattr(logging, env_level.upper(), logging.INFO)

    # Then config file
    if _config_log_level:
        return getattr(logging, _config_log_level, logging.INFO)

    # Default
    return logging.INFO


def get_log_file() -> Optional[Path]:
    """Get the configured log file path.

    Precedence: CLI args > environment > config file > None.

    Returns:
        Path to log file, or None if not configured.
    """
    # CLI args take highest precedence
    if _cli_log_file:
        return Path(_cli_log_file).expanduser()

    # Then environment variable
    env_file = os.environ.get("AIGENT_LOG_FILE")
    if env_file:
        return Path(env_file).expanduser()

    # Then config file
    if _config_log_file:
        return Path(_config_log_file).expanduser()

    return None


def configure_root_logger() -> None:
    """Configure the root Aigent logger.

    This sets up handlers for stderr output and optionally file output.
    Should be called once at application startup, but is idempotent.
    """
    global _configured
    if _configured:
        return

    root_logger = logging.getLogger(ROOT_LOGGER_NAME)

    # Clear any existing handlers (in case of reconfiguration)
    root_logger.handlers.clear()

    level = get_log_level()
    root_logger.setLevel(level)

    # Use debug format if DEBUG level is enabled
    log_format = LOG_FORMAT_DEBUG if level == logging.DEBUG else LOG_FORMAT
    formatter = logging.Formatter(log_format, datefmt=DATE_FORMAT)

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    log_file = get_log_file()
    if log_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except (OSError, IOError) as e:
            root_logger.warning("Could not create log file %s: %s", log_file, e)

    # Prevent propagation to root logger (avoids duplicate logs)
    root_logger.propagate = False

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the specified module.

    If the name starts with 'aigent.', it's used as-is.
    Otherwise, 'aigent.' is prepended to create a hierarchical logger.

    Args:
        name: The module name (typically __name__).

    Returns:
        A configured logger instance.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger = get_logger("aigent.interfaces.tui.app")
        >>> logger = get_logger("tui")  # becomes "aigent.tui"
    """
    # Ensure root logger is configured
    configure_root_logger()

    # Normalize the name to be under our namespace
    if not name.startswith(ROOT_LOGGER_NAME):
        # Handle common patterns
        if name.startswith("src.aigent."):
            name = name[4:]  # Remove "src." prefix
        elif not name.startswith("aigent."):
            name = f"{ROOT_LOGGER_NAME}.{name}"

    return logging.getLogger(name)


def set_level(level: int) -> None:
    """Dynamically change the log level for all Aigent loggers.

    Args:
        level: The logging level constant (e.g., logging.DEBUG).
    """
    root_logger = logging.getLogger(ROOT_LOGGER_NAME)
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        handler.setLevel(level)


# Convenience exports
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
