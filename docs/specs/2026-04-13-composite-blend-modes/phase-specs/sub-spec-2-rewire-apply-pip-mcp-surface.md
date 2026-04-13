---
type: phase-spec
master_spec: "../../2026-04-13-composite-blend-modes.md"
sub_spec_number: 2
title: "Rewire apply_pip + MCP Surface"
date: 2026-04-13
dependencies: [1]
---

# Sub-Spec 2: Rewire apply_pip + MCP Surface

Refined from spec.md -- Factory Run ff-2026-04-13-composite-blend-modes.

## Scope

Rewire `apply_pip` to delegate to `apply_composite` (from Sub-Spec 1) without changing its public signature. Register new MCP tool `composite_set` in `server/tools.py`. Add integration test exercising `composite_set` end-to-end against fixture `keyframe_project.kdenlive`. Add a regression test for `apply_pip` ensuring its externally observable output remains equivalent to the pre-rewire behavior.

### CRITICAL CONTEXT (from Stage 3 analysis)

Pre-rewire, `apply_pip` emits `AddComposition(composition_type="composite", params={"geometry": ...})`. The `composite` MLT service carries no blend-mode property. Post-rewire through `apply_composite(blend_mode="cairoblend")`, the emitted `composition_type` becomes `"frei0r.cairoblend"` and `params` gains a `"1": "normal"` entry. **This is NOT byte-identical to pre-rewire output.** Master spec Requirement 11 requires "visually unchanged" and Acceptance criterion asks for "byte-identical OR serialize_project string comparison". The worker must interpret this: a semantic regression test (same visual result in Kdenlive) is acceptable; byte-identical serialized XML is NOT achievable given the service change.

The interpretation taken here: the regression test compares the STRUCTURAL contract (transition exists, spans correct tracks, correct frame range, correct geometry) rather than raw bytes. This is called out in the Escalation Triggers below.

## Interface Contracts

