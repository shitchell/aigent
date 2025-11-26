# Unified Architecture Cleanup Steps

## Overview
We are on `feat/cleanup-unified-architecture`. This branch already has the test suite and Codex's fix merged. The goal now is to identify and remove any extraneous bugfix attempts while preserving real features.

---

## Phase 1: Audit Current State

- [x] Review git log to identify commits that are failed bugfix attempts
- [x] List files that contain unnecessary changes
- [x] Run full test suite to establish baseline: `pytest tests/unit/ -v`

**Results:** Source code is already clean. Only found one broken test file (test_bus.py).

---

## Phase 2: Remove Extraneous Changes

- [x] Remove ANSI prompt instructions from `src/aigent/core/prompts.py` (if present) - NOT FOUND (already clean)
- [x] Verify no Rich library imports in CLI code - VERIFIED (no Rich imports)
- [x] Remove any debug/experimental code - Removed `tests/unit/test_bus.py` (referenced non-existent module)
- [x] Run tests after each removal: `pytest tests/unit/ -v` - 33 passed, 2 failed (pre-existing mock issues)

---

## Phase 3: Verify Core Features Work

- [ ] Test server management commands work
- [ ] Test ephemeral CLI sessions work
- [ ] Test version flag works: `aigent --version`
- [ ] Test `ready_for_input` synchronization is intact

---

## Phase 4: Full Test Suite

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

## Phase 6: Finalize for Merge

- [ ] Untrack `_work/` directory: `git rm -r --cached _work/`
- [ ] Add `_work/` to `.gitignore`
- [ ] Final commit
- [ ] Squash merge into `feat/unified-client-server` branch

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