---
title: Auto-inject DYLD_LIBRARY_PATH for WeasyPrint on macOS
status: accepted
date: 2026-05-06
context: div_legal build_pdfs.py
---

# ADR 0012: Auto-inject DYLD_LIBRARY_PATH for WeasyPrint on macOS

## Context

WeasyPrint depends on Homebrew-installed libraries (pango, cairo, gobject-introspection) on Apple Silicon Macs. Without `DYLD_LIBRARY_PATH=/opt/homebrew/lib`, the import fails with a dylib not found error.

Previously every invocation required the prefix:
```bash
DYLD_LIBRARY_PATH=/opt/homebrew/lib uv run python -m src.scripts.build_pdfs ...
```

This was error-prone and cluttered all INSTRUCTIONS.md files and CLAUDE.md references.

## Decision

Auto-inject the env var at the top of `build_pdfs.py` before importing weasyprint:

```python
import os, platform
if platform.system() == "Darwin" and "/opt/homebrew/lib" not in os.environ.get("DYLD_LIBRARY_PATH", ""):
    os.environ["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib:" + os.environ.get("DYLD_LIBRARY_PATH", "")
```

This is a no-op on Linux/CI and only activates on macOS when the path isn't already set.

## Consequences

- `uv run python -m src.scripts.build_pdfs` works without any prefix
- Any repo importing or copying this pattern should include the same guard
- If Homebrew location changes (e.g., Intel Mac at /usr/local/lib), the guard would need updating
- Applied in: `div_legal/src/scripts/build_pdfs.py`
