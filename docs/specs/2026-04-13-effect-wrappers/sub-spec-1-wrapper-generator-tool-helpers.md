---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-effect-wrappers.md"
sub_spec_number: 1
title: "Wrapper Generator + Tool Helpers"
date: 2026-04-13
dependencies: [none]
---

# Sub-Spec 1: Wrapper Generator + Tool Helpers

Refined from `docs/specs/2026-04-13-effect-wrappers.md`.

## Scope

Create generator infrastructure and extract shared helpers so generated per-effect wrapper modules can register `@mcp.tool()` tools without importing `server/tools.py` (avoiding circular imports).

Three deliverables:
1. **`server/tools_helpers.py`** — new module holding `_ok`, `_err`, `_require_workspace`, `_validate_workspace_path`, and a new `register_effect_wrapper` decorator.
2. **`pipelines/effect_wrapper_gen.py`** — generator with `select_wrappable_effects`, `render_wrapper_module`, `emit_wrappers_package`, `SELECTION_HEURISTIC_DOCSTRING`.
3. **`pipelines/effect_wrappers/`** — the GENERATED package, committed to VCS. One `.py` per effect plus `__init__.py` re-exporting every wrapper function.

Wrapper bodies call `patcher.insert_effect_xml` directly (NOT `effect_add`) to avoid MCP-in-MCP invocation. They build filter XML from catalog `ParamDef` kwargs, auto-snapshot via `create_snapshot`, and return `_ok({"effect_index", "snapshot_id"})`.

CLI subcommand `workshop-video-brain catalog regenerate-wrappers [--output PATH] [--force]` and script `scripts/generate_effect_wrappers.py` both trigger `emit_wrappers_package`.

### Refactor Strategy (CRITICAL — resolves escalation trigger)

`server/tools.py` has 60+ `@mcp.tool()` functions already using `_ok`, `_err`, `_require_workspace`, `_validate_workspace_path` as module-local helpers (defined at lines 22, 26, 30, 45).

**Safe extraction approach (zero behavioral change):**
1. Copy the four helper function bodies verbatim into `server/tools_helpers.py`.
2. In `server/tools.py`, DELETE the local definitions and replace with a single import: `from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, _require_workspace, _validate_workspace_path`.
3. Do NOT rename anything; do NOT change any call site in `tools.py`.
4. `tools.py` remains the central `@mcp.tool()` registration site for hand-written tools; generated wrappers live in `pipelines/effect_wrappers/` and register themselves by importing `mcp` directly (same pattern `tools.py` uses: `from workshop_video_brain.server import mcp`).
5. `server.py` must import both `tools` and the wrappers package so registration side effects fire.
6. Run `uv run pytest tests/ -v` after extraction — must pass at baseline before generator work continues.

## Interface Contracts

### Provides
- `tools_helpers._ok(data) -> dict`, `tools_helpers._err(msg) -> dict`, `tools_helpers._require_workspace(path) -> (Path, Workspace)`, `tools_helpers._validate_workspace_path(path) -> Path` — used by `tools.py`, `effect_presets.py` (Sub-Spec 2), and all generated wrappers.
- `tools_helpers.register_effect_wrapper` — thin wrapper over `@mcp.tool()` that also appends the decorated callable's name to a module-level `__wrapped_effects__` list for traceability.
- `pipelines.effect_wrapper_gen.SELECTION_HEURISTIC_DOCSTRING: str` — the canonical filter-rule docstring.
- `pipelines.effect_wrapper_gen.select_wrappable_effects(catalog: dict[str, EffectDef]) -> list[EffectDef]`.
- `pipelines.effect_wrapper_gen.render_wrapper_module(effect_def: EffectDef) -> str`.
- `pipelines.effect_wrapper_gen.emit_wrappers_package(effects, output_dir: Path, *, force: bool = False) -> None`.
- `pipelines.effect_wrappers.__init__` — re-exports every generated `effect_<kdenlive_id>` function.

