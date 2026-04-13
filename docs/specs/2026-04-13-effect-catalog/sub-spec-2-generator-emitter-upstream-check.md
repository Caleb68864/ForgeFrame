---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-effect-catalog.md"
sub_spec_number: 2
title: "Generator + Emitter + Upstream Check"
date: 2026-04-13
dependencies: [1]
---

# Sub-Spec 2: Generator + Emitter + Upstream Check

Refined from `docs/specs/2026-04-13-effect-catalog.md` — Factory Run 2026-04-13-effect-catalog.

## Scope

Build the catalog builder that orchestrates: (1) parsing every XML file in a source directory using sub-spec 1's `parse_effect_xml`, (2) optional cross-check against upstream Kdenlive (`data/effects/` in the github.com/KDE/kdenlive repo), (3) emission of a typed Python module to a target path. Wraps unparseable files in skip-with-log; warns on duplicate `kdenlive_id`. Adds a one-shot script entry point at `scripts/generate_effect_catalog.py` (new directory — repo currently has none, so the script also creates the dir on first commit).

The generated `effect_catalog.py` is a checked-in artifact. It must be valid importable Python with zero runtime file I/O, exposing `CATALOG: dict[str, EffectDef]` plus the two helper lookups, plus generation metadata constants.

Codebase findings:
- No `scripts/` directory exists yet at repo root — sub-spec creates it. Confirmed via `ls /home/caleb/Projects/ForgeFrame/scripts` returning no-such-file.
- `/usr/share/kdenlive/effects/` contains 376 entries on this machine (375 `.xml` files plus one `update/` subdir to ignore).
- Kdenlive package version (Arch): `kdenlive 25.12.3-1` — `__source_version__` should be detected via `pacman -Q kdenlive` (Arch) OR fallback to a `--source-version` CLI flag, OR read from a known-location header. Use a small `_detect_source_version()` helper that tries `pacman` then `dpkg -s kdenlive` then returns `"unknown"`.
- Upstream URL pattern: `https://api.github.com/repos/KDE/kdenlive/contents/data/effects` (lists XML filenames); use `urllib.request` from stdlib (no new deps).

## Interface Contracts

### Provides
- `build_catalog(local_dir: Path, check_upstream: bool = True) -> tuple[list[EffectDef], DiffReport]`: orchestrator.
- `emit_python_module(effects: list[EffectDef], output_path: Path, source_version: str, diff_report: DiffReport) -> None`: writes the generated module.
- `fetch_upstream_effects() -> list[str] | None`: returns list of upstream `kdenlive_id`s (filename stems) or `None` on any network/parse failure.
- `DiffReport` (frozen `@dataclass(slots=True)`): summary of the cross-check.
- Generated module `workshop_video_brain.edit_mcp.pipelines.effect_catalog` exposes `CATALOG`, `find_by_name`, `find_by_service`, `__generated_at__`, `__source_version__`, `__local_count__`, `__upstream_diff__`.
- Script `scripts/generate_effect_catalog.py` callable as `python scripts/generate_effect_catalog.py [flags]`.

### Requires
From sub-spec 1:
- `EffectDef`, `ParamDef`, `ParamType` dataclasses/enum.
- `parse_effect_xml(path) -> EffectDef`.

### Shared State
- The generated `effect_catalog.py` file on disk is shared with sub-spec 3 (which imports `CATALOG` and the lookup helpers).

## Implementation Steps

