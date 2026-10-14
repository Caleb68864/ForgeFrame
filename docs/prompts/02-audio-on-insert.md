# 02 -- Fix "audio is lost on insert" (roadmap step 2)

Read `docs/prompts/00-README.md` first; its shared rules apply. Needs prompt 01
(the Kdenlive differential test): its `xfail` for audio should flip to passing
when this is done. Remove that `xfail` marker as part of this task.

---

You are working in the ForgeFrame repo at `/home/caleb/Projects/ForgeFrame`,
branch `feat/media-mcp-phase0`. It is an MCP server that edits Kdenlive
`.kdenlive` project files (MLT XML) directly and renders them with `melt`.
Read `CLAUDE.md` at the repo root first. Its rules are mandatory, especially
the "Authoring a New MCP Tool" checklist, the Testing section, and
"Kdenlive XML serialization".

## Shell rules for this machine (important)

- Do NOT use `cd`. In this zsh, `cd` runs `eza` and hangs. Use absolute paths
  and `git -C /home/caleb/Projects/ForgeFrame ...`.
- zsh does not word-split unquoted variables. Use arrays or literal arguments.
- Run Python through uv: `uv run --project /home/caleb/Projects/ForgeFrame ...`.
- Tests that use melt need a display: prefix the command with `xvfb-run -a`.
- Do not commit. Report back when finished.

## The bug

Every timeline built with the `clip_insert` MCP tool is silent, in both melt
and Kdenlive 26.08 (measured at -91 dB). Evidence is in
`docs/testing/2026-10-13-kdenlive-2608-differential.md`. To reproduce, run
`uv run --project /home/caleb/Projects/ForgeFrame python /home/caleb/Projects/ForgeFrame/scripts/kdenlive_check_pack.py /home/caleb/Projects/ForgeFrame/kdenlive-check-pack`
and open `kdenlive-check-pack/02_two_clips.kdenlive`. You will see:

- `<playlist id="playlist_audio" />` is empty.
- The video track's lanes are `<track hide="audio" .../>`, so the clip's
  audio is muted where the clip actually sits.

### Root cause

- `clip_insert` in
  `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/clips_nle.py`
  (around lines 39-160) builds a single `AddClip` intent that targets only the
  first video playlist.
- `_apply_add_clip` in
  `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher_intents.py`
  (around line 336) inserts one `PlaylistEntry` into that playlist and nothing
  else.
- Nothing ever places the clip's audio on an audio track.

## What Kdenlive itself does (the ground truth)

See `tests/fixtures/kdenlive_references/cross_dissolve_native.kdenlive`.

- A clip with audio occupies **two** timeline tracks:
  - a video entry on a video track;
  - an audio entry on an audio track, at the **same timeline position** with
    the same in and out points.
- In that fixture, `playlist0` (audio track, `hide="video"` lanes) and
  `playlist6` (video track, `hide="audio"` lanes) both have `<blank length=…>`
  followed by an `<entry>` with the same in, out and `kdenlive:id`.
- The two halves are linked through the sequence property
  `kdenlive:sequenceproperties.groups`, as an `"AVSplit"` group whose leaves
  are `"<trackIndex>:<positionFrame>:-1"`.
  - Grouping is optional for this fix. Do NOT emit groups unless you have
    verified the track-index numbering against that fixture. Leave it as a
    follow-up note.

The test builders already put the same producer on both tracks; melt renders
audio from that. See `sequence_project` in `tests/_testkit.py`.

## The fix: do these steps in order

### 1. Probe for audio

`clip_insert` already calls `probe_media(media_file)`. The returned
`MediaAsset` (`core/models/media.py`) has `audio_codec` and `channels`.
Treat the media as having audio when `channels > 0` or `audio_codec` is
non-empty. If the probe fails, keep the current behaviour: video only, and
add `"audio_placed": false` to the result.

### 2. Place the audio half

Choose the target audio playlist: the first playlist whose track has
`track_type == "audio"`. Track types come from `project.tracks`; copy the
lookup pattern `clip_insert` already uses for video.

- If the media has audio and an audio track exists, emit a **second**
  `AddClip` intent in the same `patch_project` call. It uses the same
  `producer_id`, `in_point`, `out_point` and `source_path`, with
  `track_ref`/`track_id` set to the audio playlist id.