### Provides
- New MCP tool `composite_set` at `server/tools.py`, callable via FastMCP with the exact signature in the Completeness Checklist.
- Unchanged public surface: `composite_pip` MCP tool, `composite_wipe` MCP tool, `apply_pip` function, `apply_wipe` function (only `apply_pip`'s internals change).

### Requires
- From Sub-Spec 1: `BLEND_MODES`, `BLEND_MODE_TO_MLT`, `apply_composite` -- all exported from `pipelines.compositing`.

### Shared State
None.

## Escalation Triggers

1. **Byte-identical regression for `apply_pip` is NOT achievable** because the service name on the emitted `<transition>` changes from `composite` to `frei0r.cairoblend`. Worker implements a structural-equivalence regression test instead. If the user requires byte-identity, STOP and report.
2. **Kdenlive fixture compatibility:** If `keyframe_project.kdenlive` does not have at least 5 tracks (we need `track_a=1`, `track_b=4`), pick smaller track indices that do exist in the fixture and update the integration test. Inspect the fixture at `tests/integration/fixtures/keyframe_project.kdenlive` first.

## Implementation Steps

### Step 1: Write failing regression test for apply_pip
- **File:** `tests/unit/test_apply_pip_regression.py`
- **Purpose:** lock in externally observable `apply_pip` behavior using structural equivalence (not byte-identity).
- **Test:** `test_apply_pip_emits_expected_transition_structure`
  - Build a minimal `KdenliveProject` (1920x1080 profile).
  - Call `apply_pip(project, overlay_track=2, base_track=1, start_frame=0, end_frame=120, layout=PipLayout(x=1440, y=780, width=480, height=270))`.
  - Assert the returned project has exactly one more `opaque_element` than input.
  - Parse the opaque element XML; assert:
    - Tag is `transition`.
    - `mlt_service` attribute is `"frei0r.cairoblend"` (post-rewire).
    - Has `<property name="a_track">1</property>`, `<property name="b_track">2</property>`, `<property name="in">0</property>`, `<property name="out">120</property>`.
    - Has `<property name="geometry">1440/780:480x270:100</property>`.
    - Has `<property name="1">normal</property>` (the blend-mode property from `BLEND_MODE_TO_MLT["cairoblend"]`).
- **Run:** `uv run pytest tests/unit/test_apply_pip_regression.py -v`
- **Expected:** FAIL (pre-rewire `apply_pip` emits `mlt_service="composite"` without `<property name="1">`).

### Step 2: Rewire `apply_pip` to delegate to `apply_composite`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py`
- **Action:** modify
- **Changes:** Replace `apply_pip` body (lines 40-58) while keeping the public signature identical:
  ```python
  def apply_pip(
      project: KdenliveProject,
      overlay_track: int,
      base_track: int,
      start_frame: int,
      end_frame: int,
      layout: PipLayout,
  ) -> KdenliveProject:
      """Add a PiP composite composition via the shared apply_composite path."""
      geometry = f"{layout.x}/{layout.y}:{layout.width}x{layout.height}:100"
      return apply_composite(
          project,
          track_a=base_track,
          track_b=overlay_track,
          start_frame=start_frame,
          end_frame=end_frame,
          blend_mode="cairoblend",
          geometry=geometry,
      )
  ```
- **Note:** Preserve the `track_a=base, track_b=overlay` ordering used before to keep any downstream parse consistent.

### Step 3: Confirm apply_pip regression test now passes
- **Run:** `uv run pytest tests/unit/test_apply_pip_regression.py -v`
- **Expected:** PASS.

### Step 4: Write failing integration test for composite_set
- **File:** `tests/integration/test_composite_set_mcp_tool.py`
- **Pattern to follow:** `tests/integration/test_mcp_tools.py` and `tests/integration/test_masking_mcp_tools.py` for workspace setup + fixture-project copy + snapshot assertions.
- **Tests (initial failures):**
  1. `test_composite_set_screen_writes_cairoblend_transition` -- invoke tool with `blend_mode="screen"` on a temp-workspace copy of `keyframe_project.kdenlive`; reparse the written file; assert a `<transition mlt_service="frei0r.cairoblend">` exists with `<property name="1">screen</property>` between the specified tracks.
  2. `test_composite_set_destination_in_writes_qtblend` -- invoke with `blend_mode="destination_in"`; reparse; assert `<transition mlt_service="qtblend">` with `<property name="compositing">6</property>`.
  3. `test_composite_set_unknown_mode_returns_err` -- `blend_mode="bogus"` returns `{"status":"error", ...}` whose error message contains all 11 valid mode names.
  4. `test_composite_set_same_track_returns_err` -- `track_a == track_b` returns error.
  5. `test_composite_set_bad_frames_returns_err` -- `end_frame <= start_frame` returns error.
  6. `test_composite_set_creates_snapshot` -- after a successful call, a new entry exists under the workspace's snapshots dir; tool response `data.snapshot_id` is that entry's id and exists on disk.
  7. `test_composite_set_custom_geometry` -- `geometry="100/50:1920x1080:75"` is present verbatim in the written transition.
  8. `test_composite_set_return_shape` -- success response is `{"status":"ok","data":{"composition_added": True, "blend_mode": "screen", "track_a": <int>, "track_b": <int>, "snapshot_id": <str>}}`.
  9. `test_composite_set_importable` -- `from workshop_video_brain.edit_mcp.server.tools import composite_set, composite_pip, composite_wipe` all succeed (criterion `[INTEGRATION]`).
- **Fixture note:** verify `keyframe_project.kdenlive` has the required tracks. If not, use track indices that exist there.
- **Run:** `uv run pytest tests/integration/test_composite_set_mcp_tool.py -v`
- **Expected:** FAIL (tool not registered yet).

### Step 5: Register `composite_set` MCP tool
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Action:** modify -- add new `@mcp.tool()`-decorated function directly below `composite_wipe` (~line 4320).
- **Pattern:** mirror `composite_pip` (lines 4240-4282) exactly for workspace/snapshot/parse/serialize flow.
- **Function:**
  ```python
  @mcp.tool()
  def composite_set(
      workspace_path: str,
      project_file: str,
      track_a: int,
      track_b: int,
      start_frame: int,
      end_frame: int,
      blend_mode: str = "cairoblend",
      geometry: str = "",
  ) -> dict:
      """Add a composite transition between two tracks with a named blend mode."""
      from workshop_video_brain.edit_mcp.pipelines.compositing import (
          apply_composite, BLEND_MODES,
      )
      from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
      from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
      from workshop_video_brain.workspace import create_snapshot

      try:
          ws_path, workspace = _require_workspace(workspace_path)
      except (ValueError, FileNotFoundError) as exc:
          return _err(str(exc))

      proj_path = ws_path / project_file
      if not proj_path.exists():
          return _err(f"Project file not found: {project_file}")

      if blend_mode not in BLEND_MODES:
          return _err(
              f"Unknown blend_mode '{blend_mode}'; valid modes: {sorted(BLEND_MODES)}"
          )

      snapshot = create_snapshot(
          ws_path, proj_path, description=f"before_composite_{blend_mode}"
      )

      project = parse_project(proj_path)
      try:
          geom = geometry if geometry else None
          updated = apply_composite(
              project,
              track_a=track_a,
              track_b=track_b,
              start_frame=start_frame,
              end_frame=end_frame,
              blend_mode=blend_mode,
              geometry=geom,
          )
      except ValueError as exc:
          return _err(str(exc))

      serialize_project(updated, proj_path)
      return _ok({
          "composition_added": True,
          "blend_mode": blend_mode,
          "track_a": track_a,
          "track_b": track_b,
          "snapshot_id": str(snapshot),  # adapt to whatever create_snapshot returns
      })
  ```
- **Adapt `snapshot_id`** to the actual return shape of `create_snapshot` -- inspect signature first at `workshop_video_brain/workspace.py`. `composite_pip` calls `create_snapshot(...)` for side-effect only; `composite_set` must thread the returned id.
- `composite_pip` and `composite_wipe` remain untouched.

### Step 6: Run integration tests
- **Run:** `uv run pytest tests/integration/test_composite_set_mcp_tool.py tests/unit/test_apply_pip_regression.py -v`
- **Expected:** PASS.

### Step 7: Full regression
- **Run:** `uv run pytest tests/ -v`
- **Expected:** all previously passing tests still pass. Any test that asserted `apply_pip` produced `mlt_service="composite"` must be updated; check `tests/unit/test_compositing.py` and `tests/integration/test_mcp_tools.py` for such assertions. If found, update them to expect `frei0r.cairoblend` (this is a legitimate consequence of the rewire).

### Step 8: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py tests/integration/test_composite_set_mcp_tool.py tests/unit/test_apply_pip_regression.py` (plus any legacy test updates).
- **Message:** `feat: rewire apply_pip + mcp composite_set surface`

## Acceptance Criteria

- `[STRUCTURAL]` `server/tools.py` registers `composite_set` via `@mcp.tool()`.
- `[STRUCTURAL]` `composite_set` signature: `(workspace_path: str, project_file: str, track_a: int, track_b: int, start_frame: int, end_frame: int, blend_mode: str = "cairoblend", geometry: str = "") -> dict`.
- `[STRUCTURAL]` `composite_set` return shape on success: `{"status":"ok","data":{"composition_added": true, "blend_mode": str, "track_a": int, "track_b": int, "snapshot_id": str}}`.
- `[STRUCTURAL]` `apply_pip` signature unchanged; body delegates to `apply_composite`.
- `[STRUCTURAL]` `apply_wipe` unchanged.
- `[STRUCTURAL]` MCP `composite_pip` and `composite_wipe` signatures unchanged.
- `[INTEGRATION]` All three MCP tools importable as callables from `workshop_video_brain.edit_mcp.server.tools`.
- `[BEHAVIORAL]` End-to-end `composite_set` with `blend_mode="screen"` -- reparsed `.kdenlive` shows the correct transition between tracks carrying the screen blend value.
- `[BEHAVIORAL]` `composite_set` with `blend_mode="destination_in"` writes the correct MLT value from `BLEND_MODE_TO_MLT` (on the `qtblend` service).
- `[BEHAVIORAL]` `composite_set` with unknown `blend_mode` returns `_err` listing all 11 valid modes.
- `[BEHAVIORAL]` `composite_set` with `track_a == track_b` returns `_err`.
- `[BEHAVIORAL]` `composite_set` with `end_frame <= start_frame` returns `_err`.
- `[BEHAVIORAL]` `composite_set` creates a snapshot on disk; `snapshot_id` is returned in the response.
- `[BEHAVIORAL]` `composite_set` with `geometry="100/50:1920x1080:75"` writes geometry verbatim.
- `[BEHAVIORAL]` `apply_pip` regression -- structural equivalence test passes (byte-identity N/A due to service-name change; see Escalation Trigger 1).
- `[MECHANICAL]` `uv run pytest tests/integration/test_composite_set_mcp_tool.py tests/unit/test_apply_pip_regression.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` passes.

## Completeness Checklist

### `composite_set` parameters

| Field          | Type  | Required | Default       | Notes |
|----------------|-------|----------|---------------|-------|
| workspace_path | str   | required | --            | passed to `_require_workspace` |
| project_file   | str   | required | --            | relative to workspace root |
| track_a        | int   | required | --            | |
| track_b        | int   | required | --            | must differ from track_a |
| start_frame    | int   | required | --            | |
| end_frame      | int   | required | --            | must be > start_frame |
| blend_mode     | str   | optional | "cairoblend"  | must be in BLEND_MODES |
| geometry       | str   | optional | ""            | "" -> default full-frame |

### `composite_set` success response data keys

| Key               | Type | Required |
|-------------------|------|----------|
| composition_added | bool | required (always `true` on success) |
| blend_mode        | str  | required |
| track_a           | int  | required |
| track_b           | int  | required |
| snapshot_id       | str  | required |

### Error return contract
- Unknown blend_mode -> `_err` string MUST contain every valid mode name.
- `track_a == track_b` -> `_err`.
- `end_frame <= start_frame` -> `_err`.
- Missing project file -> `_err` mentioning filename.
- Invalid workspace -> `_err` via existing `_require_workspace`.

## Verification Commands

- **Build:** `uv sync`
- **Unit regression:** `uv run pytest tests/unit/test_apply_pip_regression.py -v`
- **Integration:** `uv run pytest tests/integration/test_composite_set_mcp_tool.py -v`
- **Full:** `uv run pytest tests/ -v`
- **Manual (Kdenlive):** per master spec Verification step 2, open a produced `.kdenlive` with `blend_mode="screen"` in Kdenlive 25.x and confirm visual screen blend.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:4240` (`composite_pip`) -- canonical MCP tool template: workspace guard, path existence check, snapshot, parse, pipeline call under try/except ValueError, serialize, `_ok` response.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py:40` (`apply_pip`) -- the body we are rewriting.
- `tests/integration/test_masking_mcp_tools.py` and `tests/integration/test_mcp_tools.py` -- workspace fixture + copy-of-fixture pattern for integration tests.
- `tests/integration/fixtures/keyframe_project.kdenlive` -- real Kdenlive project for reparse assertions.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py` | Modify | Rewire `apply_pip` to delegate to `apply_composite`. |
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Register `@mcp.tool() composite_set`. |
| `tests/integration/test_composite_set_mcp_tool.py` | Create | End-to-end tests for the new MCP tool. |
| `tests/unit/test_apply_pip_regression.py` | Create | Structural-equivalence regression for `apply_pip` rewire. |
| `tests/unit/test_compositing.py` (potentially) | Modify | Update any assertions that pinned `mlt_service="composite"` to expect `"frei0r.cairoblend"`. |
