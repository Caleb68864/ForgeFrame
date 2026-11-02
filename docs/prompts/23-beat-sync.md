# Prompt 23: beat-synced cuts, zooms and flashes from `music_beat_grid`

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here.

**Summary.** `music_beat_grid` already detects tempo and a beat grid for a
music file (pure NumPy) and writes `reports/beat_grid.json`;
`markers_from_beats` turns bars into workspace markers. Nothing yet *edits*
to the beat. Add three tools on top of the existing grid: `beat_cut`
(re-time consecutive clips so cuts land on selected beats), `beat_zoom` (a
zoom punch on selected beats) and `beat_flash` (a short brightness flash on
selected beats). Beats are chosen with musical variety, not on every beat.
Assumes prompts 20 (linked-audio helper, `_ensure_producer_length`) and 21
(`pipelines/camera_moves.py`, `zoom_punch`) are merged; if either is missing,
stop and report.

## What exists (read first)

- `edit_mcp/server/bundles/beat_grid.py`: `music_beat_grid(workspace_path,
  source, sensitivity)` writes `reports/beat_grid.json` = the dict from
  `pipelines/beat_grid.analyze_beats`: `bpm_estimate`, `period_seconds`,
  `beats` (seconds, music-file time), `onsets`, `duration_seconds`, plus
  `source` (absolute path of the analysed file). `markers_from_beats`
  (every N-th beat = a bar; there is **no downbeat detection**).
- Timeline helpers: `edit_mcp/pipelines/clip_place.py` (`entry_length`,
  `clip_start_frame`, `playlist_length`), `pipelines/_common.seconds_to_frames`.
- Clip edits: `TrimClip` intent (`clip_ref="<playlist_id>:<index>"`), the
  linked-audio helper and `_ensure_producer_length` from prompt 20 in
  `adapters/kdenlive/patcher_intents.py`.
- Effects: `patcher.insert_effect_xml`, `patcher.list_effects`, the
  `_build_filter_xml(...)` call in `bundles/shake_shadow.py` (~151);
  `pipelines/keyframes.build_keyframe_string`; prompt 21's
  `pipelines/camera_moves.zoom_punch`; the catalog entry `brightness`
  (`mlt_service=brightness`, animated param `level`, 1 = unchanged).
- Shell pattern for latest-working-copy tools: `clip_trim` in
  `edit_mcp/server/tools/clips_nle.py` (~401): `_load_latest_project`,
  `_resolve_playlist(project, track)` (`track` = video-track index),
  `patch_project(..., with_report=True)`, `_save_patched`.

### Ideas harvested from another project (reimplemented, not copied)

- **Musical variety**: cutting on every beat looks robotic. An `intensity`
  picks the base stride: `subtle` = every 4th beat, `medium` = every 2nd,
  `aggressive` = every beat. Beats on a bar start (they had a downbeat
  detector; we approximate bars as every 4th beat from a `phase` offset) are
  always included, even at `subtle`.
- **Cut on beat**: keep clip order; the first clip keeps its start; each
  following boundary moves to the next selected beat. If there are more clips
  than selected beats, fall back to the full beat list; if that runs out,
  leave the remaining clips as they are. Never drop a clip.
- **Zoom on beat**: a zoom punch at each selected beat.
- **Flash on beat**: they faked it with an opacity spike; we use a real
  brightness spike instead (an opacity dip over the black background reads
  as a dark flicker, not a flash).

## Steps

