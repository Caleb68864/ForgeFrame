---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-effect-catalog.md"
sub_spec_number: 3
title: "MCP Tool Surface + CLI Subcommand + Integration"
date: 2026-04-13
dependencies: [1, 2]
---

# Sub-Spec 3: MCP Tool Surface + CLI Subcommand + Integration

Refined from `docs/specs/2026-04-13-effect-catalog.md` — Factory Run 2026-04-13-effect-catalog.

## Scope

Wire the catalog into the MCP tool surface and the CLI:
1. Add a new `@mcp.tool() effect_info(name: str) -> dict` in `edit_mcp/server/tools.py`.
2. Re-source the existing `effect_list_common()` body so it iterates the generated catalog instead of `effect_apply.list_common_effects()` — the `@mcp.tool()` signature stays unchanged.
3. Add a `catalog regenerate` subcommand to the click CLI at `workshop-video-brain/src/workshop_video_brain/app/cli.py`.

Codebase findings:
- CLI is **click-based**. Pattern: `@main.group()` then `@<group>.command("name")`. See existing `workspace`, `media` groups in `app/cli.py` lines 33-100.
- `effect_list_common` exists at `tools.py:3727` and currently delegates to `from workshop_video_brain.edit_mcp.pipelines.effect_apply import list_common_effects`. We replace the body, keep the decorator and signature.
- `effect_add` is at `tools.py:3666` — DO NOT touch (per master spec must-not).
- Helper functions `_ok` / `_err` exist in `tools.py` and follow `{"status": "success"|"error", ...}` pattern.
- Integration test pattern reference: `tests/integration/test_mcp_tools.py`, `tests/integration/test_keyframe_mcp_tools.py` — they import tools as callables and assert response shape.
- CLI test pattern reference: `tests/unit/test_cli.py` — uses `click.testing.CliRunner`.

## Interface Contracts

### Provides
- MCP tool `effect_info(name: str) -> dict` registered with `@mcp.tool()` on the FastMCP server.
- MCP tool `effect_list_common() -> dict` (rewired body; signature unchanged) returning > 300 entries.
- CLI subcommand group `catalog` with `regenerate` command accepting `--no-upstream-check`, `--output PATH`, `--source-dir PATH`, `--source-version STR`.

### Requires
From sub-spec 1:
- `EffectDef`, `ParamDef`, `ParamType` for serialization.

From sub-spec 2:
- `workshop_video_brain.edit_mcp.pipelines.effect_catalog` module with `CATALOG`, `find_by_name`, `find_by_service`.
- `scripts/generate_effect_catalog.py` script (CLI subcommand shells out to the same `build_catalog` / `emit_python_module` functions, NOT to the script file).

### Shared State
- Reads from the generated `effect_catalog.py` module at runtime.
- Writes to the same generated module via the CLI subcommand (when invoked).

## Implementation Steps

### Step 1: Write failing integration tests for MCP tools
- **File:** `tests/integration/test_effect_catalog_mcp_tools.py`
- **Pattern:** `tests/integration/test_mcp_tools.py` style — import the tool callable from `workshop_video_brain.edit_mcp.server.tools` and call directly.
- **Tests:**
  1. `test_effect_info_by_kdenlive_id` — `effect_info("acompressor")` returns `{"status":"success","data":{"kdenlive_id":"acompressor", "mlt_service":"avfilter.acompressor", "category":"audio", ...}}` and `data["params"]` is a list of dicts with all 10 ParamDef fields serialized.
  2. `test_effect_info_by_mlt_service` — `effect_info("avfilter.acompressor")` returns the same `kdenlive_id`.
  3. `test_effect_info_not_found` — `effect_info("nonexistent_effect")` returns `{"status":"error","message": "Effect not found: nonexistent_effect. Try `effect_list_common` for the registry."}`. (Exact message string match.)
  4. `test_effect_info_empty_string` — `effect_info("")` returns `{"status":"error","message":"Effect name cannot be empty."}`.
  5. `test_effect_info_param_serialization` — find a param with all fields populated; assert `type` is serialized as the lowercase enum value string (e.g., `"constant"`), `values` and `value_labels` are lists (not tuples), `keyframable` is bool.
  6. `test_effect_list_common_returns_full_catalog` — `effect_list_common()` returns `{"status":"success","data":{"effects":[...]}}` with `len(data["effects"]) > 300`.
  7. `test_effect_list_common_entry_shape` — each entry has keys `kdenlive_id`, `mlt_service`, `display_name`, `category`, `short_description`.
  8. `test_short_description_truncation` — pick or synthesize an effect whose description > 80 chars; assert `short_description` ends with `"..."` and len <= 83.
  9. `test_effect_list_common_signature_unchanged` — `inspect.signature(effect_list_common)` has zero parameters.
