# Unified Architecture Cleanup - Handoff Document

## Purpose
This directory contains working files for cleaning up the `feat/unified-client-server` branch, removing failed bugfix attempts while preserving the real features.

---

## Background Story

### The Original Problem
The `feat/unified-client-server` branch introduced a WebSocket-based client-server architecture for Aigent. After the initial implementation, severe CLI rendering bugs appeared:
- Character-by-character display with escape sequences
- Terminal control sequence artifacts (`?[?25h`, `?[?25l`)
- Disappearing text with carriage returns
- Excessive blank lines and cursor movements

### The Debugging Journey
Multiple fix attempts were made (all failed):
1. Removing Rich library - helped but didn't solve it
2. Switching print methods - didn't help
3. Token buffering - didn't help
4. System prompt changes about ANSI - didn't help
5. `patch_stdout()` scope changes - partially helped

### The Real Fix
**Codex** found the actual solution: **event synchronization** using `ready_for_input = asyncio.Event()`. The race condition was between:
- WebSocket listener streaming tokens
- Prompt trying to redraw for input

The fix ensures the prompt ONLY appears after the FINISH event is received.

---

## Current State

### Branch: `feat/cleanup-unified-architecture`
This branch has:
- All the test infrastructure we built
- The comprehensive test suite
- The Codex fix merged in
- BUT also contains all the failed fix attempts we want to remove

### Branch: `feat/unified-client-server`
The original feature branch with all the cruft.

### Branch: `codex-cli-chat-messages`
Contains Codex's working fix (commit `af9a768`).

---

## Key Files

### Test Suite (KEEP - copy to clean branch)
```
tests/
├── unit/
│   ├── test_cli_rendering.py      # 8 tests - CLI artifact prevention
│   ├── test_websocket_logic.py    # 9 tests - WebSocket protocol
│   ├── test_server_lifecycle.py   # Server shutdown tests
│   └── test_persistence.py        # Session persistence
├── integration/
│   ├── test_server_startup.py     # 7 tests - Server lifecycle
│   └── test_session_switching.py  # 6 tests - Session management
├── e2e/
│   ├── test_cli_web_sync.py       # Full CLI↔Web sync
│   ├── test_cli_asyncio.py        # CLI subprocess tests
│   ├── test_cli_golden.py         # Golden file comparison
│   └── test_cli_artifacts.py      # Artifact detection
└── conftest.py                    # Shared fixtures
```

### Scripts (KEEP)
```
scripts/
├── strict_type_check.sh    # Ultra-strict mypy + docstrings
└── run_tests.sh            # Test runner
```

### Documentation (KEEP)
```
docs/
├── testing_plan.md         # Test strategy
└── type_standards.md       # Type annotation guide
```

---

## Key Technical Details

### The `ready_for_input` Pattern
```python
# In run_cli():
ready_for_input = asyncio.Event()
ready_for_input.set()  # Initially ready

# Before sending message:
ready_for_input.clear()
await ws.send(user_input)

# In ws_listener(), on FINISH event:
ready_for_input.set()

# Before showing prompt:
await ready_for_input.wait()
with patch_stdout():
    user_input = await session.prompt_async(prompt_text)
```

### Escape Sequence Testing
Tests extract ONLY the agent's response (regex: `/Test.*confirmed/`) and check that substring. Allowed sequences (warning, not fail):
- `\x1b[0m` - Reset formatting
- `\x1b[?7h` - Enable line wrap

Still FAIL on:
- `\r` - Carriage returns
- `\x1b[nA/B/C/D` - Cursor movement
- `\x1b[2K` - Clear line

---

## Running Tests

```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ --run-integration -v

# E2E tests (costs LLM tokens!)
pytest tests/e2e/ --e2e -v

# All tests
pytest --e2e --run-integration -v

# Type checking
./scripts/strict_type_check.sh
```

---

## Commits Reference

| Commit | Description | Keep? |
|--------|-------------|-------|
| `8179699` | Unified client-server architecture | ✅ BASE |
| `43294d3` | Server management commands | ✅ YES |
| `1a14f22` | Ephemeral CLI sessions | ✅ YES |
| `931aa16` | PID discovery via API | ✅ YES |
| `1af682c` | Version flag | ✅ YES |
| `af9a768` | Codex's ready_for_input fix | ✅ YES |
| `5fed547` | ANSI prompt instructions | ❌ NO |
| `8c71a62` | patch_stdout scope attempt | ❌ NO |
| Various | Rich library removal iterations | ❌ NO |

---

## Next Steps

See `STEPS.md` for the detailed checklist.

The general approach:
1. Create fresh branch from `8179699`
2. Cherry-pick only the essential commits
3. Apply Codex's fix
4. Copy over the test suite
5. Run all tests to verify
6. Clean up and commit

---

## Files in This Directory

- `README.md` - This file
- `STEPS.md` - Cleanup checklist
- (Add logs, reports, scratch files as needed)

---

## Contact

This cleanup was planned during a debugging session that identified:
- Root cause: async race condition between output and input
- Solution: event-based synchronization
- Tests: comprehensive suite to prevent regression

Good luck! 🚀