# Documentation

This directory contains all project documentation, organized into three categories:

## Directory Structure

```
docs/
├── GLOSSARY.md          # Project-specific terminology and definitions
├── core/                # Identity, principles, and values
├── standards/           # Code quality and style standards
└── implementation/      # Version-specific technical documentation
```

## Directories

### [`core/`](core/)

The philosophical foundation of the project. Contains documents that define:

- **Who** the project serves
- **Why** it exists
- **What** principles guide development decisions

These documents should rarely change and serve as the "north star" for all other decisions.

### [`standards/`](standards/)

Code quality and style standards that apply across the entire codebase. Covers:

- Type checking requirements
- Documentation standards
- Code style guidelines
- Testing requirements

### [`implementation/`](implementation/)

Version-specific technical documentation. Each subdirectory represents a major version or architectural iteration, containing:

- Architecture overviews
- Design decisions
- Technical specifications
- Implementation patterns

## Files

| File | Description |
|------|-------------|
| [`GLOSSARY.md`](GLOSSARY.md) | Definitions for project-specific terminology |