### Requires
- `effect_catalog.CATALOG` (Spec 3, shipped) with `EffectDef` and `ParamDef` dataclasses.
- `patcher.insert_effect_xml` (shipped, `adapters/kdenlive/patcher.py:964`).
- `create_snapshot` returning `SnapshotRecord.snapshot_id` (shipped).
- `workshop_video_brain.server.mcp` singleton (shipped).

### Shared State
- `pipelines/effect_wrappers/` is a generated directory. Hand-edits are forbidden; regeneration must be byte-identical.

## Implementation Steps

### Step 1: Write failing test — helper extraction
- **File:** `tests/unit/test_tools_helpers.py`
- **Test:** `test_helpers_exported_and_stable`
- **Asserts:**
  - `from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, _require_workspace, _validate_workspace_path, register_effect_wrapper` succeeds.
  - `_ok({"a": 1}) == {"status": "success", "data": {"a": 1}}`.
  - `_err("x") == {"status": "error", "message": "x"}`.
- **Run:** `uv run pytest tests/unit/test_tools_helpers.py -v`
- **Expected:** FAIL (module does not exist yet).

### Step 2: Create `tools_helpers.py`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools_helpers.py`
- **Action:** create
- **Pattern:** Copy the four helper definitions from `server/tools.py` lines 22–49 verbatim. Add `register_effect_wrapper` as a decorator:
  ```python
  __wrapped_effects__: list[str] = []
  def register_effect_wrapper(fn):
      from workshop_video_brain.server import mcp
      __wrapped_effects__.append(fn.__name__)
      return mcp.tool()(fn)
  ```

### Step 3: Refactor `tools.py` to import helpers
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Action:** modify (lines 18–49)
- **Changes:** Delete the four local helper defs. Insert `from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, _require_workspace, _validate_workspace_path` near the top-of-file imports.

### Step 4: Run full suite — regression gate
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS at prior baseline (2552+ tests). If anything fails, STOP and escalate — do not proceed.

### Step 5: Write failing test — generator selection
- **File:** `tests/unit/test_effect_wrapper_gen.py`
- **Tests:**
  - `test_select_wrappable_effects_yields_at_least_20`
  - `test_select_skips_audio_category`
  - `test_select_skips_params_gt_8`
  - `test_select_skips_bad_kdenlive_id`
- **Run:** `uv run pytest tests/unit/test_effect_wrapper_gen.py -v`
- **Expected:** FAIL.

### Step 6: Implement `select_wrappable_effects`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrapper_gen.py`
- **Action:** create
- **Rules (verbatim from heuristic):**
  - `category == "video"`
  - `len(params) <= 8`
  - `kdenlive_id` matches `^[A-Za-z0-9_\-]+$`
  - `display_name` non-empty after strip
- **Sort:** result sorted by `kdenlive_id` for deterministic output.
- **Constant:** define `SELECTION_HEURISTIC_DOCSTRING` capturing these rules as plain text.
- **Escalation check:** If `len(result) < 20`, caller (CLI/script) must raise `RuntimeError("selection heuristic yielded < 20 effects; tune heuristic")`. The function itself returns the list; the guard lives in CLI/emit.

### Step 7: Write failing test — renderer
- **File:** `tests/unit/test_effect_wrapper_gen.py` (extend)
- **Tests:**
  - `test_render_wrapper_module_for_transform_is_valid_python` — `ast.parse(render_wrapper_module(CATALOG['transform']))` succeeds and contains a `FunctionDef` named `effect_transform`.
  - `test_render_adds_keyframes_param_for_animated_params` — any effect with a `KEYFRAME`/`ANIMATED`/`GEOMETRY` param yields a `keyframes: str = ""` kwarg.
  - `test_render_skips_hidden_params` — params with `ParamType.HIDDEN` are absent from the signature.
  - `test_render_fixed_param_uses_catalog_default` — `FIXED` params appear with their default as the kwarg default.
  - `test_rendered_module_contains_generated_marker` — docstring contains literal `"GENERATED"`.
