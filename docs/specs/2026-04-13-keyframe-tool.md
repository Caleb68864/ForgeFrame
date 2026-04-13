# Keyframe Tool for Kdenlive MCP

## Meta
- Client: ForgeFrame (self)
- Project: Workshop Video Brain
- Repo: /home/caleb/Projects/ForgeFrame
- Date: 2026-04-13
- Author: Caleb Bennett
- Status: completed
- Executed: 2026-04-13
- Result: 4/4 sub-specs passed (2313 tests, 0 regressions)
- Design Doc: `docs/plans/2026-04-13-keyframe-tool-design.md`
- Quality Scores (7 dims / 35): Outcome 5 · Scope 5 · Decisions 4 · Edges 5 · Criteria 4 · Decomposition 4 · Purpose 5 · **Total 32/35**

## Outcome
Three typed MCP tools (`effect_keyframe_set_scalar`, `effect_keyframe_set_rect`, `effect_keyframe_set_color`) plus an `effect_find` helper write MLT keyframe-animation strings into `<property>` elements of `<filter>` nodes in a `.kdenlive` project. Animations written by these tools render correctly in Kdenlive 25.x / MLT 7.36 with full easing support across all 40+ MLT keyframe types.

## Intent
**Trade-off hierarchy (highest priority first):**
1. Correctness of MLT output over runtime performance (re-read fps per call; don't cache)
2. LLM-friendly API clarity over tool-count minimization (three typed tools, not one polymorphic)
3. Explicit caller intent over hidden magic (replace is default; merge must be requested)
4. Generic primitive over ergonomic wrapper (primitive ships first; wrappers layer on top in Spec 7)

**Preferences:**
- Prefer additive changes to `patcher.py`; do not refactor existing methods
- Prefer the workspace `workspace.yaml` as per-video config home; no new global config files
- Prefer hardcoded fallback (`cubic`) over failure when workspace config is absent

**Escalation triggers (agent should stop and ask):**
- Any change to `.kdenlive` serializer output for non-keyframe properties (out of scope)
- Introduction of new dependencies beyond what's already in `pyproject.toml`
- Changes to existing `effect_add`, `effect_list_common`, or `composite_*` tool signatures

## Context
ForgeFrame is a local-first video production assistant built as a Claude Code plugin marketplace. The `workshop-video-brain` MCP server exposes tools that drive Kdenlive projects via direct `.kdenlive` XML manipulation (parser + patcher + serializer). The current `effect_add` tool writes static property values only; it cannot express animation. This blocks ~80% of the motion-graphics techniques identified in four analyzed tutorial videos (`transcripts/iu0gI30NZ8M.en.vtt`, `Fh1xhOzfjBE.en.vtt`, `OO4STGUXWl8.en.vtt`, `cVCRmUXj87Q.en.vtt`).

Decisions locked during design discussion are captured in `EFFECTS_DISCUSSION.md` and the design doc. Authoritative MLT keyframe-operator table sourced from `mltframework/mlt` `src/framework/mlt_animation.c` `keyframe_type_map[]`. Target runtime: Kdenlive 25.12 / MLT 7.36.

Key files touched:
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` (extended)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/keyframes.py` (new)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_find.py` (new)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended)
- `workshop-video-brain/src/workshop_video_brain/core/models/workspace.py` (extended — `keyframe_defaults` field)

## Requirements

1. Three typed MCP tools exist and are registered: `effect_keyframe_set_scalar`, `effect_keyframe_set_rect`, `effect_keyframe_set_color`.
2. An `effect_find(workspace, track, clip, name) -> int` MCP tool exists and resolves filters by `kdenlive_id` (preferred) or `mlt_service` string.
3. Time inputs accept a union of `{"frame": int}`, `{"seconds": float}`, `{"timestamp": "HH:MM:SS.mmm"}`; internal storage is MLT timestamp format.
4. Easing accepts both abstract names (`linear`, `hold`, `smooth`, `smooth_natural`, `smooth_tight`, `ease_in`, `ease_out`, `ease_in_out`, all `ease_in_<family>` and `<family>_in` aliases for sine/quad/cubic/quart/quint/expo/circ/back/elastic/bounce) AND raw MLT operators (bare `=`, `~=`, `|=`, `$=`, `-=`, `a=`..`D=`).
5. The abstract `ease_in` / `ease_out` / `ease_in_out` aliases resolve via the workspace `keyframe_defaults.ease_family` config; default is `cubic` when unset.
6. `mode` parameter accepts `"replace"` (default) and `"merge"`; merge overwrites same-frame keyframes rather than stacking.
7. Rect values accept both 4-tuple `[x, y, w, h]` (implicit opacity=1) and 5-tuple `[x, y, w, h, opacity]`.
8. FPS is re-read from the `.kdenlive` project profile on every call (no caching).
9. Existing project safety policy (auto-snapshot per MCP call) is honored.
10. All tools raise precise errors with actionable context (what's available, what's valid).
11. Unit tests cover: time normalization, easing resolution, keyframe string build/parse round-trip, merge logic, same-frame merge overwrite, rect 4/5-tuple handling, error cases.
12. Integration test: the four new MCP tools import and execute from `server/tools.py` against a fixture `.kdenlive` project; written keyframes parse back identically.

## Sub-Specs

### Sub-Spec 1: Patcher Effect-Property Extensions
**Scope.** Add three methods to the existing Kdenlive patcher: `get_effect_property`, `set_effect_property`, `list_effects`. Additive only — do not modify existing methods.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` (extended)
- `tests/unit/test_patcher_effect_properties.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` `patcher.py` exports `get_effect_property(clip_ref, effect_index, property_name) -> str | None`.
- `[STRUCTURAL]` `patcher.py` exports `set_effect_property(clip_ref, effect_index, property_name, value: str) -> None`.
- `[STRUCTURAL]` `patcher.py` exports `list_effects(clip_ref) -> list[dict]` where each dict has keys `index`, `mlt_service`, `kdenlive_id`, `properties` (dict).
- `[BEHAVIORAL]` Given a fixture `.kdenlive` with a transform filter on clip (track=2, index=0), `get_effect_property((2,0), 0, "rect")` returns the existing rect string.
- `[BEHAVIORAL]` Calling `set_effect_property((2,0), 0, "rect", "00:00:00.000=0 0 1920 1080 1")` mutates the in-memory project tree; subsequent `get_effect_property` returns the new string.
- `[BEHAVIORAL]` `list_effects((2,0))` returns filters in stack order with their properties.
- `[BEHAVIORAL]` `get_effect_property` on a non-existent property returns `None`; on a non-existent effect_index or clip raises `IndexError` or equivalent with clear message.
- `[MECHANICAL]` `uv run pytest tests/unit/test_patcher_effect_properties.py -v` passes.

**Dependencies.** none

---

### Sub-Spec 2: Keyframes Pipeline Module
**Scope.** New `pipelines/keyframes.py` owning time normalization, easing resolution, MLT keyframe-string build/parse, and replace/merge logic. No XML I/O, no MCP concerns.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/keyframes.py` (new)
- `tests/unit/test_keyframes_pipeline.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` Module exports `normalize_time(input: dict, fps: float) -> str` accepting the time union.
- `[STRUCTURAL]` Module exports `resolve_easing(name_or_operator: str, ease_family_default: str = "cubic") -> str` returning the single-char MLT operator prefix (`""` for linear).
- `[STRUCTURAL]` Module exports `build_keyframe_string(kind: Literal["scalar","rect","color"], keyframes: list[Keyframe], fps: float, ease_family_default: str) -> str`.
- `[STRUCTURAL]` Module exports `parse_keyframe_string(kind: Literal["scalar","rect","color"], s: str) -> list[Keyframe]`.
- `[STRUCTURAL]` Module exports `merge_keyframes(existing: list[Keyframe], new: list[Keyframe]) -> list[Keyframe]`.
- `[STRUCTURAL]` `Keyframe` dataclass/TypedDict has fields `frame: int`, `value: Any`, `easing: str`.
- `[BEHAVIORAL]` `normalize_time({"frame": 60}, 30.0)` returns `"00:00:02.000"`.
- `[BEHAVIORAL]` `normalize_time({"seconds": 2.0}, 30.0)` returns `"00:00:02.000"`.
- `[BEHAVIORAL]` `normalize_time({"timestamp": "00:00:02.000"}, 30.0)` returns `"00:00:02.000"`.
- `[BEHAVIORAL]` `resolve_easing("linear")` returns `""`; `resolve_easing("smooth")` returns `"~"`; `resolve_easing("hold")` returns `"|"`; `resolve_easing("ease_in_out_expo")` returns `"r"`; `resolve_easing("ease_in", ease_family_default="expo")` returns `"p"`; `resolve_easing("$=")` returns `"$"`.
- `[BEHAVIORAL]` `build_keyframe_string("rect", [{frame:0, value:[0,0,1920,1080,1], easing:"linear"}, {frame:60, value:[100,50,1920,1080,0.5], easing:"ease_in_out"}], 30.0, "cubic")` returns `"00:00:00.000=0 0 1920 1080 1;00:00:02.000i=100 50 1920 1080 0.5"`.
- `[BEHAVIORAL]` `build_keyframe_string` for `rect` accepts 4-tuple `[x,y,w,h]` and emits `"x y w h 1"` (opacity defaults to 1).
- `[BEHAVIORAL]` `parse_keyframe_string` round-trips values produced by `build_keyframe_string` for scalar, rect, and color kinds.
- `[BEHAVIORAL]` `merge_keyframes` with overlapping frame overwrites the existing keyframe at that frame and keeps others sorted by frame.
- `[BEHAVIORAL]` `merge_keyframes` with a non-keyframe static string on existing (no `;`, no `=`) treats it as a single keyframe at frame 0.
- `[BEHAVIORAL]` Invalid time input (missing all three keys, negative frame, malformed timestamp) raises `ValueError` with the offending key in the message.
- `[BEHAVIORAL]` Unknown easing name raises `ValueError` listing the valid abstract-name set.
- `[BEHAVIORAL]` Unknown raw operator char raises `ValueError` referencing the MLT operator table.
- `[MECHANICAL]` `uv run pytest tests/unit/test_keyframes_pipeline.py -v` passes.

**Dependencies.** none

---

### Sub-Spec 3: Effect-Find Module + Workspace Config Extension
**Scope.** New `pipelines/effect_find.py` for name-based effect lookup. Extend the workspace model to include a `keyframe_defaults.ease_family` field read from `workspace.yaml`.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_find.py` (new)
- `workshop-video-brain/src/workshop_video_brain/core/models/workspace.py` (extended)
- `tests/unit/test_effect_find.py` (new)
- `tests/unit/test_workspace_keyframe_defaults.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` `effect_find.py` exports `find(project, clip_ref, name: str) -> int`.
- `[STRUCTURAL]` Workspace model (Pydantic or dataclass — match existing pattern) has a `keyframe_defaults` field with `ease_family: Literal[...]` valid values: `sine`, `quad`, `cubic`, `quart`, `quint`, `expo`, `circ`, `back`, `elastic`, `bounce`. Default `cubic`.
- `[STRUCTURAL]` Workspace loader reads `keyframe_defaults.ease_family` from `workspace.yaml` if present; absence yields the default.
- `[BEHAVIORAL]` `find(project, (2,0), "transform")` returns the index of the filter whose `kdenlive_id` equals `"transform"` if present.
- `[BEHAVIORAL]` `find(project, (2,0), "affine")` returns the index of the filter whose `mlt_service` equals `"affine"` when no `kdenlive_id` match.
- `[BEHAVIORAL]` `find` raises `LookupError` with message listing all effects on the clip when no match found.
- `[BEHAVIORAL]` `find` raises `ValueError` with all matching indices listed when the name is ambiguous (≥2 matches).
- `[BEHAVIORAL]` Loading a `workspace.yaml` with `keyframe_defaults: {ease_family: "expo"}` yields `workspace.keyframe_defaults.ease_family == "expo"`.
- `[BEHAVIORAL]` Loading a `workspace.yaml` without a `keyframe_defaults` section yields `workspace.keyframe_defaults.ease_family == "cubic"`.
- `[BEHAVIORAL]` Loading with an invalid `ease_family` value (e.g., `"invalid"`) raises a validation error.
- `[MECHANICAL]` `uv run pytest tests/unit/test_effect_find.py tests/unit/test_workspace_keyframe_defaults.py -v` passes.

**Dependencies.** none

---

### Sub-Spec 4: MCP Tool Surface + Integration
**Scope.** Register four new MCP tools in `server/tools.py` wired to the pipelines and patcher extensions from sub-specs 1-3. Each tool loads the project, invokes pipeline logic, writes via patcher, auto-snapshots per existing policy, and returns patched state.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended)
- `tests/integration/test_keyframe_mcp_tools.py` (new)
- `tests/integration/fixtures/keyframe_project.kdenlive` (new — minimal project with a transform filter on one clip)

