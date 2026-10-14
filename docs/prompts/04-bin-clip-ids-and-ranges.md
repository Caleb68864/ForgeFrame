# Prompt 04: bin clip ids, `main_bin` ranges and producer `length` (roadmap step 5, part 1)

Hand this whole file to the implementing model.

---

**Summary.** Every `.kdenlive` file the serializer writes numbers its bin
clips wrong and registers them with zero-length ranges. Media clips get
`kdenlive:id` 2, 3, ... (2 is the "Sequences" bin folder id) and the main
sequence gets `len(producers) + 2`. Native Kdenlive gives the sequence id **3**
and starts user clips at **4**. Every `main_bin` `<entry>` has `out="0"`; the
native value for a media clip is `length - 1`. That cannot be fixed yet
because `clip_insert` never records the producer's `length`, even though it
already probes the media duration. This task fixes the numbering, gives every
modelled producer a `length` that covers all its uses (CLAUDE.md hard rule 14),
and writes `out = length - 1` on the media `main_bin` entries. Timeline-entry
ids and the speed variant come in prompt 05. Do not do them here.

**Read `docs/prompts/00-README.md` first.** Its shell, test and scope rules
apply and are not repeated here. This prompt assumes prompts 01-03 are merged.
Line numbers below are approximate, because prompts 02 and 03 edit the same
files.

## Evidence (verified 2026-10-14)

- **Generated output.** Build the check pack with
  `uv run --project /home/caleb/Projects/ForgeFrame python /home/caleb/Projects/ForgeFrame/scripts/kdenlive_check_pack.py /home/caleb/Projects/ForgeFrame/kdenlive-check-pack`.
  `03_speed.kdenlive` contains:
  - `a_bars_*` with `kdenlive:id` 2, `b_blue_*` with 3, `b_blue_*_tw2` with 4;
  - the sequence tractor with `kdenlive:id` 5;
  - no `length` property on either media producer;
  - every `main_bin` entry with `in="0" out="0"`.
- **Native ground truth.**
  - `tests/fixtures/projects/real/empty_2604.kdenlive` was saved by Kdenlive
    26.04.2. Its sequence has `kdenlive:id` 3 and `kdenlive:folderid` 2.
  - The 25.08.3 saves in `tests/fixtures/kdenlive_references/` agree:
    - `cross_dissolve_native`, `clip_speed_400_native` and
      `multi_clip_and_title_native` all give the sequence 3;
    - their media start at 4.
  - Native media `main_bin` entries end at `length - 1`. For example, in
    `cross_dissolve_native.kdenlive` `chain3` has `length` 1071 and its
    `main_bin` entry has out `00:00:44.628`, which is frame 1070 at 23.976.
  - **The sequence's own `main_bin` entry is `out="00:00:00.000"` in every
    native file. Keep the sequence entry at `out="0"`.**
  - The pre-23.04 corpus files (`corpus_*_2604.kdenlive`, which despite the
    name are Kdenlive 22-23 saves) use id 2 for media. They predate the
    Sequences folder, so ignore them for numbering.
- **What Kdenlive 26.08.2 does with our ids today.** We captured the playlist
  Kdenlive rebuilds during `kdenlive --render 03_speed.kdenlive` (see
  "Verify in Kdenlive" below for how). It renumbers the clips itself:
  - `a_bars` becomes 3, `b_blue` 4, `_tw2` 5 and the sequence 6;
  - its rebuilt `main_bin` entries have real ranges (out `00:00:03.960`).

  So the headless loader tolerates our ids by remapping them. This fix is
  conformance with the native contract, not a crash fix. The GUI pass
  (prompt 06) will show whether the GUI complains.

## Root cause (where to change)

All paths are under `workshop-video-brain/src/workshop_video_brain/`.

1. `edit_mcp/adapters/kdenlive/serializer.py`, `serialize_project`:
   - **Media ids** (around line 524):
     `for kdenlive_id, producer in enumerate(project.producers, start=2):`
   - **Sequence id** (around line 671): `seq_kid = len(project.producers) + 2`.
   - **`main_bin` entries** (around lines 820-829): every producer entry gets
     `entry.set("out", "0")`, and so does the sequence entry.
2. `edit_mcp/server/tools/clips_nle.py`, `clip_insert` (around lines 36-160):
   - It probes `asset.duration` but never passes it on.
   - **Second bug, same function:** it converts seconds to frames with the
     *media* fps (`fps = asset.fps`). MLT producer frames are profile frames,
     so a 30 fps file in a 25 fps project gets in and out points 20% too
     large.
3. `edit_mcp/adapters/kdenlive/patcher_intents.py`, `_apply_add_clip`
   (around line 336): it creates `Producer(...)` with only `resource`.
4. `core/models/timeline.py`, `AddClip` (line 33): it has no way to carry a
   length.

## Steps

