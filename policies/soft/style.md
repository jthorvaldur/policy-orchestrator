# Preference: Code Style (SOFT)

**Severity:** WARN — advisory

## Conventions

1. **Use conventional commits.** Format: `type: description` where type is one of: init, feat, fix, refactor, docs, test, ci, chore.
2. **Python: use uv for package management.** Prefer `uv` over pip, poetry, pipenv.
3. **Python: use ruff for linting and formatting.** Prefer ruff over black, flake8, isort.
4. **Type hints encouraged.** Python code should use type annotations for function signatures.
5. **Prefer snake_case for Python, camelCase for JavaScript/TypeScript.**

## Enforcement

- `devctl audit` reports missing linter config as WARN
- No CI failures for style-only issues
