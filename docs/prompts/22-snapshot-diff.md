# Prompt 22: `snapshot_diff`, an LLM-readable diff between two project versions

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here.

**Summary.** Every edit writes a new working copy (`projects/working_copies/
<slug>_v<N>.kdenlive`) and most edits also leave a snapshot
(`projects/snapshots/<id>/`). `snapshot_list` and `snapshot_restore` exist,
but nothing tells the user or the model *what changed* between two versions.
Add a read-only tool `snapshot_diff` that parses both versions with the
existing parser and reports, in plain sentences plus structured JSON, which
tracks, clips, effects, transitions, guides and bin clips were added, removed
or changed. It compares parsed models, never raw XML text.

## What exists (read first)

- `workshop-video-brain/src/workshop_video_brain/workspace/snapshot.py`:
  `create`, `restore`, `list_snapshots`. A snapshot is a directory
  `projects/snapshots/<snapshot_id>/` holding a copy of the project file
  (same file name as the original) and `metadata.yaml` (`SnapshotRecord`,
  with `project_file_path`). `restore` (~87) shows the safe way to resolve and
  validate a snapshot id (no path traversal, stays inside the snapshots dir).
- `edit_mcp/server/tools/timeline_project.py`: `snapshot_list` (~325),
  `snapshot_restore` (~368). Put the new tool in a **new module**, not here.
- `edit_mcp/server/tools_helpers/_projects.py`: `latest_project(files)` and
  `_project_version_key` (`_v<N>` ordering).
- Parser `edit_mcp/adapters/kdenlive/parser.py::parse_project` ->
  `KdenliveProject` (`core/models/kdenlive.py`): `profile`, `producers`
  (`id`, `resource`, `properties`), `tracks` (`id`, `track_type`, `name`),
  `playlists` (`id`, `entries` of `PlaylistEntry(producer_id, in_point,
  out_point)`; empty `producer_id` = blank of `out_point + 1` frames),
  `guides`, `subtitles`, `opaque_elements`. Clip effects, track filters,
  transitions and mute/hide directives are OpaqueElements (see the long
  comment at the end of `KdenliveProject`):
  - clip effect: `tag="filter"` with `track` + `clip_index` attributes;
  - track filter: `tag="filter"` with `track` and no `clip_index`;
  - transition/composition: `tag="transition"` with `<property>`s
    `mlt_service`, `kdenlive_id`, `a_track`, `b_track`, `in`, `out` (ints, or
    `HH:MM:SS.mmm` in files Kdenlive saved);
  - mute/visibility: `tag="kdenlive:hide"`.
- `edit_mcp/adapters/kdenlive/effect_stack.list_effects(project, (track, clip))`
  gives `{index, mlt_service, kdenlive_id, properties}` per clip effect.
- `edit_mcp/pipelines/clip_place.py`: `entry_length`, `playlist_length`.
- `edit_mcp/pipelines/_common.py`: `seconds_to_mmss`.

The harvested project only had a stub `compare_snapshots` tool with no
implementation, so there is nothing to borrow; this design is ours.

## Steps

1. **Pipeline** `edit_mcp/pipelines/project_diff.py` (pure, takes two
   `KdenliveProject`s):
   - `track_label(project, playlist_index) -> str`: `V<n>`/`A<n>` counting
     within the track type in playlist order, plus the track name if set,
     e.g. `"V1 (Video)"`.
   - `clip_records(project, playlist_index) -> list[dict]`: one per non-blank
     entry: `clip_index`, `start`, `end` (frames), `producer_id`, `in`, `out`,
     `name` (basename of the producer `resource`, else the producer id).
   - `diff_projects(a, b, max_changes=200) -> dict` producing a list of change
     dicts `{category, action, track, ..., text}` where `text` is one plain
     English sentence with times as `mm:ss` (and frames in brackets). Rules:
     - **profile**: width/height/fps changed.
     - **tracks**: match by `Track.id`; added, removed, renamed, type changed;
       mute/hide directive changed.
     - **clips** per matched track: align `clip_records` with
       `difflib.SequenceMatcher` on the key `(producer_id, in, out)`.
       `equal` pairs whose `start` differs are **moved**. In a `replace`
       block, pair records one by one: same producer and overlapping source
       range -> **trimmed** (report in/out deltas); same start and length but
       different producer -> **replaced**; otherwise removed + added. `delete`
       -> removed, `insert` -> added. Keep the old->new clip index map for
       the effect step.
     - **clip effects**, for every clip pair from the map: align effect lists
       on `kdenlive_id or mlt_service`; added / removed / reordered; for
       matched effects report changed properties (old -> new; for long
       keyframe strings say "keyframes changed (N -> M keyframes)" instead
       of dumping them) and enabled/disabled (`disable` property). Ignore
       bookkeeping keys (`kdenlive:*`, `track`, `clip_index`).
     - **track filters**: same as clip effects, per track.
     - **transitions**: key `(kdenlive_id or mlt_service, a_track, b_track)`;
       normalise `in`/`out` to frames (ints or timecodes, using the project
       fps); added, removed, moved/resized.
     - **guides**: by `(position, label)`; added, removed, relabelled at the
       same position.
     - **bin**: producers added/removed, matched by `resource` (fall back to
       id for generated producers such as `color`).
     - **duration**: overall timeline length (max `playlist_length`) changed.
   - Return `{"identical": bool, "summary": {category: {action: count}},
     "changes": [...first max_changes...], "truncated": bool, "text": "..."}`
     where `text` is the sentences joined with newlines, grouped by
     category, starting with a one-line summary such as
     `"3 clips changed on V1, 1 effect added, duration 01:12 -> 01:05."`.