### Step 1: Write failing test file
- **File:** `tests/unit/test_effect_catalog_generator.py`
- **Pattern:** `tests/unit/test_effect_apply.py` style.
- **Tests:**
  1. `test_build_catalog_no_upstream_returns_three_effects` — pass a `tmp_path` containing 3 valid fixture XMLs (copy from `tests/unit/fixtures/effect_xml/`); assert returns `(list of 3, DiffReport(upstream_check="skipped", upstream_count=None))`.
  2. `test_build_catalog_skips_unparseable` — tmp_path with 2 valid + 1 malformed file; returns 2 effects, malformed logged.
  3. `test_build_catalog_warns_on_duplicate_id` — tmp_path with two files where one is renamed copy of another so stems differ but parsed `kdenlive_id` collision is forced via direct `EffectDef` injection in a unit-level helper test; assert warning emitted via `caplog`. (Practically: simulate by writing two files `foo.xml` that both have same content but the loop processes them — duplication arises only if list contains two EffectDefs with the same id; test by mocking parse to return colliding ids.)
  4. `test_emit_python_module_produces_importable_file` — call `emit_python_module([effect_def_1, effect_def_2], tmp_path / "out.py", source_version="25.12.3", diff_report=...)`; then `importlib.util.spec_from_file_location` import it; assert `module.CATALOG` has both ids and `module.__source_version__ == "25.12.3"`.
  5. `test_emit_python_module_top_docstring_has_regen_instructions` — assert generated file's first docstring contains both `"regenerate"` (case-insensitive) and the source version.
  6. `test_emit_idempotent` — call `emit_python_module` twice with same inputs; resulting bytes are byte-identical (sort effects by `kdenlive_id` before emit).
  7. `test_diffreport_fields` — instantiate DiffReport with all fields; frozen check.
  8. `test_fetch_upstream_returns_none_on_network_failure` — patch `urllib.request.urlopen` to raise `URLError`; `fetch_upstream_effects()` returns None and does not raise.
  9. `test_fetch_upstream_returns_list_on_success` — patch `urlopen` to return JSON list of `{"name": "foo.xml"}` entries; returns `["foo"]`.
  10. `test_find_by_name_and_service` — generate a module, import it, assert helpers work.
  11. `test_emit_includes_local_count_metadata` — `__local_count__ == len(effects)`.
- **Run:** `uv run pytest tests/unit/test_effect_catalog_generator.py -v`
- **Expected:** all FAIL.