- The audio entry must start at the same **timeline frame** as the video
  entry. The playlists are sequential (an entry's start is the sum of the
  lengths of everything before it, including blanks), so appending to both
  playlists only lines up when both have the same total length. Handle that
  case:
  - Compute the video playlist's timeline length before the insert (sum of
    `out_point - in_point + 1` over all entries, blanks included; a blank
    entry has `producer_id == ""`).
  - Do the same for the audio playlist.
  - If the audio playlist is shorter, append a blank first:
    `PlaylistEntry(producer_id="", in_point=0, out_point=gap - 1)`.
  - Put this logic in a helper in `patcher_intents.py` (logic belongs in the
    adapter, not the tool shell).
  - Simplest correct design: add an optional `align_with_track: str = ""`
    field to `AddClip` in `core/models/timeline.py`. When it is set and
    `position < 0`, `_apply_add_clip` pads the target playlist with a blank
    up to the start frame the clip has on `align_with_track`. Existing
    callers are unaffected because the default is empty.
- For `position >= 0` (insert in the middle), insert into the audio playlist
  at the index of the entry that starts at the same timeline frame. If no
  such index exists, log a warning, place the video only, and report
  `"audio_placed": false`. Do not guess.
- Return `"audio_playlist_id"` and `"audio_placed": true/false` in the
  `_ok` payload.

### 3. Keep linked edits in sync

Check every tool that edits a clip by index on the video track. It must also
edit the linked audio entry: same `producer_id`, same timeline start frame.

- `_apply_set_clip_speed` (patcher_intents.py, around line 852): its
  docstring says it already swaps "linked entries (same producer at the same
  clip index on other tracks)". Verify with a test that after `clip_speed` the
  audio entry is retimed too. Fix it if not.
- `audio_fade` tool (clips_nle.py, around line 548) and `_apply_audio_fade`
  (patcher_intents.py, around line 1068): it currently resolves a **video**
  playlist and nests the `volume` filter in the video entry, whose audio is
  hidden, so the fade is inaudible. Make it target the linked audio entry
  when one exists. Fall back to the old behaviour otherwise.
- **`audio_fade` must also use Kdenlive's native fade identity.** Today's
  `volume` filter has no `kdenlive_id`, so Kdenlive 26.08 drops it even once
  it sits on the audio entry: it plays in melt but is silent in Kdenlive.
  Kdenlive's own form, from
  `tests/fixtures/kdenlive_references/audio_mix_upstream_kde.kdenlive`
  lines 144-176 (ids from `/usr/share/kdenlive/effects/fadein.xml` and
  `fadeout.xml`), is a filter nested in the audio `<entry>`. The filter's
  `in`/`out` attributes span only the fade, in clip-local frames:
  - fade in: `<filter out="{dur-1}">`;
  - fade out: `<filter in="{clip_len-dur}" out="{clip_len-1}">`;
  - properties `window=75`, `max_gain=20dB`, `mlt_service=volume`, and
    `kdenlive_id` = `fadein`/`fadeout`;
  - fade in uses `gain=0`, `end=1`; fade out uses `gain=1`, `end=0`;
  - no `level` keyframe string.

  Replace the keyframed `level` form in `_apply_audio_fade` with this form.
  Check how the serializer passes filter `in`/`out` attributes through
  (`_extract_clip_filters` in `serializer.py`); keep them if they are already
  preserved, otherwise make them preserved. Prove it in melt: the first
  0.5 s of a fade-in is quieter than seconds 2-3. Prove it in Kdenlive with
  the step-5 measurement below.
