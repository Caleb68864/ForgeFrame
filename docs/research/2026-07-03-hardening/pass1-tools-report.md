# Hardening Pass 1 — server/tools audit report

Scope: `workshop_video_brain/edit_mcp/server/tools/` (16 modules, 117 registered
`@mcp.tool()` tools) + new contract module `server/errors.py`.

Contract: `server/errors.py` (see `error-contract.md`). Backward compatible with
the live `_err` shape `{"status": "error", "message": ...}` (the pre-existing key
is **`message`**, not `error` as the brief assumed — verified in
`tools_helpers.py` without editing it).

## What changed globally

- **`@tool_guard` applied to all 117 tools** (outer backstop): any exception
  that escapes a tool body is logged with full traceback to the server log and
  returned as a structured `operation_failed` error carrying only a one-line
  `cause` — never a traceback in the payload. Applied under `@mcp.tool()`;
  `functools.wraps` preserves the FastMCP schema/signature.
- **306+ explicit error paths enriched** via safe literal replacement, message
  text preserved verbatim (so all substring/exact-dict test assertions still
  pass), adding `error_type` + `suggestion` + echoed input:

  | pattern (occurrences) | now returns |
  |---|---|
  | `_err(str(exc))` / `_err(str(e))` (171) | `from_exception(exc)` → classifies to corrupt_project / missing_file / missing_dependency / invalid_input / operation_failed |
  | `workspace_path must be a non-empty string` (42) | `invalid_input(...)` |
  | `Workspace path does not exist` (31) | `missing_file(...)` |
  | `Workspace path is not a directory` (30) | `invalid_input(...)` |
  | `Project file not found` (22) | `err(..., missing_file, suggestion=create working copy)` |
  | `No .kdenlive files found ...` (6) | `err(..., missing_file, suggestion=...)` |
  | `File not found: {source/file_path}` (7) | `err(..., missing_file, ...)` |
  | `Invalid params/points JSON` (4) | `err(..., bad_json_param, example)` |

- **`ProjectParseError` → `corrupt_project`**: `from_exception` imports the
  adapter's `ProjectParseError` (read-only) and maps it to `error_type=
  corrupt_project` with a snapshot-restore suggestion, replacing the old generic
  `_err(str(exc))` 500. Every tool that parses a project routes through either an
  explicit `from_exception` catch or the `@tool_guard` backstop.

## Per-module audit table

| module | tools | failure modes covered | changes |
|---|---|---|---|
| workspace_media | 7 | missing/empty workspace, missing media, backstop | guard×7, ws + file paths enriched |
| transcript_markers | 7 | missing/empty workspace, no markers/transcripts dir, backstop | guard×7, ws paths enriched |
| timeline_project | 12 | missing/empty workspace, no working copy, snapshot restore, backstop | guard×12, ws + no-kdenlive enriched |
| transitions | 3 | missing/empty workspace, <2 clips, backstop | guard×3, ws paths enriched |
| clips_nle | 14 | missing/empty workspace, missing media, invalid clip/track index, empty query, backstop | guard×14, ws + str(exc) enriched |
| render | 7 | missing file_path, missing/empty workspace, backstop | guard×7, file + ws enriched |
| audio | 6 | missing source file, missing/empty workspace, no audio in media/raw, backstop | guard×6, File-not-found + ws enriched |
| broll | 5 | missing/empty workspace, unconfigured vault, backstop | guard×5, ws + str(exc) enriched |
| assembly_titles | 6 | missing/empty workspace, backstop | guard×6, ws + str(exc) enriched |
| social_publish | 13 | missing/empty workspace, backstop | guard×13, str(exc) enriched |
| keyframes | 4 | missing project file, invalid index, bad keyframe JSON, backstop | guard×4, project-not-found + str(exc) enriched |
| compositing_masking | 9 | missing project file, bad params/points JSON, invalid mask type/shape, backstop | guard×9, prelude + JSON + str(exc) enriched |
| effects_catalog | 10 | missing project file, bad params JSON, effect not found, backstop | guard×10, project-not-found + JSON + str(exc) enriched |
| effects_bundles | 8 | missing project file, invalid fade args, invalid index, backstop | guard×8, project-not-found + str(exc) enriched |
| effects_color | 6 | missing project/file, bad points JSON, out-of-range params, backstop | guard×6, File-not-found + project + JSON + str(exc) enriched |
| **total** | **117** | | **117 guards + 306+ enriched paths** |

## Tests

New: `tests/integration/test_hardening_tools.py` — 47 tests:
- contract-builder unit coverage (`err`, all constructors, `from_exception`,
  `tool_guard` name/signature/success preservation, one-line cause);
- per-module integration cases (empty workspace, nonexistent workspace,
  nonexistent file) asserting `status=error`, `error_type ∈ VALID_ERROR_TYPES`,
  non-generic `suggestion` (len>15, not a filler word), and **no `Traceback`
  text in any payload field**.

Full suite: **4 failed, 3955 passed, 2 skipped** (from a fluctuating baseline of
35–49 failed / ~3843 passed while the serializer agent landed changes). All 4
remaining failures are pre-existing and outside this package — verified by
reverting `tools/` and re-running: `test_multicam_render` (2),
`test_transition_renders` (1), `test_effect_presets::...on_transform` (1), all
tied to the serializer's `transform`→`qtblend` change and external melt/ffmpeg
renders. **Zero net-new failures introduced by this package.**

## Deferred

- **166 tool-specific validation `_err(...)` calls** (enum checks, numeric range
  checks like `tolerance_far >= tolerance_near`, `Snapshot failed: {exc}`, etc.)
  still return the legacy `{status, message}` shape without `error_type`/
  `suggestion`. They remain **graceful** (they sit inside the `@tool_guard`
  envelope and return `status=error`) but are not yet maximally *loud*. Lower
  frequency + tool-specific wording → deferred to pass 2/3.
- **kdenlive-adapter follow-up**: `corrupt_project` classification depends on the
  adapter's `ProjectParseError` (owned by another agent; imported read-only). If
  the adapter changes that exception's identity/shape, revisit `from_exception`.
- `tools_helpers.py` `_err`/`_ok` (owned by another agent) left untouched;
  `err()` is purely additive and backward compatible.