### Step 2: Extend effect_catalog_gen.py with DiffReport + builder
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py`
- **Action:** modify (extend with new code below the sub-spec 1 definitions)
- **Add:**
  - `from typing import Literal`
  - `import json, urllib.request, urllib.error, datetime, logging`
  - `_LOG = logging.getLogger(__name__)`
  - `@dataclass(frozen=True, slots=True) class DiffReport:` with fields `local_count: int`, `upstream_count: int | None`, `upstream_only_ids: tuple[str, ...]`, `local_only_ids: tuple[str, ...]`, `upstream_check: Literal["ok","skipped","failed"]`.
  - `UPSTREAM_API_URL = "https://api.github.com/repos/KDE/kdenlive/contents/data/effects"`
  - `def fetch_upstream_effects() -> list[str] | None:` — `urlopen(UPSTREAM_API_URL, timeout=10)`; parse JSON; return sorted list of stems for entries whose name ends in `.xml`. Catch `urllib.error.URLError`, `json.JSONDecodeError`, `TimeoutError`, `OSError` — log warning, return None.
  - `def build_catalog(local_dir: Path, check_upstream: bool = True) -> tuple[list[EffectDef], DiffReport]:`
    - Glob `*.xml` in `local_dir`; sort filenames for deterministic order.
    - For each file: try `parse_effect_xml`; on `ET.ParseError` or `ValueError` log warning and skip. Note: `ValueError` from unknown param type is also skipped here (the parser raises loudly, but the BUILDER catches and logs — design decision per master spec edge case). Document this in the function docstring.
    - Detect duplicates by `kdenlive_id`: keep last-wins, log warning naming both source paths.
    - If `check_upstream`: call `fetch_upstream_effects()`. If None -> `upstream_check="failed"`, upstream_count=None, both diff lists empty. Else compute set differences -> `upstream_check="ok"`.
    - If not `check_upstream`: `upstream_check="skipped"`, upstream_count=None.
    - Return `(effects_list, DiffReport(...))`.

### Step 3: Implement emit_python_module
- **File:** same module
- **Function:** `def emit_python_module(effects: list[EffectDef], output_path: Path, source_version: str, diff_report: DiffReport) -> None:`
- **Logic:**
  - Sort `effects` by `kdenlive_id` (idempotency).
  - Build text:
    ```python
    """GENERATED FILE -- do not edit by hand.

    Regenerate with:
        python scripts/generate_effect_catalog.py
        # or
        uv run workshop-video-brain catalog regenerate

    Source: Kdenlive {source_version} effects at /usr/share/kdenlive/effects/
    """
    from __future__ import annotations
    from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import (
        EffectDef, ParamDef, ParamType,
    )

    __generated_at__ = "{ISO timestamp UTC, no microseconds}"
    __source_version__ = "{source_version}"
    __local_count__ = {len(effects)}
    __upstream_diff__ = {repr-of-DiffReport-as-dict}

    CATALOG: dict[str, EffectDef] = {
        "{id}": EffectDef(
            kdenlive_id="{id}",
            mlt_service="{svc}",
            display_name={repr},
            description={repr},
            category="{cat}",
            params=(
                ParamDef(name={repr}, display_name={repr}, type=ParamType.{ENUM}, default={repr}, min={val}, max={val}, decimals={val}, values={tuple_repr}, value_labels={tuple_repr}, keyframable={bool}),
                ...
            ),
        ),
        ...
    }

    def find_by_name(name: str) -> EffectDef | None:
        return CATALOG.get(name)

    def find_by_service(mlt_service: str) -> EffectDef | None:
        for eff in CATALOG.values():
            if eff.mlt_service == mlt_service:
                return eff
        return None
    ```
  - Use `repr()` for all string/None/numeric values for safe escaping.
  - For idempotency: ISO timestamp must be deterministic if the test wants byte-identical output. Solution: accept an optional `now: datetime | None = None` parameter; when None use `datetime.now(timezone.utc).replace(microsecond=0)`. Tests pass an explicit timestamp; the script does not.
  - Write atomically: write to `output_path.with_suffix(".py.tmp")` then `os.replace(...)`.

### Step 4: Implement _detect_source_version helper
- **File:** same module
- **Function:** `def _detect_source_version() -> str:`
- **Logic:** try `subprocess.run(["pacman", "-Q", "kdenlive"], capture_output=True, text=True, timeout=5)` -> parse `kdenlive 25.12.3-1` -> return `"25.12.3"`. On non-zero or missing binary, try `dpkg -s kdenlive`. Else return `"unknown"`. Wrap in `try/except FileNotFoundError`.

### Step 5: Run unit tests for generator
- **Run:** `uv run pytest tests/unit/test_effect_catalog_generator.py -v`
- **Expected:** all 11 tests PASS.

### Step 6: Create the script entry point
- **File:** `scripts/generate_effect_catalog.py`
- **Action:** create (also creates `scripts/` directory)
- **Pattern:** standalone Python script with shebang `#!/usr/bin/env python3` and `if __name__ == "__main__":` guard. Use `argparse` (stdlib).
- **Flags:**
  - `--no-upstream-check` (store_true): skip upstream fetch.
  - `--output PATH` (default: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py`).
  - `--source-dir PATH` (default: `/usr/share/kdenlive/effects/`).
  - `--source-version STR` (default: auto-detect via `_detect_source_version`).
- **Logic:**
  - Validate source dir exists. If not, print friendly hint: "Kdenlive not installed at {dir}. Install Kdenlive or pass --source-dir."
  - `effects, diff = build_catalog(source_dir, check_upstream=not args.no_upstream_check)`
  - `emit_python_module(effects, output, source_version, diff)`
  - Print summary: `f"Wrote {output}: {len(effects)} effects (upstream check: {diff.upstream_check})"`
  - Exit 0.

### Step 7: Run the generator against real Kdenlive
- **Run:** `uv run python scripts/generate_effect_catalog.py --no-upstream-check`
- **Expected:** writes `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py`. Exit 0.
- **Verify:** `uv run python -c "from workshop_video_brain.edit_mcp.pipelines.effect_catalog import CATALOG; print(len(CATALOG))"` returns a number > 300.

### Step 8: Smoke-test the generator against fixtures
- **Run:** `uv run python scripts/generate_effect_catalog.py --no-upstream-check --output /tmp/test_catalog.py --source-dir tests/unit/fixtures/effect_xml/`
- **Expected:** exits 0, writes `/tmp/test_catalog.py`. `python -c "import importlib.util; spec=importlib.util.spec_from_file_location('t','/tmp/test_catalog.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(len(m.CATALOG))"` runs.

### Step 9: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py scripts/generate_effect_catalog.py tests/unit/test_effect_catalog_generator.py`
- **Message:** `feat: catalog generator + emitter + upstream cross-check`

## Acceptance Criteria

- `[STRUCTURAL]` Module exports `build_catalog(local_dir: Path, check_upstream: bool = True) -> tuple[list[EffectDef], DiffReport]`.
- `[STRUCTURAL]` Module exports `emit_python_module(effects: list[EffectDef], output_path: Path, source_version: str, diff_report: DiffReport) -> None`.
- `[STRUCTURAL]` Module exports `fetch_upstream_effects() -> list[str] | None` (returns None on fetch failure, list of ids on success).
- `[STRUCTURAL]` `DiffReport` dataclass with fields `local_count: int`, `upstream_count: int | None`, `upstream_only_ids: tuple[str, ...]`, `local_only_ids: tuple[str, ...]`, `upstream_check: Literal["ok","skipped","failed"]`.
- `[STRUCTURAL]` Generated `effect_catalog.py` defines `CATALOG: dict[str, EffectDef]`, `find_by_name(name)`, `find_by_service(mlt_service)`, `__generated_at__`, `__source_version__`, `__local_count__`.
- `[BEHAVIORAL]` `build_catalog` with `check_upstream=False` on a directory of 3 fixture XMLs returns a 3-element list and a DiffReport with `upstream_check="skipped"`.
- `[BEHAVIORAL]` `emit_python_module` produces a file that is syntactically valid Python, importable, and whose `CATALOG` dict contains entries matching the input list.
- `[BEHAVIORAL]` Generated module has a top docstring including regeneration instructions and `source_version`.
- `[BEHAVIORAL]` `fetch_upstream_effects` on a network failure returns `None` without raising.
- `[BEHAVIORAL]` Duplicate kdenlive_id across parsed files yields a warning log and last-wins in CATALOG; both filenames included in the warning.
- `[MECHANICAL]` `python scripts/generate_effect_catalog.py --no-upstream-check --output /tmp/test_catalog.py --source-dir tests/unit/fixtures/effect_xml/` runs to completion, exits 0, produces a valid Python file.
- `[MECHANICAL]` Running the generator against the real `/usr/share/kdenlive/effects/` produces a `pipelines/effect_catalog.py` with `__local_count__` matching `len(os.listdir("/usr/share/kdenlive/effects/"))` minus unparseable count.
- `[MECHANICAL]` `python -c "from workshop_video_brain.edit_mcp.pipelines.effect_catalog import CATALOG; print(len(CATALOG))"` returns a count > 300.
- `[MECHANICAL]` `uv run pytest tests/unit/test_effect_catalog_generator.py -v` passes.

## Completeness Checklist

`DiffReport` fields:

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| local_count | int | required | generated module metadata |
| upstream_count | int \| None | optional | generated module metadata |
| upstream_only_ids | tuple[str, ...] | required (may be empty) | generated module metadata |
| local_only_ids | tuple[str, ...] | required (may be empty) | generated module metadata |
| upstream_check | Literal["ok","skipped","failed"] | required | generated module metadata |

Generated module top-level constants:

| Name | Type | Required | Notes |
|------|------|----------|-------|
| `__generated_at__` | str | required | ISO 8601 UTC, no microseconds |
| `__source_version__` | str | required | e.g., "25.12.3" or "unknown" |
| `__local_count__` | int | required | == len(CATALOG) |
| `__upstream_diff__` | dict | required | DiffReport rendered as dict |
| `CATALOG` | dict[str, EffectDef] | required | keyed by kdenlive_id |
| `find_by_name` | callable | required | returns EffectDef \| None |
| `find_by_service` | callable | required | returns EffectDef \| None |

Resource limits:
- Upstream HTTP timeout: 10 seconds — enforced in `fetch_upstream_effects`.
- Subprocess timeout for version detection: 5 seconds — enforced in `_detect_source_version`.

## Verification Commands

- **Build:** `uv sync`
- **Tests:** `uv run pytest tests/unit/test_effect_catalog_generator.py -v`
- **Acceptance:**
  - `uv run python scripts/generate_effect_catalog.py --no-upstream-check`
  - `uv run python -c "from workshop_video_brain.edit_mcp.pipelines.effect_catalog import CATALOG, find_by_name, find_by_service; assert len(CATALOG) > 300; assert find_by_name('acompressor') is not None; assert find_by_service('avfilter.acompressor') is not None; print('ok', len(CATALOG))"`
  - Idempotency: run generator twice, `diff` the two outputs (only `__generated_at__` may differ — confirm by `grep -v __generated_at__` then diff).

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py`: stdlib-first, pure functions.
- `tests/unit/test_effect_apply.py`: function-style pytest with `unittest.mock.patch` for I/O boundaries.
- For atomic file write: `os.replace(tmp, final)` after writing tmp file.
- For importing a generated file in tests: `importlib.util.spec_from_file_location` + `module_from_spec` + `spec.loader.exec_module`.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py` | Modify | Append `DiffReport`, `build_catalog`, `emit_python_module`, `fetch_upstream_effects`, `_detect_source_version`. |
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` | Create (generated) | Checked-in generated catalog with > 300 entries. |
| `scripts/generate_effect_catalog.py` | Create | Standalone CLI script (also creates `scripts/` dir). |
| `tests/unit/test_effect_catalog_generator.py` | Create | Generator + emitter unit tests. |
