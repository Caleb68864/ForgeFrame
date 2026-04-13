---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-keyframe-tool.md"
sub_spec_number: 2
title: "Keyframes Pipeline Module"
date: 2026-04-13
dependencies: [none]
---

# Sub-Spec 2: Keyframes Pipeline Module

Refined from spec.md — ForgeFrame keyframe tool.

## Scope

Create a new pure-logic module
`workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/keyframes.py`
that owns:

1. Time normalization across `{frame|seconds|timestamp}` union → MLT
   `HH:MM:SS.mmm` string.
2. Easing resolution (abstract names + family aliases + raw MLT operator chars)
   → single-char MLT operator prefix (empty string for linear).
3. `build_keyframe_string(kind, keyframes, fps, ease_family_default)` → MLT
   keyframe animation string.
4. `parse_keyframe_string(kind, s)` → `list[Keyframe]` (round-trip inverse).
5. `merge_keyframes(existing, new)` → deduped, frame-sorted list (new wins on
   same-frame collision; static strings treated as single frame-0 keyframe).

No XML I/O. No MCP registration. No filesystem access. No project-model
imports beyond the lightweight `Keyframe` dataclass/TypedDict this module
defines. This is the only unit in the feature that can be exhaustively unit
tested without fixtures.

**Authoritative MLT operator table** is vendored at
`docs/reference/mlt/keyframe-operators.md`. The `_OPERATORS` dict in this
module MUST be populated from that reference verbatim — do not transcribe
from external sources. On any unknown-operator path, the raised `ValueError`
message MUST point at `docs/reference/mlt/keyframe-operators.md` so the
reader has a single source of truth.

**Color format (locked):** input accepts `"#RRGGBB"`, `"#RRGGBBAA"`, or `int`
in `0xRRGGBBAA` form; output is ALWAYS `0xRRGGBBAA` hex-integer literal. See
the reference file §"Color values". Example: `value="#ff0000"` with
`kind="color"` emits `0xff0000ff` in the keyframe string.

## Interface Contracts

### Provides
- `Keyframe` — dataclass (prefer `@dataclass(frozen=True, slots=True)` over TypedDict for type-narrowing in builders) with fields `frame: int`, `value: Any`, `easing: str`.
- `normalize_time(input: dict, fps: float) -> str` — accepts `{"frame": int}`, `{"seconds": float}`, or `{"timestamp": "HH:MM:SS.mmm"}`.
- `resolve_easing(name_or_operator: str, ease_family_default: str = "cubic") -> str`.
- `build_keyframe_string(kind, keyframes, fps, ease_family_default) -> str` where `kind: Literal["scalar","rect","color"]`.
- `parse_keyframe_string(kind, s) -> list[Keyframe]`.
- `merge_keyframes(existing: list[Keyframe] | str, new: list[Keyframe]) -> list[Keyframe]`. Accept a raw string for `existing` to satisfy the "static non-keyframe value" edge case (master spec Edge Cases).
- Module-level `VALID_EASING_NAMES: frozenset[str]` and `VALID_EASE_FAMILIES: tuple[str, ...]` for Sub-Spec 3's workspace validation to import.

### Requires
None — no dependencies.

### Shared State
None — pure functions.

## Implementation Steps

### Step 1: Write failing test file
- **File:** `tests/unit/test_keyframes_pipeline.py`
- **Tests (one per bullet in Acceptance Criteria):**
  - `test_normalize_time_frame`
  - `test_normalize_time_seconds`
  - `test_normalize_time_timestamp_passthrough`
  - `test_normalize_time_missing_keys_raises`
  - `test_normalize_time_negative_frame_raises`
  - `test_normalize_time_malformed_timestamp_raises`
  - `test_resolve_easing_linear_empty`
  - `test_resolve_easing_smooth_tilde`
  - `test_resolve_easing_hold_pipe`
  - `test_resolve_easing_ease_in_out_expo`
  - `test_resolve_easing_ease_in_with_family_default`
  - `test_resolve_easing_raw_operator_passthrough`
  - `test_resolve_easing_unknown_name_lists_valid_set`
  - `test_resolve_easing_unknown_raw_operator`
  - `test_build_keyframe_string_rect_two_frames`
  - `test_build_keyframe_string_rect_four_tuple_adds_default_opacity`
  - `test_build_keyframe_string_scalar`
  - `test_build_keyframe_string_color`
  - `test_parse_keyframe_string_roundtrip_scalar`
  - `test_parse_keyframe_string_roundtrip_rect`
  - `test_parse_keyframe_string_roundtrip_color`
  - `test_merge_keyframes_overlap_overwrites`
  - `test_merge_keyframes_static_string_treated_as_frame_zero`
  - `test_merge_keyframes_duplicate_frames_in_new_last_wins`