### 1. One id map, built before any XML is emitted

Add a module-level helper in `serializer.py`:

```python
SEQUENCE_FOLDER_ID = 2   # kdenlive:folder.-1.2 / kdenlive:sequenceFolder
MAIN_SEQUENCE_ID = 3
FIRST_CLIP_ID = 4

def _assign_bin_ids(project: KdenliveProject) -> dict[str, int]:
    """producer.id -> kdenlive:id for every modelled producer."""
```

- Assign ids in `project.producers` order, starting at `FIRST_CLIP_ID`.
- **Skip every id already used by a preserved native element.** Look at the
  `<producer>`/`<chain>` entries in `project.opaque_elements`, read their
  `kdenlive:id` property, and never hand those ids out again. Reuse the
  parsing pattern of `_known_producer_ids` (around line 343).
- Use the map in the producer loop instead of `enumerate(..., start=2)`.
- Give the sequence tractor `MAIN_SEQUENCE_ID`.
- Use `SEQUENCE_FOLDER_ID` in the three places that hard-code `"2"` for the
  folder: the `kdenlive:folderid` of the sequence and the two `main_bin`
  properties.
- Prompt 05 extends this helper so that speed variants share their base
  clip's id. Keep it a pure function of the project.

### 2. Effective `length` for every modelled producer (hard rule 14)

Add `_effective_length(producer, project) -> int | None` in `serializer.py`.
It returns the maximum of:

- the integer value of `producer.properties["length"]`, when it is a plain
  integer. Native image or colour producers use timecodes such as
  `00:00:05.005`; treat those as unknown.
- `max(entry.out_point) + 1` over every playlist entry whose `producer_id` is
  this producer.

It returns `None` when both are unknown.

When the result is not `None`, write it as the producer's `length` property.
Replace the stored value; never emit two `length` properties. The stored
properties loop already copies `length`, so either skip `length` in that loop
or overwrite the element afterwards with `_set_prop` (around line 153).

This covers every builder that never sets a length: assembly,
selects_timeline, review_timeline, replay_generator, overlay_looks and
PlaceClip. Do not edit those builders.

### 3. `main_bin` media entries: `out = length - 1`

- In the `main_bin` loop, set `out` to `_effective_length(...) - 1` when it is
  known.
- When it is `None` (an unused bin clip with no length), keep `out="0"`, log at
  debug level, and list the case in your report.
- Leave the sequence entry at `out="0"`. It matches native.

### 4. Record the probed length on insert

- Add `producer_length: int = 0` to `AddClip` (`core/models/timeline.py`);
  0 means unknown.
- In `_apply_add_clip`:
  - when the producer is **created** and `intent.producer_length > 0`, set
    `properties["length"]`;
  - when the producer **already exists**, raise its `length` to
    `max(existing, intent.producer_length, intent.out_point + 1)`. Never
    lower it.
- Apply the same rule in `_apply_place_clip` (around line 629) only if
  `PlaceClip` gains the field naturally. Otherwise leave it; step 2 covers it.
- In `clip_insert`:
  - Compute `producer_length = seconds_to_frames(asset.duration, project_fps)`
    when the probe worked, where
    `project_fps = project.profile.fps or 25.0`.
  - Pass it on **every** `AddClip` the tool builds. After prompt 02 there is
    a second, audio `AddClip` for the same producer.
- Fix the fps bug in the same place: convert `in_seconds`, `out_seconds` and
  the duration with `project_fps`, not `asset.fps`. Keep `asset.fps` out of
  the frame math entirely.
- Add `"producer_length"` to the `_ok` payload.
- If a model-completeness test (for example
  `tests/unit/test_kdenlive_model_has_no_dead_declarations.py`) flags the new
  field, wire it properly. Do not add it to an exemption list.

### 5. Validator: catch these regressions in the E shape too

`edit_mcp/adapters/kdenlive/validator.py`, `validate_serialized_xml`
(around line 275). Today the reserved-id and `out=length-1` checks run only
when `twin_shape` is true. Add two checks that run for **every** shape:

- A bin clip (any `main_bin` reference except the main sequence) must not use
  the main sequence's `kdenlive:id`, and must not use the folder id in
  `main_bin`'s `kdenlive:sequenceFolder` property. Message style: "Bin clip
  '<id>' uses kdenlive:id 2, which is the Sequences folder id; user clips start
  at 4."
  - Use this exact collision rule, **not** a blanket ">= 4". Preserved
    pre-23.04 native clips legitimately use 2 when the document has no
    Sequences folder.
- A media `main_bin` entry (producer or chain, not the sequence tractor) whose
  `out` and its producer's `length` are both plain integers must have
  `out == length - 1`.

Do not touch the twin-shape branch.

### 6. Tests (all required)