**Acceptance Criteria.**
- `[STRUCTURAL]` `server/tools.py` registers four MCP tools via the existing MCP registration pattern: `effect_keyframe_set_scalar`, `effect_keyframe_set_rect`, `effect_keyframe_set_color`, `effect_find`.
- `[STRUCTURAL]` Each keyframe tool signature is `(workspace_path: str, project_file: str, track: int, clip: int, effect_index: int, property: str, keyframes: str, mode: str = "replace") -> dict` where `keyframes` is a JSON-encoded `list[{time_union, value, easing}]` and `mode` is validated to `{"replace","merge"}` in the body. Returns `{"status","data":{...,"snapshot_id":str}}` on success (matches existing `effect_add` param shape at `tools.py:3666`).
- `[STRUCTURAL]` `effect_find` signature is `(workspace_path: str, project_file: str, track: int, clip: int, name: str) -> dict` returning `{"status","data":{"effect_index":int}}`.
- `[INTEGRATION]` All four tools are importable as callables from `workshop_video_brain.edit_mcp.server.tools` after module import (decorator-based registration is a side effect of import).
- `[BEHAVIORAL]` Against `fixtures/keyframe_project.kdenlive`, calling `effect_keyframe_set_rect(workspace, track=2, clip=0, effect_index=0, property="rect", keyframes=[{frame:0, value:[0,0,1920,1080], easing:"linear"}, {seconds:2, value:[100,50,1920,1080,0.5], easing:"ease_in_out"}])` writes the expected keyframe string into the `<property name="rect">` of the transform filter; re-parsing the project yields the same keyframe list.
- `[BEHAVIORAL]` Calling a keyframe tool with `mode="merge"` against an existing keyframe string preserves non-overlapping frames and overwrites same-frame entries.
- `[BEHAVIORAL]` Calling `effect_find(workspace, track=2, clip=0, name="transform")` returns `0` for the fixture.
- `[BEHAVIORAL]` Calling a keyframe tool with an invalid `effect_index` returns `{"status":"error","message":<str>}` where the message includes `list_effects(...)` output for the clip (NOT a raised exception — wraps in `_err` envelope per existing tool convention).
- `[BEHAVIORAL]` Each MCP call produces a workspace snapshot per the existing auto-snapshot policy; `data.snapshot_id` in the return value is the snapshot directory name (format `{timestamp}-{slug}`), usable as input to `snapshot_restore`.
- `[INTEGRATION]` Workspace `keyframe_defaults.ease_family` flows through to output: setting it to `"expo"` on the workspace manifest, then calling `effect_keyframe_set_scalar` with `easing="ease_in"` produces a keyframe string containing operator `p` (expo_in), not `g` (cubic_in).
- `[BEHAVIORAL]` `effect_keyframe_set_color` emits MLT canonical `0xRRGGBBAA` hex-integer format: `value="#ff0000"` produces `0xff0000ff` (alpha defaulted to `ff`).
- `[BEHAVIORAL]` Pre-flight API fix: `SnapshotRecord` has a `snapshot_id: str` field populated by `workspace.snapshot.create` with the snapshot directory name. All existing callers of the (non-existent) `WorkspaceManager.create_snapshot` in `tools.py` (lines 3578, 3708, 3942, 3980) are updated to use `workspace.create_snapshot` directly.
- `[MECHANICAL]` `uv run pytest tests/integration/test_keyframe_mcp_tools.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.

**Dependencies.** sub-spec 1, sub-spec 2, sub-spec 3

## Edge Cases

- **Abstract noun "property name"** — Disambiguated: property names are the literal MLT `<property name="...">` attribute (e.g., `"rect"`, `"0"`, `"amount"`). Tool does not translate Kdenlive UI labels to property names; caller supplies the MLT name directly (catalog work in Spec 3 will later provide hints).
- **Abstract noun "value" for scalar** — Disambiguated: scalars are Python `float` or `int`; tool coerces to `float` internally, emits without a decimal point only when integral (matches MLT convention).
- **Color value format (locked)** — Input accepts `"#RRGGBB"`, `"#RRGGBBAA"`, or `int` in `0xRRGGBBAA` form. Output is ALWAYS MLT canonical `0xRRGGBBAA` hex-integer literal (8 hex digits, alpha in low byte). Missing alpha defaults to `ff` (opaque). See `docs/reference/mlt/keyframe-operators.md` §"Color values".
- **Empty keyframes list** — Tool raises `ValueError("keyframes list cannot be empty")`. A zero-keyframe animation is never what the caller wanted.
- **Single keyframe** — Permitted. Emits a single `"HH:MM:SS.mmm=value"` with the easing operator attached; MLT treats this as a static value.
- **Keyframes with duplicate frames in input list** — The later entry wins (within-call deduplication). No error; just log one warning line in the return.
- **Time conversion collision** — `frame=59` and `seconds=1.967` both round to `"00:00:01.967"` at 30fps. If two input keyframes collide post-normalization, error with both offending entries.
- **Property has a static non-keyframe value on merge** — Treat the static value as a single keyframe at frame 0 with linear easing, then merge.
- **Workspace config missing `keyframe_defaults` entirely** — Hardcoded fallback `cubic`; no error.
- **Workspace config has invalid `ease_family`** — Validation error at workspace load time, NOT at keyframe call time (fail fast).
- **MLT version guard** — If `smooth_natural`/`smooth_tight`/`$=`/`-=` is requested and workspace metadata pins MLT<7.22, raise with version requirement. Current target MLT 7.36 makes this a cold path; implement the check but do not block common-case code paths on it.
- **Ambiguous `effect_find`** — Two filters with the same `kdenlive_id` on one clip: raise with all matching indices. Caller uses `effect_index` directly instead.
- **`effect_find` by `mlt_service` when `kdenlive_id` is present on some filters** — Search `kdenlive_id` first; only fall back to `mlt_service` if no `kdenlive_id` match found. Document in docstring.

## Out of Scope

- Per-effect wrapper tools (`effect_transform`, `effect_blur`, etc.) — Spec 7
- Effect catalog expansion and `effect_list_common` replacement — Spec 3
- Rotoscoping, masking, chroma key tools — Spec 5
- Composite blend mode refactor — Spec 6
- Effect stack copy/paste/reorder — Spec 2
- Effect stack preset save/apply/promote — Spec 4
- Changes to existing `effect_add`, `composite_pip`, `composite_wipe`, `transitions_*` tools
- Changes to serializer behavior for non-keyframe properties
- Kdenlive UI-label → MLT property-name translation (lives in catalog spec)
- Runtime introspection of frei0r binaries for param metadata (catalog spec)
- GUI preview of keyframe animation
- Bezier-handle editing of keyframe curves (not a Kdenlive feature anyway)

## Constraints

### Musts
- All acceptance criteria above.
- Python 3.12+ compatibility (per `pyproject.toml`).
- Pydantic for new data models (match existing pattern).
- No new runtime dependencies beyond what's in `pyproject.toml`.

### Must-Nots
- Must NOT modify existing `effect_add`, `effect_list_common`, `composite_pip`, `composite_wipe`, or `transitions_*` tool signatures.
- Must NOT change `.kdenlive` serializer output for non-keyframe properties.
- Must NOT introduce a caching layer for fps or workspace config (correctness > perf).
- Must NOT overwrite files in `media/raw/` or `projects/source/` (project safety rule).
- Must NOT bypass the existing auto-snapshot policy.

### Preferences
- Prefer additive changes to `patcher.py`; keep existing methods untouched.
- Prefer small, focused test files (one per module).
- Prefer explicit typed exceptions (`ValueError`, `LookupError`, `IndexError`) over generic `Exception`.
- Prefer exhaustive Literal types over string validation where the value set is fixed (e.g., `ease_family`, `mode`, `kind`).

### Escalation Triggers
- Discovery that the existing patcher does not already expose a way to locate a filter within a clip's effect stack → stop and report before inventing a new access pattern.
- Discovery that `workspace.yaml` loading uses a pattern incompatible with adding nested config (stop and ask).
- Any test fixture requirement that cannot be met by a hand-written minimal `.kdenlive` file (stop and ask about alternatives).
- If adding the four new MCP tools would push the server past a registration limit or collision (stop and ask).

## Verification

End-to-end confirmation the feature works:

1. `uv run pytest tests/ -v` passes with no regressions and all new tests green.
2. Start the MCP server: `uv run workshop-video-brain serve` (or equivalent); use an MCP client to confirm all four new tools are listed.
3. Against a real `.kdenlive` fixture, call `effect_keyframe_set_rect` with a two-keyframe transform animation.
4. Open the resulting `.kdenlive` in Kdenlive 25.x; scrub the timeline; confirm the transform animates from start pose to end pose with visible cubic-in-out easing.
5. Call the same tool with `mode="merge"` adding a third keyframe; re-open in Kdenlive; confirm all three keyframes are present and animate correctly.
6. Call `effect_find` with a filter name that exists; confirm the returned index matches manual inspection.