- `_apply_add_transition` (patcher_intents.py, the dissolve; fixed in commit
  `38fe0e1`; do not change its video logic). When it pulls the right clip
  earlier by `pull` frames, the audio of the right clip and of every later
  clip must move the same amount. Otherwise audio drifts out of sync after a
  dissolve. Minimal correct fix:
  - In the audio playlist, find the linked audio entry of the right clip.
  - Shorten the audio timeline before it by `pull` frames (shrink or remove
    the preceding blank, or trim the left clip's audio out-point by `pull`).
  - If the left audio entry was extended by `extend` frames on video, extend
    its audio the same way.
  - An audio crossfade (`mix`) is optional. Skip it.
  - Add a test that the audio and video start frames of the right clip are
    equal after the dissolve.
- Grep for other intents that move or trim video entries
  (`TrimClip`, `InsertGap`, ripple/move intents in `patcher_intents.py`).
  For each, either keep audio in sync or add a line to the report listing it
  as a known gap. Do not silently skip this.

### 4. Tests (all required)

- **Unit** (`tests/unit/test_clip_insert_audio.py`). Build projects with
  `tests/_testkit.py` helpers. Call the tool with `call_tool`/`unwrap`, as
  other unit tests in `tests/unit/` do, using `make_test_clip(...,
  with_audio=True)` for real media. Real media needs ffmpeg, so add the
  `requires_ffmpeg_ffprobe` mark from `tests/_testkit.py`. Assert:
  - The audio playlist gets an entry with the same producer, in and out.
  - The audio and video entries start at the same timeline frame after two
    inserts.
  - A video-only file (`make_test_clip(..., with_audio=False)`) places no
    audio entry and reports `audio_placed: false`.
  - `clip_speed` and the dissolve keep audio and video start frames equal.
  - `audio_fade` puts its `volume` filter on the audio entry.
- **External render proof** (`tests/integration/external/`, see CLAUDE.md
  checklist item 6). Build a timeline through `clip_insert` with a media clip
  that has audio, render it with `render_video` from `_oracle.py`, and use
  `audio_stats` (`_oracle.py:350`) to assert the output is NOT silent: mean
  volume above -60 dB; the bug measures -91 dB. Copy the style of
  `tests/integration/external/test_track_audio.py`. Any `melt ... -consumer
  null:` call must include `terminate_on_pause=1`.
- Run, in order:
  1. `uv run --project /home/caleb/Projects/ForgeFrame pytest /home/caleb/Projects/ForgeFrame/tests/unit -q -p no:cacheprovider`
  2. `xvfb-run -a uv run --project /home/caleb/Projects/ForgeFrame pytest /home/caleb/Projects/ForgeFrame/tests -q -p no:cacheprovider`
     This takes about 7 minutes. The baseline is 4806 passed and 20 skipped,
     and the skips are expected. Do not pass `-n` (no xdist installed).
  3. `uvx ruff check --select F401,F841` on the files you changed. It must be
     clean.

### 5. Verify in real Kdenlive (required, not optional)

Kdenlive 26.08.2 is installed, and `kdenlive --render` works headless.

1. Rebuild the check pack (command under "The bug").
2. For `02_two_clips`, `03_speed`, `04_dissolve` and `05_audio_fade`:
   - `xvfb-run -a kdenlive --render <project> <out>.mp4`
   - `melt <project> -consumer avformat:<out_melt>.mp4 terminate_on_pause=1`
3. Measure audio for both outputs with
   `ffmpeg -i X.mp4 -af volumedetect -f null - 2>&1 | grep mean_volume`.
   - Both must be well above -60 dB.
   - In `05_audio_fade`, the first 0.5 s must be quieter than seconds 2-3. Use
     `-ss`/`-t` with `volumedetect`.
4. Put the numbers in the report.

## Do NOT

- Do not change the dissolve's video logic, `a_track`/`b_track`, or transition
  ordering in `serializer.py`. They were just fixed and verified against
  Kdenlive.
- Do not remove `hide="audio"` from video-track lanes. Kdenlive's own files
  have it; the fix is a real audio-track entry.
- Do not edit any `__init__.py` or tool registry; tools are auto-discovered.
- Do not "fix" the F401 re-export block in `adapters/kdenlive/patcher.py`.
  It is intentional.
- Do not touch `kdenlive:id` numbering or `main_bin` `out="0"`. That is
  roadmap step 5, a separate task.
- Do not write into `media/raw/` or `projects/source/`.
- Do not hand-roll ffprobe or `ET` in the tool shell. Use `probe_media`, the
  intents and the serializer.

## When done

1. Update `docs/plans/2026-04-08-feature-roadmap.md`: mark step 2 "Done"
   with the date and a one-paragraph summary, in the same style as step 4.
2. Update the `05 audio fade` row in
   `docs/testing/2026-10-13-kdenlive-2608-differential.md` with your measured
   numbers.
3. Add a vault note `vault/wiki/kdenlive-av-clip-placement.md`: a clip with
   audio needs an entry on a video track and an audio track at the same frame,
   plus the fixture evidence.
4. Report:
   - files changed;
   - test counts;
   - the Kdenlive/melt dB numbers;
   - any intents you found that still do not keep audio in sync.