- **Run:** `uv run pytest tests/unit/test_keyframes_pipeline.py -v`
- **Expected:** all fail (module does not yet exist).

### Step 2: Create module skeleton with `Keyframe` and constants
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/keyframes.py`
- **Action:** create
- **Pattern:** follow existing `pipelines/effect_apply.py` header style (`"""Docstring."""`, `from __future__ import annotations`, module `logger`, no runtime dependency beyond stdlib).
- **Changes:**
  - Add `Keyframe` dataclass (`frozen=True, slots=True`).
  - Declare `_OPERATORS: dict[str, str]` with 40+ MLT types. Keys = abstract names AND raw operator chars; values = single-char operator. Include at minimum: `linear→""`, `smooth→"~"`, `hold→"|"`, `smooth_natural→"$"`, `smooth_tight→"-"`, and the family set `sine/quad/cubic/quart/quint/expo/circ/back/elastic/bounce` each crossed with `ease_in_<fam>`, `ease_out_<fam>`, `ease_in_out_<fam>`, and the terse alias `<fam>_in`/`<fam>_out`/`<fam>_in_out`. (Transcribe the `keyframe_type_map[]` from MLT source — the master spec's example `ease_in_out_expo→"r"` must be present and correct.)
  - Declare `VALID_EASING_NAMES = frozenset(n for n in _OPERATORS if not _is_single_operator_char(n))`.
  - Declare `VALID_EASE_FAMILIES = ("sine","quad","cubic","quart","quint","expo","circ","back","elastic","bounce")`.
  - Expose `resolve_ease_family_alias(name: str, family: str) -> str` as a helper (e.g., `"ease_in"` + family `"expo"` → `"ease_in_expo"`), used inside `resolve_easing`.

### Step 3: Implement `normalize_time`
- Validate exactly one key present from `{"frame","seconds","timestamp"}`.
- Frame path: require `int`, `>= 0`, convert `seconds = frame / fps`, then format.
- Seconds path: require non-negative `float|int`.
- Timestamp path: validate regex `^\d{2}:\d{2}:\d{2}\.\d{3}$`; return as-is.
- Output format: `f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"` — MLT canonical. Rounding: nearest millisecond (`round(seconds * 1000)`).
- On error, raise `ValueError` with the offending input dict included in the message (per acceptance criterion wording "offending key in the message").

### Step 4: Implement `resolve_easing`
- If input in `_OPERATORS` keys → return mapped char.
- If length 1 and present as value anywhere in `_OPERATORS` → passthrough raw operator.
- If input starts with `ease_in`/`ease_out`/`ease_in_out` and ends with bare `in|out|in_out` (no family) → compose `f"ease_{direction}_{ease_family_default}"` and look up.
- Else raise `ValueError` with `sorted(VALID_EASING_NAMES)` truncated to first 20 and pointer to the MLT operator table in the docstring.

### Step 5: Implement `build_keyframe_string`
- Normalize value per `kind`:
  - `scalar`: coerce to `float`; emit `str(int(v))` if `v.is_integer()`, else `repr(v)` trimmed to max 6 decimals.
  - `rect`: list of 4 or 5 numbers → always emit 5 space-separated (opacity defaults to `1`).
  - `color`: hex `#rrggbb[aa]` OR `"#rrggbbaa"`, OR tuple `(r,g,b,a)` 0-1 or 0-255 — pick one canonical form and document. Recommend: accept `"#rrggbb"`/`"#rrggbbaa"` strings, emit verbatim.
- For each keyframe: `time_string = normalize_time({"frame": kf.frame}, fps)`; `op = resolve_easing(kf.easing, ease_family_default)`; emit `f"{time_string}{op}={value_string}"`.
- Join with `;`.
- Raise `ValueError("keyframes list cannot be empty")` if empty.
- Warn + dedupe when multiple input keyframes collide post-normalization; raise on collision with DIFFERENT values.

### Step 6: Implement `parse_keyframe_string`
- Split on `;`.
- For each segment: regex match time, optional operator char, `=`, value.
- Reverse-lookup operator char → easing name (prefer bare canonical name like `"smooth"` over `"ease_in_out_cubic"` when ambiguous — pick the shortest matching name for deterministic round-trip).
- Parse value per `kind` (inverse of Step 5).
- Return `list[Keyframe]`. Empty / whitespace-only → `[]`.