- **Run:** `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py -v`
- **Expected:** all FAIL.

### Step 2: Write failing unit tests for CLI subcommand
- **File:** `tests/unit/test_cli_catalog.py`
- **Pattern:** `tests/unit/test_cli.py` — `click.testing.CliRunner`.
- **Tests:**
  1. `test_catalog_help` — `runner.invoke(main, ["catalog", "--help"])` exit 0, output contains `"regenerate"`.
  2. `test_catalog_regenerate_help` — `runner.invoke(main, ["catalog", "regenerate", "--help"])` exit 0, output contains `--no-upstream-check`, `--output`, `--source-dir`.
  3. `test_catalog_regenerate_against_fixtures` — `runner.invoke(main, ["catalog", "regenerate", "--no-upstream-check", "--output", str(tmp_path / "out.py"), "--source-dir", "tests/unit/fixtures/effect_xml/"])`; exit 0; tmp file exists and is non-empty.
  4. `test_catalog_regenerate_missing_source_dir` — point at `/nonexistent/path`; exit non-zero, stderr mentions "Kdenlive" or the path.
- **Run:** `uv run pytest tests/unit/test_cli_catalog.py -v`
- **Expected:** all FAIL.

### Step 3: Add `effect_info` MCP tool
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Action:** modify — insert immediately after `effect_list_common` (around line 3736).
- **Pattern:** Follow `effect_add` and `effect_list_common` style — module-level decorator, lazy imports inside the function body, `_ok`/`_err` helpers.
- **Implementation:**
  ```python
  @mcp.tool()
  def effect_info(name: str) -> dict:
      """Return full schema for a Kdenlive effect by kdenlive_id or MLT service tag.

      Looks up the catalog generated from /usr/share/kdenlive/effects/. Use
      `effect_list_common` to discover available effect ids.
      """
      if not name or not name.strip():
          return _err("Effect name cannot be empty.")
      try:
          from workshop_video_brain.edit_mcp.pipelines.effect_catalog import (
              find_by_name, find_by_service,
          )
      except ModuleNotFoundError:
          return _err(
              "Effect catalog not generated. Run: "
              "uv run workshop-video-brain catalog regenerate"
          )
      eff = find_by_name(name) or find_by_service(name)
      if eff is None:
          return _err(
              f"Effect not found: {name}. Try `effect_list_common` for the registry."
          )
      return _ok(_effect_def_to_dict(eff))
  ```
- **Add helper** (private, near `effect_info`):
  ```python
  def _effect_def_to_dict(eff) -> dict:
      return {
          "kdenlive_id": eff.kdenlive_id,
          "mlt_service": eff.mlt_service,
          "display_name": eff.display_name,
          "description": eff.description,
          "category": eff.category,
          "params": [
              {
                  "name": p.name,
                  "display_name": p.display_name,
                  "type": p.type.value,  # ParamType -> lowercase string
                  "default": p.default,
                  "min": p.min,
                  "max": p.max,
                  "decimals": p.decimals,
                  "values": list(p.values),
                  "value_labels": list(p.value_labels),
                  "keyframable": p.keyframable,
              }
              for p in eff.params
          ],
      }
  ```

### Step 4: Re-source `effect_list_common` from catalog
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Action:** modify the existing `effect_list_common` body (line ~3727). KEEP the `@mcp.tool()` decorator, function name, and signature `def effect_list_common() -> dict:`.
- **New body:**
  ```python
  try:
      from workshop_video_brain.edit_mcp.pipelines.effect_catalog import CATALOG
  except ModuleNotFoundError:
      return _err(
          "Effect catalog not generated. Run: "
          "uv run workshop-video-brain catalog regenerate"
      )
  effects = []
  for eff in CATALOG.values():
      desc = eff.description or ""
      short = desc if len(desc) <= 80 else desc[:80] + "..."
      effects.append({
          "kdenlive_id": eff.kdenlive_id,
          "mlt_service": eff.mlt_service,
          "display_name": eff.display_name,
          "category": eff.category,
          "short_description": short,
      })
  return _ok({"effects": effects})
  ```
