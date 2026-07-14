---
sub_spec_id: SS-12
phase: run
depends_on: ['SS-07']
dispatch: factory
wave: 3
---

# SS-12 — Optional research dependency extra

## Context
Declare an optional-deps extra so scoring/dedup/OCR libs install on request without becoming core
requirements. The **root** `pyproject.toml` governs `uv sync` (red-team C-3). Core `dependencies`
must stay unchanged; SS-07/SS-08 import numpy/Pillow lazily.

## Implementation Steps
1. **Modify** root `pyproject.toml`: add
   `[project.optional-dependencies]\nresearch = ["numpy>=1.26", "Pillow>=10.0", "pytesseract>=0.3"]`.
   Leave the core `dependencies` array untouched.
2. **Verify** parse + core install:
   `uv run python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); assert 'research' in d['project']['optional-dependencies']"`
   then `uv sync`.
3. **Commit:** `factory(SS-12): optional research dependency extra [factory-managed]`

## Interface Contracts
- Consumes nothing at runtime; enables the guarded imports in SS-07/SS-08. Owns no code contract.

## Verification Commands
- `uv run python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); assert 'research' in d['project']['optional-dependencies']"`
- `uv sync`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| root pyproject declares research extra | [STRUCTURAL] | `grep -q "pytesseract" pyproject.toml && grep -q "optional-dependencies" pyproject.toml \|\| (echo "FAIL: research extra missing in root pyproject" && exit 1)` |
| extra parses via tomllib | [MECHANICAL] | `uv run python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); assert 'research' in d['project']['optional-dependencies']"` |
| core install unaffected | [MECHANICAL] | `uv sync 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: uv sync" && exit 1)` |
