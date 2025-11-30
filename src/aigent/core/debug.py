"""Black Box Debugger.

This module captures execution state (stack frames, local variables) upon
unhandled exceptions and serializes them for post-mortem analysis.
"""

import datetime
import traceback
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import dill as pickle
except ImportError:
    import pickle

from aigent.core.logging import get_logger

logger = get_logger(__name__)

CRASH_DIR = Path.home() / ".aigent" / "crashes"


def dump_crash_state(exception: Exception, context: Optional[Dict[str, Any]] = None) -> str:
    """Serialize the crash state to a file.

    Args:
        exception: The exception that triggered the crash.
        context: The Event Context active at the time of crash.

    Returns:
        The path to the generated crash dump file.
    """
    try:
        CRASH_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"crash_{timestamp}_{type(exception).__name__}.pkl"
        filepath = CRASH_DIR / filename

        # Capture Stack Trace
        tb_list = traceback.extract_tb(exception.__traceback__)

        # Capture Locals from the last frame (if possible)
        last_frame_locals = {}
        if exception.__traceback__:
            # Get the frame object from the traceback
            # tb_frame is the frame object
            last_frame = exception.__traceback__.tb_next
            while last_frame and last_frame.tb_next:
                last_frame = last_frame.tb_next

            if last_frame:
                # Safely copy locals (avoiding unserializable objects if possible)
                # We use repr() for things that might fail pickling as a fallback?
                # For now, let dill handle it.
                last_frame_locals = last_frame.tb_frame.f_locals.copy()

        crash_data = {
            "timestamp": timestamp,
            "exception_type": type(exception).__name__,
            "exception_msg": str(exception),
            "traceback": "".join(traceback.format_tb(exception.__traceback__)),
            "event_context": context,
            "locals": last_frame_locals,
        }

        with open(filepath, "wb") as f:
            pickle.dump(crash_data, f)

        logger.error(f"⚠️ Crash Dump saved to: {filepath}")
        return str(filepath)

    except Exception as e:
        logger.critical(f"Failed to save crash dump: {e}")
        return ""


def load_crash_state(path: str) -> Dict[str, Any]:
    """Load a crash dump for analysis."""
    with open(path, "rb") as f:
        return pickle.load(f)  # type: ignore[no-any-return]