1. **Pure pipeline** `edit_mcp/pipelines/beat_sync.py`:
   - `select_beats(beats, intensity="medium", every_n=0, phase=0,
     bar_every=4, start_s=None, end_s=None, min_gap_s=0.0) -> list[float]`:
     `every_n > 0` overrides the intensity stride; bar beats (`(i - phase) %
     bar_every == 0`) are always kept; drop beats closer than `min_gap_s` to
     the previous kept one; unknown intensity -> `ValueError` listing valid
     ones.
   - `beats_to_timeline_frames(beats, fps, music_start_frame, music_in_frame,
     music_out_frame) -> list[int]`: `music_start_frame + round(beat * fps)
     - music_in_frame`, keeping only beats inside the music entry's used
     source range. With an explicit offset instead of a music entry, use
     `round((offset + beat) * fps)`.
   - `plan_beat_cut(clip_records, beat_frames, min_clip_frames=6) -> list[dict]`
     where each record is `{start, length, in, source_frames}`: returns new
     lengths per clip following the "cut on beat" rule above; a clip that
     cannot reach its beat (not enough source) uses what it has and is
     flagged `off_beat: true`; boundaries closer than `min_clip_frames` skip
     to the next beat.
   - `clip_hits(track_records, beat_frames) -> dict[int, list[int]]`: map
     each beat frame to `(clip_index, entry-local frame)` of the video clip
     that covers it (beats over blanks are ignored and counted).
   - `flash_keyframes(local_frames, clip_length, strength=1.0,
     attack_frames=1, decay_frames=3) -> list[Keyframe]` for `level`:
     baseline 1.0, peak `1.0 + strength`; overlapping pulses are merged
     (the next pulse's attack truncates the previous decay); keyframes stay
     inside `[0, clip_length - 1]`.
   - For zooms, add `zoom_punch_train(width, height, at_frames, fps, ...)` to
     `pipelines/camera_moves.py` (prompt 21's module) that merges several
     punches into one keyframe string with the same overlap rule.
2. **Music position resolution** (shell helper, does I/O): read the beat file
   (default `reports/beat_grid.json`; workspace-relative or absolute). Find
   the music entry: `music_track >= 0` + `music_clip_index`, or (default
   `music_track=-1`) the first audio-track entry whose producer `resource`
   equals the beat file's `source`. `music_offset_seconds >= 0` overrides
   both. No music found and no offset -> `invalid_input` explaining the
   three options.
3. **Tools** in a new module `edit_mcp/server/bundles/beat_sync.py`, each
   `@mcp.tool()` then `@tool_guard`, operating on the latest working copy:
   - `beat_cut(workspace_path, track=0, first_clip_index=0,
     last_clip_index=-1, beat_file="", intensity="medium", every_n=0,
     phase=0, music_track=-1, music_clip_index=0, music_offset_seconds=-1.0,
     min_clip_seconds=0.25)`: emits `TrimClip` (out-point only) for each
     changed clip **and** its linked audio entry, then
     `_ensure_producer_length`. Return per-clip old/new length, `off_beat`
     flags, and the timeline shift of everything after `last_clip_index`.
   - `beat_zoom(workspace_path, track=0, beat_file="", intensity="medium",
     every_n=0, phase=0, punch=0.12, attack_frames=2, decay_frames=8,
     music_track=-1, music_clip_index=0, music_offset_seconds=-1.0)`: one
     `qtblend` filter per hit clip (not one per beat).
   - `beat_flash(...same selection args..., strength=1.0, decay_frames=3)`:
     one `brightness` filter per hit clip with keyframed `level`.
   - All return the selected beat times, the timeline frames used, beats
     skipped (over blanks / outside music), the bpm, and the new project
     path. Errors: missing beat file -> `missing_file` (suggest
     `music_beat_grid`), empty beats -> `not_found`, bad indices ->
     `invalid_index`.

## Tests

1. **Unit** `tests/unit/test_beat_sync.py`: `select_beats` strides, bar
   inclusion, phase, window, min gap, bad intensity; frame mapping with a
   trimmed music entry; `plan_beat_cut` (exact landing, off-beat fallback,
   more clips than beats, min length); `clip_hits` across clip boundaries and
   blanks; flash/zoom pulse merging; tools via `call_tool` on a workspace
   (pattern `_make_workspace`, `tests/unit/test_nle_operations.py` ~73) with a
   hand-written `beat_grid.json` (no audio decode needed); linked audio
   entries trimmed identically; tools registered.
2. **External render proofs** `tests/integration/external/test_beat_sync_render.py`
   (use a hand-written beat grid at 25 fps with beats every 0.48 s = 12
   frames and `music_offset_seconds=0`):
   - `beat_cut` on colour clips (build producers with `length` 200 so they
     can grow): for each selected beat frame F, frame F-1 renders the
     previous clip's colour and frame F the next clip's colour.
   - `beat_flash` on a grey clip (`0x808080ff`): mean luma at a beat frame
     is clearly above the luma 6 frames later (assert a margin, put the
     numbers in the report).
   - `beat_zoom` on `make_test_clip(kind="video")` (`requires_ffmpeg`): the
     beat frame differs from the same frame without the effect; a frame
     after the decay is similar.
   - End to end (`requires_ffmpeg`): make a 120 BPM click track with ffmpeg
     (`aevalsrc` producing a short 1 kHz burst every 0.5 s), run
     `music_beat_grid` on it, assert bpm within 2 of 120, then `beat_cut`
     with `every_n=1` and assert every new boundary lies within 1 frame of a
     multiple of 0.5 s.

## Acceptance criteria

- The three tools work from a real `music_beat_grid` output and from a
  hand-written grid; cuts land on beats within 1 frame.
- Linked audio stays aligned after `beat_cut`; producer lengths cover the
  new out-points (rule 14).
- Full suite green; ruff clean.

## Do NOT

- Do not change `music_beat_grid`, `markers_from_beats` or the beat
  detection maths.
- Do not add librosa or any new dependency.
- Do not stack one filter per beat on a clip; merge pulses per clip.
- Do not reorder, drop or create clips in `beat_cut`; it only changes
  out-points.

## When done

1. Document the tools in `workshop-video-brain/skills/ff-pacing-meter/SKILL.md`
   or the skill that documents `music_beat_grid` (grep for it): "analyse the
   music, then cut/zoom/flash on the beat", with the intensity table.
2. Add `vault/wiki/beat-synced-editing.md` (beat-to-frame mapping through
   the music entry's in-point, the variety rule, why brightness not opacity).
3. Regenerate `docs/capabilities.md`; mark Phase 4 item 8 done in
   `docs/plans/2026-10-13-media-mcp-expansion.md`.
4. Report as in `00-README.md`, including the luma numbers and the
   end-to-end bpm. Note any idea from the harvest left out (a beat-synced
   montage from a list of sources) as a follow-up.