- **Run:** `uv run pytest tests/unit/test_effect_wrapper_gen.py -v`
- **Expected:** FAIL.

### Step 8: Implement `render_wrapper_module`
- **File:** `pipelines/effect_wrapper_gen.py` (extend)
- **Output template (per effect):**
  ```python
  """GENERATED — regenerate with `workshop-video-brain catalog regenerate-wrappers`.

  Source effect: <kdenlive_id> (<mlt_service>).
  """
  from __future__ import annotations
  from workshop_video_brain.edit_mcp.server.tools_helpers import (
      _ok, _err, _require_workspace, register_effect_wrapper,
  )
  from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
  # ... helpers for filter XML build + snapshot

  @register_effect_wrapper
  def effect_<kdenlive_id>(workspace_path: str, track: int, clip: int,
                           <typed param kwargs with catalog defaults>,
                           keyframes: str = "",  # only if animated
                           ) -> dict:
      """<display_name>: <description (first line)>."""
      try:
          ws_path, _ws = _require_workspace(workspace_path)
          # load project, build XML, insert_effect_xml at end of stack,
          # snapshot, serialize, return _ok({"effect_index", "snapshot_id"})
          ...
      except (ValueError, FileNotFoundError, IndexError) as exc:
          return _err(str(exc))
  ```
- **Param type mapping:**
  - `INTEGER` → `int`
  - `DOUBLE` / `CONSTANT` → `float`
  - `BOOL` / `SWITCH` → `bool`
  - `COLOR` / `STRING` / `URL` → `str`
  - `LIST` with `values` → `typing.Literal[<values>]`
  - `FIXED` → kwarg with the fixed default (caller may override)
  - `HIDDEN` → skipped
  - `KEYFRAME` / `ANIMATED` / `GEOMETRY` → skipped as typed kwarg; contributes `keyframes: str = ""`
- **Determinism:** Always emit kwargs in catalog param order. Never use `dict.items()` without sorting. No timestamps in the output except inside the generator's own header comment (but keep that fixed — no dates).

### Step 9: Write failing test — package emitter
- **Tests:**
  - `test_emit_wrappers_package_writes_one_file_per_effect`
  - `test_emit_wrappers_package_writes_init_exporting_all`
  - `test_emit_wrappers_package_is_byte_identical_across_runs` (emit to two tmpdirs, assert file-by-file `bytes` equality).
  - `test_emit_refuses_non_empty_without_force`
- **Run:** `uv run pytest tests/unit/test_effect_wrapper_gen.py -v`
- **Expected:** FAIL.

### Step 10: Implement `emit_wrappers_package`
- **File:** `pipelines/effect_wrapper_gen.py` (extend)
- **Behavior:**
  - Ensure `output_dir` exists. If non-empty and not `force`, raise `FileExistsError` listing blocker files.
  - For each effect: write `effect_<kdenlive_id>.py` with `render_wrapper_module(effect)`.
  - Write `__init__.py`:
    ```python
    """GENERATED package of per-effect MCP wrappers."""
    from .effect_<id_1> import effect_<id_1>
    ...
    __all__ = ["effect_<id_1>", ...]
    ```
    Imports sorted alphabetically.
  - Signature-conflict detection: maintain a set of emitted function names; raise `RuntimeError` on collision.

### Step 11: Run generator and commit the package
- **Run:** `uv run python -c "from workshop_video_brain.edit_mcp.pipelines.effect_wrapper_gen import emit_wrappers_package, select_wrappable_effects; from workshop_video_brain.edit_mcp.pipelines.effect_catalog import CATALOG; from pathlib import Path; emit_wrappers_package(select_wrappable_effects(CATALOG), Path('workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrappers'), force=True)"`
- **Verify:** `uv run python -c "from workshop_video_brain.edit_mcp.pipelines.effect_wrappers import effect_transform; print(effect_transform.__doc__)"` prints a docstring starting with the effect display name.

