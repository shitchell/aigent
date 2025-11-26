# Unified Architecture Cleanup Steps

## Overview
Remove extraneous bugfix attempts from `feat/unified-client-server` while preserving real features.

---

## Phase 1: Create Clean Branch

- [ ] Create new branch from unified architecture base: `git checkout -b feat/final-cleanup 8179699`

---

## Phase 2: Cherry-Pick Essential Features

- [ ] Server management commands: `git cherry-pick 43294d3`
- [ ] Ephemeral CLI sessions: `git cherry-pick 1a14f22`
- [ ] PID discovery via API: `git cherry-pick 931aa16`
- [ ] Version flag (--version): `git cherry-pick 1af682c`

---

## Phase 3: Apply The Real Fix

- [ ] Apply Codex's `ready_for_input` synchronization fix from `codex-cli-chat-messages` branch
  - Key file: `src/aigent/interfaces/cli.py`
  - Added `ready_for_input = asyncio.Event()` for flow control
  - Ensures prompt only appears after FINISH event
  - `patch_stdout()` scoped only around prompt operations

---

## Phase 4: Verify

- [ ] Run unit tests: `pytest tests/unit/ -v`
- [ ] Run integration tests: `pytest tests/integration/ --run-integration -v`
- [ ] Run E2E tests: `pytest tests/e2e/ --e2e -v`
- [ ] Run type checker: `./scripts/strict_type_check.sh`
- [ ] Manual smoke test: `aigent chat` and verify clean output

---

## Phase 5: Cleanup

- [ ] Remove any stray debug files (script recordings, logs)
- [ ] Ensure no Rich library imports anywhere
- [ ] Verify system prompts don't have unnecessary ANSI instructions
- [ ] Final commit and push

---

## What To Keep

| Feature | Commit | Description |
|---------|--------|-------------|
| Unified architecture | `8179699` | Base WebSocket client-server |
| Server commands | `43294d3` | /kill, server management |
| Ephemeral sessions | `1a14f22` | Random session IDs for CLI |
| PID discovery | `931aa16` | API-based server discovery |
| Version flag | `1af682c` | `--version` CLI option |
| Codex fix | `af9a768` | `ready_for_input` sync |

---

## What To Remove

| Issue | Description |
|-------|-------------|
| Rich library | Caused original rendering bugs |
| ANSI prompt instructions | Failed fix attempt - not needed |
| print vs print_formatted_text iterations | Multiple failed attempts |
| Excessive patch_stdout scoping | Fixed by Codex's approach |

---

## Known Acceptable State

The CLI currently outputs some escape sequences (`\x1b[0m`, `\x1b[?7h`) between tokens. This is:
- **Stable** - consistent behavior
- **Acceptable** - marked as warning in tests
- **Technical debt** - to be cleaned up later

Tests extract only the agent's response and validate that substring.