### Step 7: Implement `merge_keyframes`
- If `existing` is `str`: if no `;` and no `=` present, treat as a single linear keyframe at frame 0 with parsed value (use caller's `kind` — but since this helper is kind-agnostic, accept already-parsed `list[Keyframe]` from caller OR defer parsing. Simpler: require caller to parse first; the string-handling branch applies a literal single `Keyframe(frame=0, value=existing, easing="linear")`).
- Build dict `{kf.frame: kf for kf in existing}` then overlay `new` (later wins).
- Return `sorted(result.values(), key=lambda k: k.frame)`.

### Step 8: Run tests green
- **Run:** `uv run pytest tests/unit/test_keyframes_pipeline.py -v`
- **Expected:** PASS.

### Step 9: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/keyframes.py tests/unit/test_keyframes_pipeline.py`
- **Message:** `feat: keyframes pipeline module`

## Acceptance Criteria

- `[STRUCTURAL]` Module exports `normalize_time`, `resolve_easing`, `build_keyframe_string`, `parse_keyframe_string`, `merge_keyframes`, and `Keyframe`.
- `[BEHAVIORAL]` `normalize_time({"frame": 60}, 30.0) == "00:00:02.000"`.
- `[BEHAVIORAL]` `normalize_time({"seconds": 2.0}, 30.0) == "00:00:02.000"`.
- `[BEHAVIORAL]` `normalize_time({"timestamp": "00:00:02.000"}, 30.0) == "00:00:02.000"`.
- `[BEHAVIORAL]` `resolve_easing("linear") == ""`; `resolve_easing("smooth") == "~"`; `resolve_easing("hold") == "|"`; `resolve_easing("ease_in_out_expo") == "r"`; `resolve_easing("ease_in", ease_family_default="expo") == "p"`; `resolve_easing("$=") == "$"` (raw-operator passthrough strips trailing `=`).
- `[BEHAVIORAL]` `build_keyframe_string("rect", [...], 30.0, "cubic")` with the two keyframes in master-spec criterion returns `"00:00:00.000=0 0 1920 1080 1;00:00:02.000i=100 50 1920 1080 0.5"`.
- `[BEHAVIORAL]` 4-tuple `[x,y,w,h]` → `"x y w h 1"`.
- `[BEHAVIORAL]` Parse round-trips `scalar`, `rect`, `color`.
- `[BEHAVIORAL]` `merge_keyframes` — overlapping frame overwrites; result sorted.
- `[BEHAVIORAL]` `merge_keyframes` — static non-keyframe string becomes single frame-0 linear keyframe.
- `[BEHAVIORAL]` Invalid time input raises `ValueError` naming offending key.
- `[BEHAVIORAL]` Unknown easing name raises `ValueError` listing valid set.
- `[BEHAVIORAL]` Unknown raw operator raises `ValueError` referencing MLT table.
- `[MECHANICAL]` `uv run pytest tests/unit/test_keyframes_pipeline.py -v` passes.

## Completeness Checklist

### `Keyframe` dataclass fields

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `frame` | `int` | required | `build_keyframe_string`, `merge_keyframes` (dedupe key) |
| `value` | `Any` (scalar `float`, list `[x,y,w,h,opacity]`, or color `str`) | required | `build_keyframe_string` per-kind serializer |
| `easing` | `str` (abstract name or raw operator) | required | `resolve_easing` |

### `_OPERATORS` table completeness

Every row of MLT's `keyframe_type_map[]` MUST be present. At minimum these specific keys MUST exist (from master spec criteria):

- `"linear"` → `""`
- `"smooth"` → `"~"`
- `"hold"` → `"|"`
- `"smooth_natural"` → `"$"`
- `"smooth_tight"` → `"-"`
- `"ease_in_out_expo"` → `"r"`
- `"ease_in_expo"` → `"p"`
- Raw operator passthroughs: `"="`, `"~="`, `"|="`, `"$="`, `"-="`, `"a="` through `"D="`.
- All 10 families × 3 directions × 2 naming styles (40+ rows).

### Numeric limits

- Millisecond rounding: nearest (banker's rounding not required).
- Max keyframes per call: unbounded (practical limit enforced by caller).
- Negative frame: rejected with `ValueError`.

## Verification Commands

- **Build:** not configured.
- **Tests:** `uv run pytest tests/unit/test_keyframes_pipeline.py -v`
- **Acceptance:** every criterion has a matching test name in Step 1 above; passing those tests is the acceptance signal.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py` — module layout, docstring style, error types (`ValueError` for bad input, `IndexError` for range errors).
- `workshop-video-brain/src/workshop_video_brain/core/models/transitions.py` — use `Literal` types for fixed-value parameters (per master spec "Preferences").
- Design doc: `docs/plans/2026-04-13-keyframe-tool-design.md` — for examples of expected output strings.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/keyframes.py` | Create | Pure-logic keyframe pipeline module. |
| `tests/unit/test_keyframes_pipeline.py` | Create | Comprehensive unit tests. |
