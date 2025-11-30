# Specification: Debug System (Black Box)

**Module:** `src.aigent.core.debug`

## Overview
The Debug System captures the full execution state of the application at the moment of an unhandled exception, ensuring that ephemeral async states are not lost.

## Mechanism

### 1. Trigger
The `Dispatcher` catches an exception inside an event handler. It calls `dump_crash_state(exception, context)`.

### 2. Capture (`dill`/`pickle`)
The system captures:
*   **Timestamp:** When it happened.
*   **Exception:** Type and Message.
*   **Traceback:** The full stack trace string.
*   **Event Context:** The data payload of the event that caused the crash.
*   **Locals:** The local variables (`f_locals`) of the stack frame where the error occurred.

### 3. Storage
*   **Location:** `~/.aigent/crashes/`
*   **Format:** `.pkl` (Binary Pickle)
*   **Naming:** `crash_{YYYYMMDD_HHMMSS}_{ExceptionType}.pkl`

## Analysis
To analyze a crash dump:
1.  (Future Feature) Use `aigent debug last` CLI command.
2.  Load the pickle in a python script using `load_crash_state(path)`.
3.  Feed the `locals` and `traceback` to an LLM to diagnose the root cause.