- **Note:** Leave `effect_apply.list_common_effects` in place — out of scope to remove.

### Step 5: Verify MCP tool tests pass
- **Run:** `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py -v`
- **Expected:** all 9 tests PASS. (Requires `effect_catalog.py` generated by sub-spec 2 to exist.)

### Step 6: Add `catalog` subcommand group to CLI
- **File:** `workshop-video-brain/src/workshop_video_brain/app/cli.py`
- **Action:** modify — append a new section after the existing groups.
- **Pattern:** Follow the `@main.group()` -> `@workspace.command("create")` shape in lines 33-72.
- **Implementation:**
  ```python
  # ---------------------------------------------------------------------------
  # catalog group
  # ---------------------------------------------------------------------------


  @main.group()
  def catalog() -> None:
      """Effect catalog management commands."""


  @catalog.command("regenerate")
  @click.option("--no-upstream-check", is_flag=True, default=False,
                help="Skip the upstream Kdenlive cross-check.")
  @click.option("--output", default=None,
                help="Output path for generated catalog.py.")
  @click.option("--source-dir", default="/usr/share/kdenlive/effects/",
                help="Directory of Kdenlive effect XML files.")
  @click.option("--source-version", default=None,
                help="Override detected Kdenlive version string.")
  def catalog_regenerate(no_upstream_check: bool, output: str | None,
                         source_dir: str, source_version: str | None) -> None:
      """Regenerate the effect catalog from Kdenlive XML."""
      from pathlib import Path
      from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import (
          build_catalog, emit_python_module, _detect_source_version,
      )

      src = Path(source_dir)
      if not src.is_dir():
          click.echo(
              f"Error: source dir not found: {src}. "
              "Install Kdenlive or pass --source-dir.",
              err=True,
          )
          sys.exit(1)

      out = Path(output) if output else Path(
          "workshop-video-brain/src/workshop_video_brain/"
          "edit_mcp/pipelines/effect_catalog.py"
      )
      version = source_version or _detect_source_version()
      effects, diff = build_catalog(src, check_upstream=not no_upstream_check)
      emit_python_module(effects, out, version, diff)
      click.echo(
          f"Wrote {out}: {len(effects)} effects "
          f"(upstream check: {diff.upstream_check})"
      )
  ```

### Step 7: Verify CLI tests pass
- **Run:** `uv run pytest tests/unit/test_cli_catalog.py -v`
- **Expected:** all 4 tests PASS.

### Step 8: Run full suite for regressions
- **Run:** `uv run pytest tests/ -v`
- **Expected:** all tests PASS, including the prior baseline (~2357) plus the new tests from sub-specs 1, 2, and 3. Zero regressions.

### Step 9: Manual smoke test
- **Run:** `uv run workshop-video-brain catalog regenerate --help`
- **Expected:** prints help with `--no-upstream-check`, `--output`, `--source-dir`, `--source-version` listed.
- **Run:** `uv run python -c "from workshop_video_brain.edit_mcp.server.tools import effect_info, effect_list_common; r = effect_info('acompressor'); print(r['status'], len(r['data']['params'])); print(len(effect_list_common()['data']['effects']))"`
- **Expected:** `success 11`, then a number > 300.

### Step 10: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py workshop-video-brain/src/workshop_video_brain/app/cli.py tests/integration/test_effect_catalog_mcp_tools.py tests/unit/test_cli_catalog.py`
- **Message:** `feat: effect_info MCP tool, catalog-backed effect_list_common, catalog CLI`

## Acceptance Criteria

