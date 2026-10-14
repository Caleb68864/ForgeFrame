# Prompt 19: edit effects already applied to a clip (get/set params, toggle, remove)

Read `docs/prompts/00-README.md` first. Its shared rules (shell, tests, code
conventions, report format) apply and are not repeated here.

**Summary.** ForgeFrame can *add* effects to a clip (`effect_add`, ~40 effect
bundles), find one (`effect_find`), keyframe one (`effect_keyframe_set_*`) and
reorder the stack (`effect_reorder`, `move_up`...). It cannot list a clip's
applied effects with their values, change a static parameter on an applied
effect, switch an effect off without deleting it, or delete it. This task adds
those five tools as thin shells over new patcher intents, with unit tests and an
external melt render proof (a disabled effect stops changing pixels). Depends
on prompt 03, which gives every emitted filter a Kdenlive identity
(`kdenlive_id` etc.) so Kdenlive 26.08 keeps it on load.

## What already exists (reuse it, do not re-roll)

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/effect_stack.py`
  (re-exported by `patcher.py`):
  - `_iter_clip_filters(project, (track, clip_index))` (line ~37): a clip's
    effects are `OpaqueElement(tag="filter")` entries in
    `project.opaque_elements` carrying `track="<playlist index>"` and
    `clip_index="<n>"` attributes, where `<n>` counts **non-blank** entries.
    `effect_index` is the position in that clip's filter subset.
  - `list_effects` (~83) returns `[{index, mlt_service, kdenlive_id, properties}]`.
  - `get_effect_property` (~114), `set_effect_property` (~139),
    `remove_effect` (~214). All raise `IndexError` on a bad index.
- `edit_mcp/pipelines/effect_find.py::find(project, clip_ref, name)`: resolves
  a name to an index, matching `kdenlive_id` first, then `mlt_service`; raises
  `LookupError` (no match) or `ValueError` (ambiguous).
- `edit_mcp/server/tools/keyframes.py`: `effect_find` (~214) and
  `effect_keyframe_set_scalar/rect/color`. Keyframed values belong to these.
- `edit_mcp/pipelines/effect_catalog.py`: `CATALOG`, `find_by_name(kdenlive_id)`,
  `find_by_service(mlt_service)`; each `EffectDef.params` is a tuple of
  `ParamDef(name=..., keyframable=...)`.
- `edit_mcp/server/tools/effects_catalog.py::effect_add` (~39): the shell
  pattern to copy (`workspace_path`, `project_file` relative to the workspace,
  `track` = **playlist index** into `project.playlists`).
- Serializer: `serializer._extract_clip_filters` nests each filter inside its
  `<entry>`; the parser reverses this. Arbitrary `<property>` children survive
  the round trip, so a `disable` property needs no serializer change.

### Idea harvested from another project (reimplemented, not copied)

Another Kdenlive MCP server exposes: get every parameter of an applied effect
(static values plus keyframed ones, reported separately); get one parameter
(error if it is keyframed, pointing at the keyframe tool); set one static
parameter (refused for a keyframed parameter, pointing at the keyframe tool);
enable/disable an effect without removing it (written to the file as the MLT
filter property `disable=1`, absent or `0` when enabled); remove one effect.
MLT itself skips any filter whose `disable` property is `1`; Kdenlive's effect
on/off switch writes exactly that property. Identify effects by our existing
scheme (index in the stack, or name via `effect_find`), not by their ids.

## Steps

1. **Intents** in `workshop-video-brain/src/workshop_video_brain/core/models/timeline.py`,
   next to `AddEffect` (~188):
   - `SetEffectParams(track_index: int, clip_index: int, effect_index: int, params: dict[str, str])`
   - `SetEffectEnabled(track_index: int, clip_index: int, effect_index: int, enabled: bool = True)`
   - `RemoveEffect(track_index: int, clip_index: int, effect_index: int)`
2. **Apply functions** in `adapters/kdenlive/patcher_intents.py`, after
   `_apply_add_effect` (~1197), plus dispatch branches in `patch_project` (~174)
   and a line each in its docstring list:
   - Call `effect_stack.set_effect_property` / `remove_effect`. On
     `IndexError`, `logger.warning("...: ... - skipped.")` and return. The word
     "skipped" is what `PatchReport` uses to classify a no-op; keep it.
   - `SetEffectEnabled(enabled=False)` sets `disable` to `"1"`. `enabled=True`
     sets it to `"0"` (do not delete the property; Kdenlive writes `0`).
3. **Pipeline** `edit_mcp/pipelines/effect_edit.py` (pure, no I/O):
   - `resolve_effect_index(project, clip_ref, effect_index: int, effect_name: str) -> int`:
     exactly one of the two must be given (`effect_index >= 0` or a non-empty
     name); a name goes through `effect_find.find`. Raise `ValueError` for
     "both/neither", let `LookupError`/`IndexError` propagate.
   - `describe_effect(effect: dict) -> dict`: from one `list_effects` row return
     `{index, kdenlive_id, mlt_service, enabled, static_params, keyframed_params}`.
     `enabled` is `properties.get("disable", "0") != "1"`. A value is keyframed
     when it contains `=` and either `;` or a `HH:MM:SS.mmm` timestamp (reuse
     the timestamp regex in `pipelines/keyframes.py`). Exclude bookkeeping
     keys (`mlt_service`, `kdenlive_id`, `disable`, and anything starting with
     `kdenlive:`) from `static_params`.
   - `check_param_names(kdenlive_id, mlt_service, names) -> list[str]`: names
     the catalog does not know for this effect (empty list if the effect is not
     in the catalog: unknown effects are allowed, as in `effect_add`). Look the
     effect up with `find_by_service(mlt_service)` first and
     `find_by_name(kdenlive_id)` second: prompt 03 found that `CATALOG` keys
     are file stems, not the Kdenlive registry ids it now writes into
     `kdenlive_id` (see its `normalize_effect_id`).
   - `PROTECTED_PARAMS = {"mlt_service", "kdenlive_id", "disable"}`.
4. **Tools**: new module `edit_mcp/server/bundles/effect_edit.py`, each with
   `@mcp.tool()` then `@tool_guard`. Common leading parameters:
   `workspace_path: str, project_file: str, track: int, clip_index: int,
   effect_index: int = -1, effect_name: str = ""`.
   - `effect_list_applied(workspace_path, project_file, track, clip_index)`:
     read-only; returns `describe_effect` for every effect in stack order.
   - `effect_param_get(..., param: str = "")`: read-only; empty `param` returns
     the whole description; otherwise `{param, value, keyframed}`; a missing
     param is `not_found(...)` listing the names that are set.
   - `effect_param_set(..., params: str)`: `params` is a JSON object string
     (same convention as `effect_add`; bad JSON -> `bad_json_param`). Refuse
     `PROTECTED_PARAMS` (suggest `effect_toggle` for `disable`), refuse a
     currently keyframed param (suggest `effect_keyframe_set_scalar`/`_rect`),
     refuse names from `check_param_names` unless `force: bool = True` was
     passed. Values are stringified (`True`->`"1"`, numbers via `str`).
     Return old and new values.
   - `effect_toggle(..., enabled: bool)`: returns the previous and new state.
   - `effect_remove(...)`: returns the removed effect's description and the
     new stack length.
   - Order inside every writing tool: parse (catch `ProjectParseError` ->
     `corrupt_project`) -> validate (`invalid_index` for track/clip/effect,
     `invalid_input` for both/neither identifiers) -> `patch_project(...,
     with_report=True)` (all skipped -> `invalid_input`) -> `create_snapshot`
     (as `bundles/pan_zoom.py` ~205 does, to get `snapshot_id`) ->
     `serialize_project` -> `_ok({..., "snapshot_id": ...})`.
   - Use only the error constructors you need. Do not hand-parse XML in the
     shell.

## Tests

1. **Unit** `tests/unit/test_effect_edit.py`. Build projects with
   `tests/_testkit.py` (`solid_color_project`, `sequence_project`); add effects
   with `AddEffect` intents; save into a minimal workspace under `tmp_path`
   (copy the `_make_workspace` helper pattern from
   `tests/unit/test_nle_operations.py` ~73: `workspace.yaml` +
   `projects/working_copies/<slug>_v1.kdenlive`). Cover:
   - intents: set/toggle/remove change exactly the targeted filter, on the
     right clip, and leave other clips' filters untouched;
   - out-of-range index -> `PatchReport.skipped`;
   - tools via `call_tool`/`unwrap`: name vs index resolution, ambiguous name,
     both/neither identifiers, protected and keyframed param refusals,
     `force`, bad JSON, round trip (set -> serialize -> parse -> get returns the
     new value; toggle -> `disable` is `1` then `0`);
   - `assert_registered("effect_list_applied", "effect_param_get",
     "effect_param_set", "effect_toggle", "effect_remove")`.
2. **External render proof** `tests/integration/external/test_effect_edit_render.py`
   (copy the style of `test_effect_visible.py`; it already has a base-vs-effect
   oracle). Use the hermetic colour builders, `render_frame`, `frames_differ`,
   `frames_similar`, `mean_color` from `_oracle.py`:
   - red clip + `avfilter.negate` added through the same code path as
     `effect_add` (so it carries prompt 03's `kdenlive_id`): frame differs
     from the plain red render;
   - `effect_toggle(enabled=False)`: frame is similar to plain red again;
   - toggle back on: differs again;
   - `effect_remove`: similar to plain red;
   - `effect_param_set` on an MLT `brightness` filter (`level` 1.0 -> 0.3):
     the red channel of `mean_color` drops by a clear margin (assert > 30%).
   - Optional blur variant: on a `make_test_clip(kind="video")` clip
     (`requires_ffmpeg`), disabling `avfilter.gblur` makes the frame similar
     to the unblurred render again.
3. **Kdenlive check** (if `tests/_testkit.py` has `requires_kdenlive` from
   prompt 01): render the "disabled negate" project with
   `xvfb-run -a kdenlive --render` and assert it matches the melt render.
   If the mark does not exist, do this once by hand and put the PSNR in the
   report.

## Acceptance criteria

- The five tools are registered and pass their unit tests.
- Disabling an effect is visible as "no effect" in a melt render, and the
  effect is still in the file with `disable=1`.
- Removing, toggling or editing one effect never changes any other clip's
  filters or any other effect in the same stack.
- Full suite green; ruff clean on touched files.

## Do NOT

- Do not rename the legacy `clip` parameter on existing tools; new tools use
  `clip_index` (CLAUDE.md "Tool Parameter Naming").
- Do not change how filters are stored (`track`/`clip_index` attributes) or
  the serializer. Do not touch prompt 03's identity logic.
- Do not edit keyframed values here; point to the keyframe tools instead.
- Do not delete the `disable` property on re-enable; write `0`.

## When done

1. Add the five tools to `workshop-video-brain/skills/ff-effect-cookbook/SKILL.md`
   (short "inspect / tweak / bypass / remove an applied effect" section).
2. Add a paragraph to `vault/wiki/kdenlive-avfilter-and-effect-zones.md` on
   the `disable` property (MLT skips the filter; Kdenlive's on/off switch).
3. Regenerate `docs/capabilities.md`.
4. Mark Phase 4 item 3 done in `docs/plans/2026-10-13-media-mcp-expansion.md`.
5. Report as in `00-README.md`, including the mean-colour numbers and any
   Kdenlive-vs-melt PSNR.
