# Standards

This directory contains code quality and style standards that apply across the entire codebase. These documents define the "how" of writing code—requirements that all contributors must follow.

## Purpose

Standards documentation establishes:

- **Type checking** requirements and patterns
- **Documentation** expectations (docstrings, comments)
- **Code style** conventions
- **Testing** requirements

## Files

| File | Description |
|------|-------------|
| [`type_standards.md`](type_standards.md) | Type annotation requirements, patterns, and common fixes |

## Adding New Standards

When adding a new standards document:

1. Keep it focused on one topic (e.g., "error handling", "logging", "testing")
2. Include concrete examples of correct and incorrect code
3. Explain the *why* behind requirements, not just the *what*
4. Reference any tooling that enforces the standard (linters, type checkers)

## Enforcement

Standards should be enforced automatically where possible:

- **Type standards** → `mypy --strict`
- **Code style** → linters, formatters
- **Documentation** → doc coverage tools

Manual review catches what automation cannot, but automation should be the first line of defense.