- `[STRUCTURAL]` `server/tools.py` registers new `@mcp.tool()` `effect_info(name: str) -> dict`.
- `[STRUCTURAL]` `effect_info` return shape: `{"status","data":{"kdenlive_id","mlt_service","display_name","description","category","params":[{"name","display_name","type","default","min","max","decimals","values","value_labels","keyframable"}]}}`.
- `[STRUCTURAL]` `effect_list_common` tool signature is unchanged from its current form; its body now iterates the catalog instead of a hardcoded dict.
- `[STRUCTURAL]` CLI has a new subcommand `catalog regenerate` accepting `--no-upstream-check` and `--output PATH` flags.
- `[INTEGRATION]` All new + changed tools are importable as callables from `workshop_video_brain.edit_mcp.server.tools` after module import.
- `[BEHAVIORAL]` `effect_info("acompressor")` returns the generated catalog's entry for `acompressor` with full param schema.
- `[BEHAVIORAL]` `effect_info("avfilter.acompressor")` returns the same entry.
- `[BEHAVIORAL]` `effect_info("nonexistent_effect")` returns `{"status":"error","message":"Effect not found: nonexistent_effect. Try `effect_list_common` for the registry."}`.
- `[BEHAVIORAL]` `effect_list_common()` returns `{"status":"success","data":{"effects":[{...}]}}` with entry count > 300.
- `[BEHAVIORAL]` Short description truncates at ~80 chars with ellipsis if longer.
- `[BEHAVIORAL]` CLI: `uv run workshop-video-brain catalog regenerate --no-upstream-check --output /tmp/cli_catalog.py --source-dir tests/unit/fixtures/effect_xml/` exits 0 and writes the file.
- `[MECHANICAL]` `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py tests/unit/test_cli_catalog.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.

## Completeness Checklist

`effect_info` response (success):

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| status | "success" | required | |
| data.kdenlive_id | str | required | |
| data.mlt_service | str | required | |
| data.display_name | str | required | |
| data.description | str | required (may be empty) | |
| data.category | str | required | "audio"/"video"/"custom" |
| data.params | list[dict] | required (may be empty) | one entry per ParamDef |
| data.params[i].name | str | required | |
| data.params[i].display_name | str | required | |
| data.params[i].type | str | required | lowercase enum value |
| data.params[i].default | str \| null | optional | |
| data.params[i].min | float \| null | optional | |
| data.params[i].max | float \| null | optional | |
| data.params[i].decimals | int \| null | optional | |
| data.params[i].values | list[str] | required (may be empty) | |
| data.params[i].value_labels | list[str] | required (may be empty) | |
| data.params[i].keyframable | bool | required | |

`effect_list_common` response entry:

| Field | Type | Required |
|-------|------|----------|
| kdenlive_id | str | required |
| mlt_service | str | required |
| display_name | str | required |
| category | str | required |
| short_description | str | required (may be empty) |

CLI subcommand `catalog regenerate` flags:

| Flag | Type | Default | Required |
|------|------|---------|----------|
| `--no-upstream-check` | flag | False | optional |
| `--output PATH` | str | `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` | optional |
| `--source-dir PATH` | str | `/usr/share/kdenlive/effects/` | optional |
| `--source-version STR` | str | auto-detect | optional |

Resource limits:
- `short_description` truncation threshold: 80 characters (longer descriptions get `desc[:80] + "..."`).
- Error message for not-found is exact-string-matched in tests; preserve verbatim.

## Verification Commands

- **Build:** `uv sync`
- **Tests:** `uv run pytest tests/ -v`
- **Acceptance:**
  - `uv run workshop-video-brain catalog regenerate --help` -> shows all flags.
  - `uv run python -c "from workshop_video_brain.edit_mcp.server.tools import effect_info; r = effect_info('acompressor'); assert r['status']=='success'; assert len(r['data']['params'])==11; print('ok')"`
  - `uv run python -c "from workshop_video_brain.edit_mcp.server.tools import effect_list_common; r = effect_list_common(); assert r['status']=='success'; assert len(r['data']['effects']) > 300; print(len(r['data']['effects']))"`
  - `uv run python -c "from workshop_video_brain.edit_mcp.server.tools import effect_info; print(effect_info('nonexistent'))"` -> exact error message.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` lines 3666-3735 (`effect_add`, `effect_list_common`): MCP tool style with `_ok`/`_err` helpers and lazy imports.
- `workshop-video-brain/src/workshop_video_brain/app/cli.py` lines 33-72 (`workspace` group): click group + command structure with sys.exit on error.
- `tests/integration/test_mcp_tools.py`: import tool callable directly from server.tools and assert response shape.
- `tests/unit/test_cli.py`: `click.testing.CliRunner` for CLI subcommand tests.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Add `effect_info` tool + helper; rewire `effect_list_common` body. |
| `workshop-video-brain/src/workshop_video_brain/app/cli.py` | Modify | Add `catalog` group with `regenerate` subcommand. |
| `tests/integration/test_effect_catalog_mcp_tools.py` | Create | MCP tool integration tests. |
| `tests/unit/test_cli_catalog.py` | Create | CLI subcommand unit tests. |