- **`tests/unit/test_serializer_bin.py`.**
  - Rename `test_kdenlive_id_starts_at_2` to `..._starts_at_4` and expect `"4"`.
  - Expect `{p0: 4, p1: 5, p2: 6}` in `test_kdenlive_id_sequential`.
  - Add:
    - the sequence tractor has id 3;
    - an opaque native chain carrying id 4 pushes the first modelled producer
      to 5;
    - the `main_bin` media entry out equals `length - 1`;
    - the sequence entry stays `out="0"`.
- **`tests/unit/test_bin_lengths.py` (new).** Hermetic: build models with the
  `tests/_testkit.py` builders.
  - A producer without `length` used at out 99 gets `length` 100.
  - A producer reused at two in-points (`0-49` and `150-199`) gets
    `length` 200 (rule 14).
  - A declared `length` 300 larger than every use stays 300.
  - A timecode `length` falls back to the uses.
- **`tests/unit/test_clip_insert_length.py` (new).** Mark it
  `requires_ffmpeg_ffprobe`.
  - Use `make_test_clip(duration=4, fps=25)` in the default 25 fps project and
    assert `length` 100 and `main_bin` out 99.
  - Insert a **30 fps** clip of 2 s and assert its out frame is 49 and its
    length 50 (project frames).
  - Insert the same media twice and assert one producer whose length covers
    both uses.
- **`tests/unit/test_serialized_xml_validation.py`.** Add one blocking case
  each for the folder-id collision and for a bad `main_bin` out. Add one
  passing case: a no-Sequences-folder document with id 2.
- **Dissolve.** Run `tests/unit/test_dissolve_layout.py` unchanged; it must
  still pass. A clip that now has a known `length` and unused media may get a
  dissolve *handle*. That is the documented behaviour of `_apply_add_transition`.
  Do not change it.
- Then run the unit suite, the full suite (expect at least 4806 passed and the
  usual skips; report the numbers) and ruff, as in 00-README.

### 7. Verify in Kdenlive (required)

1. Rebuild the check pack (command under Evidence).
2. Check that every step's file passes the new validator. The serializer runs
   it on write, so a rebuild without errors is the proof.
3. For `03_speed` and `07_title`, capture the playlist Kdenlive rebuilds during
   a headless render. Run this in zsh:

   ```
   S=/tmp/ff-verify-04; mkdir -p $S; touch $S/stamp
   (timeout 300 xvfb-run -a kdenlive --render /home/caleb/Projects/ForgeFrame/kdenlive-check-pack/03_speed.kdenlive $S/03.mp4 > $S/03.log 2>&1 &)
   for i in $(seq 1 400); do f=$(find /tmp -maxdepth 1 -name 'kdenlive-*.mlt' -newer $S/stamp | head -1); if [ -n "$f" ]; then sleep 0.3; cp "$f" $S/03_rebuilt.mlt; break; fi; sleep 0.25; done
   ```

4. In `$S/03_rebuilt.mlt`, record:
   - the `kdenlive:id` of each producer;
   - each `main_bin` entry's `out`.

   Before this fix they were 3/4/5/6. Report what Kdenlive does with ids that
   now arrive as 4/5/(6)/3.
5. Run the prompt-01 differential test (`grep -rn requires_kdenlive
   /home/caleb/Projects/ForgeFrame/tests` finds it). Every step that matched
   before must still match.

## Do NOT

- Do not add `kdenlive:id` to timeline `<entry>` elements or change how the
  `_tw` speed producer is registered. That is prompt 05.
- Do not switch media from `<producer>` to `<chain>`, and do not add
  `kdenlive:control_uuid` to media. The E-shape contract
  (`tests/unit/test_serializer_eshape.py`) forbids it, and prompt 06 decides
  the contract.
- Do not change the dissolve logic from commit `38fe0e1`
  (`_apply_add_transition`, `a_track`/`b_track`, the transition order). Do not
  change audio placement (prompt 02) or effect identity (prompt 03).
- Do not set `out` on the sequence's `main_bin` entry.
- Do not edit the pipeline builders to add lengths; the serializer's effective
  length covers them.

## When done

1. Roadmap (`docs/plans/2026-04-08-feature-roadmap.md`), step 5: strike
   through the ids and `out="0"` items and mark them "Done <date>" with a
   two-line summary. Leave the entry-id and speed-variant items for prompt 05.
2. `docs/testing/2026-10-13-kdenlive-2608-differential.md`: mark defects 2 and
   3 fixed, and add what the rebuilt-playlist capture showed.
3. `vault/wiki/kdenlive-producer-length-must-cover-all-uses.md`: add a section
   saying the serializer now enforces the rule centrally
   (`_effective_length`), and that `clip_insert` records the probed length in
   project frames.
4. Report, using the 00-README format. Also include:
   - Kdenlive's rebuilt ids and `main_bin` outs;
   - any producers left at `out="0"`;
   - whether the fps fix changed any existing test expectations.