### Step 12: Write failing test — server wires wrappers
- **Test:** `test_effect_wrappers_registered_on_mcp` — import `workshop_video_brain.server`, then confirm at least one `effect_<id>` tool name is registered on `mcp` (use whatever introspection FastMCP exposes; if none, assert module import succeeded and `__wrapped_effects__` is non-empty in `tools_helpers`).
- **File:** `tests/unit/test_effect_wrapper_gen.py` (extend) or `tests/integration/test_server_wiring.py`.
- **Run:** `uv run pytest -v -k wrappers_registered`
- **Expected:** FAIL (server doesn't yet import the package).

### Step 13: Wire wrappers into server
- **File:** `workshop-video-brain/src/workshop_video_brain/server.py` (or wherever `tools.py` is imported)
- **Change:** Add `from workshop_video_brain.edit_mcp.pipelines import effect_wrappers  # noqa: F401 — registration side effect` next to the existing `tools` import.

### Step 14: Write failing test — CLI + script
- **Tests:**
  - `test_cli_catalog_regenerate_wrappers_writes_package` — CliRunner invokes `catalog regenerate-wrappers --output <tmp> --force`; assert files land in tmp.
  - `test_script_generate_effect_wrappers_writes_package` — subprocess call to `python scripts/generate_effect_wrappers.py --output <tmp> --force`.
- **File:** `tests/unit/test_effect_wrapper_gen.py` (extend)
- **Run:** `uv run pytest -v tests/unit/test_effect_wrapper_gen.py`
- **Expected:** FAIL.

### Step 15: Add CLI subcommand and script
- **File:** `workshop-video-brain/src/workshop_video_brain/app/cli.py` — add a new `@main.group() def catalog()` (or extend existing if one exists) with subcommand `regenerate-wrappers`. Pattern-match existing groups (e.g., `workspace()` at line 34).
- **File:** `scripts/generate_effect_wrappers.py` — new file using `argparse` with `--output`, `--force`. Pattern-match `scripts/generate_effect_catalog.py`.
- Both call `emit_wrappers_package(select_wrappable_effects(CATALOG), output, force=force)` and enforce the `>= 20` escalation.

### Step 16: Full-suite regression
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS. No regressions.

### Step 17: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools_helpers.py workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrapper_gen.py workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrappers/ workshop-video-brain/src/workshop_video_brain/server.py workshop-video-brain/src/workshop_video_brain/app/cli.py scripts/generate_effect_wrappers.py tests/unit/test_tools_helpers.py tests/unit/test_effect_wrapper_gen.py`
- **Message:** `feat: wrapper generator and tool helpers`

## Acceptance Criteria

- `[STRUCTURAL]` `effect_wrapper_gen.py` exports `select_wrappable_effects`, `render_wrapper_module`, `emit_wrappers_package`, `SELECTION_HEURISTIC_DOCSTRING`.
- `[STRUCTURAL]` `tools_helpers.py` exports `_require_workspace`, `_ok`, `_err`, `register_effect_wrapper`.
- `[STRUCTURAL]` `server/tools.py` imports helpers from `tools_helpers` (no local redefinition).
- `[STRUCTURAL]` Generated `effect_wrappers/__init__.py` exposes all wrapped effect tool names.
- `[BEHAVIORAL]` `select_wrappable_effects(CATALOG)` returns ≥ 20 entries.
- `[BEHAVIORAL]` `render_wrapper_module(CATALOG['transform'])` returns valid Python containing `def effect_transform(...)`.
- `[BEHAVIORAL]` `emit_wrappers_package` writes one `.py` per effect and updates `__init__.py`.
- `[BEHAVIORAL]` Generated modules import cleanly.
- `[BEHAVIORAL]` Animated/keyframe/geometry params add `keyframes: str = ""`.
- `[BEHAVIORAL]` Effects with `>8` params are skipped.
- `[BEHAVIORAL]` Wrapper body on call inserts filter via `patcher.insert_effect_xml`, auto-snapshots, returns `{status, data: {effect_index, snapshot_id}}`.
- `[INTEGRATION]` Generated wrappers importable from `workshop_video_brain.edit_mcp.pipelines.effect_wrappers`.
- `[BEHAVIORAL]` CLI `catalog regenerate-wrappers --output PATH` writes the package.
- `[BEHAVIORAL]` Script `scripts/generate_effect_wrappers.py` same outcome.
- `[BEHAVIORAL]` Regeneration is byte-identical (deterministic).
- `[MECHANICAL]` `uv run pytest tests/unit/test_effect_wrapper_gen.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` passes with no regressions.

## Completeness Checklist

### `ParamType` → Python type mapping (generator must handle all)

| ParamType | Emitted kwarg type | Notes |
|-----------|-------------------|-------|
| CONSTANT | float | default from catalog |
| DOUBLE | float | default from catalog |
| INTEGER | int | default from catalog |
| BOOL | bool | default parsed "0"/"1" |
| SWITCH | bool | default parsed "0"/"1" |
| COLOR | str | default from catalog |
| LIST | `Literal[...]` | use `values` tuple |
| FIXED | type inferred; default = catalog default | caller may override |
| POSITION | int | frame offset |
| URL | str | |
| STRING | str | |
| READONLY | skipped | not exposed |
| HIDDEN | skipped | not exposed |
| KEYFRAME / ANIMATED / GEOMETRY | skipped as typed kwarg; triggers `keyframes: str = ""` | |

### Wrapper return shape

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| status | `"success"` / `"error"` | required | MCP clients |
| data.effect_index | int | required (on success) | callers chaining reorder/keyframe |
| data.snapshot_id | str | required (on success) | undo/restore |
| message | str | required (on error) | clients |

### Selection heuristic (exact)

- `category == "video"` — exact string
- `len(params) <= 8`
- `kdenlive_id` regex: `^[A-Za-z0-9_\-]+$`
- `display_name.strip() != ""`
- Minimum yield: 20 effects. Below that → `RuntimeError` from CLI/script entry points.

## Verification Commands

- **Build:** `uv sync` (Python 3.12+).
- **Tests:**
  - `uv run pytest tests/unit/test_tools_helpers.py -v`
  - `uv run pytest tests/unit/test_effect_wrapper_gen.py -v`
  - `uv run pytest tests/ -v`
- **Smoke:**
  - `uv run workshop-video-brain catalog regenerate-wrappers --output /tmp/wrap_smoke --force`
  - `uv run python -c "from workshop_video_brain.edit_mcp.pipelines.effect_wrappers import effect_transform; print(effect_transform.__doc__)"`

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` — generated-file header pattern (module docstring with regenerate instructions; `GENERATED FILE -- do not edit by hand`).
- `scripts/generate_effect_catalog.py` — script entry-point pattern.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (line 22, 26, 45) — helper implementations to copy verbatim.
- `workshop-video-brain/src/workshop_video_brain/app/cli.py` (line 17, 34) — click group + subcommand pattern.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:964` — `insert_effect_xml` signature.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools_helpers.py` | Create | Shared `_ok`, `_err`, `_require_workspace`, `_validate_workspace_path`, `register_effect_wrapper` |
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Replace local helpers with import from `tools_helpers` |
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrapper_gen.py` | Create | Generator: selection, rendering, emission |
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrappers/__init__.py` | Create (generated) | Re-export wrapper callables |
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrappers/effect_*.py` | Create (generated, ~20-30 files) | One wrapper per wrappable catalog effect |
| `workshop-video-brain/src/workshop_video_brain/server.py` | Modify | Import `effect_wrappers` package so registration side effects fire |
| `workshop-video-brain/src/workshop_video_brain/app/cli.py` | Modify | Add `catalog regenerate-wrappers` subcommand |
| `scripts/generate_effect_wrappers.py` | Create | Standalone generator script |
| `tests/unit/test_tools_helpers.py` | Create | Helper extraction tests |
| `tests/unit/test_effect_wrapper_gen.py` | Create | Generator + emitter + CLI tests |
