# Preference: Documentation (SOFT)

**Severity:** WARN — advisory

## Conventions

1. **Every repo needs a README.md** with at minimum: project name, one-line description, install instructions, usage example.
2. **CLI tools must include command examples** in README or auto-generated docs section.
3. **Use auto-doc markers** for generated sections:
   ```markdown
   <!-- BEGIN AUTO CLI DOCS -->
   ...
   <!-- END AUTO CLI DOCS -->
   ```
4. **Generated sections are machine-owned.** Prose sections are human-owned. Scripts must not overwrite prose.
5. **Stale docs should be flagged.** If source changes but docs haven't been regenerated, report as INFO.

## Enforcement

- `devctl audit` checks for README presence and minimum sections
- `devctl docs refresh` regenerates auto sections