2. **Version resolution** helper in the same module or a small
   `edit_mcp/server/tools_helpers/_versions.py` (shell-level, does I/O):
   `resolve_version(ws_path, ref) -> Path` where `ref` is one of:
   `"latest"` (latest working copy), `"previous"` (the working copy just
   before latest by `_project_version_key`), a snapshot id (directory under
   `projects/snapshots/`; use the file named after `project_file_path` in its
   metadata, else the only `*.kdenlive` in it), or a `.kdenlive` path
   (absolute or workspace-relative) that resolves **inside the workspace**.
   Validate snapshot ids exactly as `snapshot.restore` does.
3. **Tool** new module `edit_mcp/server/bundles/snapshot_diff.py`:
   `snapshot_diff(workspace_path, a="previous", b="latest", max_changes=200)`
   with `@mcp.tool()` then `@tool_guard`. Read-only: no snapshot, no write.
   Errors: unknown ref -> `not_found` (hint: run `snapshot_list`), missing
   file -> `missing_file`, `ProjectParseError` -> `corrupt_project`,
   `max_changes < 1` -> `invalid_input`. Return `_ok` with the diff plus the
   two resolved paths.

## Tests

1. **Unit** `tests/unit/test_project_diff.py`, building projects with
   `tests/_testkit.py` (`sequence_project`, `two_track_project`) and mutating
   copies with `patch_project` intents (`TrimClip`, `RemoveClip`,
   `MoveClip`, `AddEffect`, `AddTransition`, `AddGuide`, `CreateTrack`) or
   direct model edits:
   - identical projects -> `identical: true`, no changes;
   - one test per category and action above, asserting the change dict and
     that its `text` names the track label and the clip name;
   - inserting a clip before others reports one **added** clip, not N
     changed ones (the alignment works), and effects on the shifted clips
     are not reported as changed;
   - disabling an effect (`disable=1`) reports "disabled";
   - timecode vs int transition `in`/`out` compare equal;
   - `max_changes` truncation sets `truncated`.
2. **Tool** `tests/unit/test_snapshot_diff_tool.py`: workspace via the
   `_make_workspace` pattern (`tests/unit/test_nle_operations.py` ~73) with
   v1 and v2 working copies and one snapshot directory; resolve `latest`,
   `previous`, a snapshot id and a relative path; traversal refs such as
   `../x` and `..` are rejected; registered via `assert_registered`.
3. No render proof is needed: the tool is read-only and does not touch the
   timeline. Say so in the report.

## Acceptance criteria

- `snapshot_diff` explains a trim, an insert, an effect change and a
  transition in plain sentences an LLM can repeat to the user.
- Read-only: no file is written anywhere (assert the workspace file list is
  unchanged in the tool test).
- Full suite green; ruff clean.

## Do NOT

- Do not diff XML text or use `ET` in the shell; the pipeline works on
  parsed models (use `ET.fromstring` only inside the pipeline to read
  OpaqueElement properties, as `effect_stack` does).
- Do not change `snapshot_list`, `snapshot_restore` or the snapshot format.
- Do not resolve refs outside the workspace or the snapshots directory.

## When done

1. Mention `snapshot_diff` in `workshop-video-brain/skills/ff-rough-cut-review/SKILL.md`
   (review what changed between versions) and in the skill that documents
   `snapshot_restore` (grep for it).
2. Regenerate `docs/capabilities.md`; mark Phase 4 item 7 done in
   `docs/plans/2026-10-13-media-mcp-expansion.md`.
3. Report as in `00-README.md`, with one example `text` output from the tool
   test.
