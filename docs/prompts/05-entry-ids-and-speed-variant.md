# Prompt 05: `kdenlive:id` on timeline entries; speed variants are not bin clips (roadmap step 5, part 2)

Hand this whole file to the implementing model.

---

**Summary.** Two hard-rule violations remain in generated XML.

1. Timeline `<entry>` elements carry no `<property name="kdenlive:id">`.
   Native Kdenlive writes the bin clip's id on every entry (hard rule 7).
2. The speed tool (`clip_speed`, intent `SetClipSpeed`) creates a `timewarp`
   producer `<base>_tw<speed>`. The serializer then registers it in `main_bin`
   as a separate bin clip with its own id, so the user sees a phantom second
   clip in the project bin. Natively, a speed-changed placement is a
   timeline-only `timewarp` producer that carries the **base clip's**
   `kdenlive:id` and is **not** listed in `main_bin`.

The same applies to the speed-ramp variants: `_tw<speed>[_pc]` slices and
`<base>_timeremap_*` chains. This task emits entry ids from the id map that
prompt 04 introduced, makes every speed or time-remap variant share its base
clip's id, drops variants from `main_bin`, and teaches the validator the rule.

**Read `docs/prompts/00-README.md` first.** Prompt 04 must be merged:
`_assign_bin_ids` and `_effective_length` exist in `serializer.py`.

## Evidence

- **Ground truth:**
  `tests/fixtures/kdenlive_references/clip_speed_400_native.kdenlive`
  (Kdenlive 25.08.3):
  - **Bin clip** `chain id="clip_kdbin"`: `avformat-novalidate`, `length` 119,
    `kdenlive:id` 4.
  - **Variant** `producer id="producer1"`:
    - `mlt_service=timewarp`, `warp_speed=4`, `warp_resource=<path>`,
      `resource=4.000000:<path>`;
    - `length` 30, which is 119/4 rounded;
    - `kdenlive:id` **4**, the same as the bin clip.
  - **Timeline entry** `<entry producer="producer1" ...>`, whose first child is
    `<property name="kdenlive:id">4</property>`.
  - **`main_bin`** lists only `clip_kdbin` and the sequence. The variant is
    absent.
- **Entry ids** are on every native timeline entry, in every fixture. The
  property is the entry's **first** child, **before** any nested `<filter>`;
  see `mlt_plus_video_effects_upstream_kde.kdenlive` around line 187.
- **What we emit today:** check-pack `03_speed.kdenlive`.
  - `b_blue_*_tw2` has `kdenlive:id` 4 (its own) and a `main_bin` entry.
  - The entries have no id property.
- **What Kdenlive 26.08.2 rebuilds from it.** We captured the playlist during
  `kdenlive --render`; the method is under "Verify in Kdenlive".
  - The variant stays a **separate bin clip** (id 5, listed in `main_bin`).
  - Its resource is mangled to
    `<project root>/2:media/b_blue.mp4` (the root is prefixed in front of the
    speed).
  - The render still matched melt (6.0 s), so this is a bin/UI defect, not a
    render defect.

## Where the code is

All paths are under `workshop-video-brain/src/workshop_video_brain/edit_mcp/`.

- `adapters/kdenlive/serializer.py`:
  - `_assign_bin_ids` (added by prompt 04);
  - the clips-lane loop in `serialize_project` that creates
    `e_elem = ET.SubElement(pl_elem, "entry")` and appends nested clip filters
    (around line 600);
  - the `main_bin` loop (around line 820).
- **Variant creators:**
  - `adapters/kdenlive/patcher_intents.py`:
    - `_apply_set_clip_speed` (around line 852): id `f"{base}_tw{speed:g}"`;
      sets `warp_resource` to the base resource.
    - `_ensure_timewarp_producer` (around line 940): id from
      `_tw_producer_id` (`_tw<speed>` plus an optional `_pc`).
  - `server/bundles/speed_ramp.py` (around line 60): a chain
    `f"{base}_timeremap_{playlist}_{in}"` with
    `resource=src.resource` and a `Link(mlt_service="timeremap")`.
- `adapters/kdenlive/validator.py`, `validate_serialized_xml`:
  - In the E-shape branch, `registered = reference in bin_refs` (around
    line 405). A variant removed from `main_bin` will fail this check until you
    change it.
  - The bin-id uniqueness check (around line 420) fails if a variant stays in
    `main_bin` while sharing its base's id. **Both changes must land
    together.**
- `adapters/kdenlive/parser.py`, `_parse_playlist` (line 139): it ignores
  `<property>` children of an entry. That is fine, because the serializer
  regenerates the ids. Do not start storing them in the model.

## Steps

### 1. Identify variants and their base (serializer helper)

Add `_variant_base(producer, project) -> Producer | None` in `serializer.py`.
It decides whether a producer is a *placement variant* of another modelled
producer:

- **timewarp:** `mlt_service == "timewarp"` and some *non-variant* producer's
  `resource` equals this producer's `warp_resource`.
  - Compare with backslashes normalised to `/`, the way the serializer writes
    resources.
- **time-remap chain:** the producer has a link with
  `mlt_service == "timeremap"` and some producer **without links** has the
  same `resource`.
- If several candidates match, pick the first in `project.producers` order.
- If none match, it is **not** a variant. This happens with a parsed project
  whose base was removed. Keep it as its own bin clip (today's behaviour) and
  log a warning.

Do not rely on id string patterns (`_tw`, `_timeremap_`) for the decision.
You may use them only as a tie-breaker when two resources match.

### 2. Variants share the base id

- Extend `_assign_bin_ids`. Number the non-variants first, in producer order,
  exactly as prompt 04 does. Then map each variant to its base's id.
- Existing numbering of non-variants must not change. A variant created before
  its base cannot happen, but handle it by resolving the base first.

### 3. `main_bin` omits variants

- Skip variants in the `main_bin` loop.
- A variant keeps its own `length` (written by `_effective_length`). It gets no
  `main_bin` entry.
- Do **not** add `kdenlive:kextractor` or `kdenlive:monitorPosition` to a
  variant.

### 4. Every timeline entry carries the bin id

- When the serializer creates a timeline `<entry>`, insert
  `<property name="kdenlive:id">N</property>` as its **first** child. Insert it
  before the nested clip filters are appended.
  - N comes from `_assign_bin_ids`. For a variant that means the base id.
- **Producers preserved as opaque XML.** If the entry references a native
  `<producer>`/`<chain>` kept in `project.opaque_elements`, use that element's
  own `kdenlive:id` property. If it has none, emit no property.
- Entries on the black-track background and on `main_bin` get **no** property.
  Blanks get nothing.
- This includes audio-track entries added by prompt 02, which reference the
  same producer as their video twin.

### 5. Validator

In `validate_serialized_xml`, for **every** shape:

1. **Variants count as registered.** A timeline entry's producer counts as
   registered when it is in `bin_refs`, **or** when its `kdenlive:id` equals
   the `kdenlive:id` of a registered bin clip **and** it is a timewarp producer
   or a chain with a `timeremap` link.
   - Otherwise keep the existing "has no matching registered bin clip" error.
2. **Entry ids must match.** A timeline entry (not in `main_bin`, not the
   black track) whose producer has a `kdenlive:id` must carry an entry
   `kdenlive:id` property with the same value.
   - Message: "Timeline entry for '<ref>' must carry its bin clip's
     kdenlive:id (<n>)."
   - The twin-shape branch already has this check (around line 398). Make it
     shape-independent, but **do not** weaken the twin-shape-specific checks.
3. **Native documents still pass.** Run the validator over every file in
   `tests/fixtures/kdenlive_references/` and `tests/fixtures/projects/real/`.
   Any that passed before must still pass.
   - Some native files use timecode attributes. The checks compare only plain
     integers, as the existing code does.

### 6. Do not change the timewarp `resource` format yet

Native writes `4.000000:<path>`; we write `2:<path>`. melt accepts both. The
Kdenlive mangling described under Evidence may disappear once the variant is
no longer a bin clip, because Kdenlive then rebuilds it from the bin clip and
`warp_speed`.

- Check this during verification (step 8).
- **Only if** the rebuilt resource is still mangled **and** the speed clip
  misbehaves (wrong duration, or render differs from melt): switch
  `_timewarp_resource` to `f"{speed:.6f}:{inner}"`, add a test, and say so in
  the report.
- Otherwise leave it and report what you saw.

### 7. Tests (all required)

- **`tests/unit/test_serializer_entry_ids.py` (new, hermetic).**
  - Two producers on V1 plus an audio track holding the same first producer.
    Every entry's first child is `kdenlive:id` with the right value, and
    clip-filter children follow it.
  - A blank gets no property.
  - An entry referencing an opaque native chain with `kdenlive:id` 7 carries 7.
- **`tests/unit/test_speed_variant_bin.py` (new, hermetic).** Build a project,
  apply `SetClipSpeed` through `patch_project`, then serialize and assert:
  - the `_tw2` producer has the base's `kdenlive:id`;
  - it is absent from `main_bin`;
  - `main_bin` has exactly one entry per real clip plus the sequence;
  - the entry referencing `_tw2` carries the base id;
  - the validator reports no issues.

  Repeat for a speed ramp (`_ensure_timewarp_producer` slices, including a
  `_pc` one) and a time-remap chain built with the `speed_ramp` bundle's
  helper. Check its signature first.
- **Golden comparison with `clip_speed_400_native.kdenlive`.** Parse the
  native file with `ElementTree` (not the project parser: it has timecodes).
  Assert the same three invariants hold in both the native file and our
  output:
  1. variant id == bin clip id;
  2. the variant is not in `main_bin`;
  3. the entry id equals the variant id.
- **Validator unit cases.** Add these:
  - a variant not in `main_bin` but sharing a registered id passes;
  - a variant with an unknown id fails;
  - a timeline entry missing its id fails;
  - a timeline entry with the wrong id fails.
- **Existing render proofs must still pass:**
  `tests/integration/external/test_speed_duration.py`,
  `test_speed_ramp_render.py` and `test_timeremap_render.py`.
- Run the unit suite, the full suite and ruff, as in 00-README.

### 8. Verify in Kdenlive (required)

1. Rebuild the check pack:
   `uv run --project /home/caleb/Projects/ForgeFrame python /home/caleb/Projects/ForgeFrame/scripts/kdenlive_check_pack.py /home/caleb/Projects/ForgeFrame/kdenlive-check-pack`
2. Capture the playlist Kdenlive rebuilds for `03_speed.kdenlive` (zsh):

   ```
   S=/tmp/ff-verify-05; mkdir -p $S; touch $S/stamp
   (timeout 300 xvfb-run -a kdenlive --render /home/caleb/Projects/ForgeFrame/kdenlive-check-pack/03_speed.kdenlive $S/03.mp4 > $S/03.log 2>&1 &)
   for i in $(seq 1 400); do f=$(find /tmp -maxdepth 1 -name 'kdenlive-*.mlt' -newer $S/stamp | head -1); if [ -n "$f" ]; then sleep 0.3; cp "$f" $S/03_rebuilt.mlt; break; fi; sleep 0.25; done
   ```

3. Report from `$S/03_rebuilt.mlt`:
   - whether `main_bin` lists the variant (expected: no);
   - the variant entry's `kdenlive:id` (expected: equal to `b_blue`'s);
   - the variant's `resource` string;
   - the duration of `$S/03.mp4`
     (`ffprobe -v error -show_entries format=duration -of csv=p=0`), which
     must be about 6.0 s.
4. Run the prompt-01 differential test (`grep -rn requires_kdenlive
   /home/caleb/Projects/ForgeFrame/tests`). Every step that matched before must
   still match, especially `03_speed` and `04_dissolve`.

## Do NOT

- Do not change bin id numbering for non-variants, `length`, or `main_bin`
  `out`. Prompt 04 owns those; only extend its helpers.
- Do not change the dissolve (commit `38fe0e1`), audio placement (prompt 02)
  or effect identity (prompt 03).
- Do not emit one producer or chain per placement ("per-track twin chains", as
  native 25.08 does). That is prompt 24. Do not add `kdenlive:control_uuid` to
  media or variants; prompt 06 settles that contract.
- Do not store entry ids in the model or the parser.
- Do not rename variant producer ids; existing tests and projects reference
  them.

## When done

1. Roadmap step 5: mark the entry-id and speed-variant items done, with the
   date and a two-line summary. Step 5 is then complete.
2. `docs/testing/2026-10-13-kdenlive-2608-differential.md`: mark defects 4 and
   5 fixed. Add the rebuilt-playlist observations.
3. `vault/wiki/kdenlive-clip-speed-pattern.md`:
   - Update the "Implementation in this repo" section: variants share the base
     id, are not in `main_bin`, and the serializer detects them by
     `warp_resource`/`timeremap` link.
   - Note what Kdenlive 26.08 does with the resource string.
4. Report, using the 00-README format. Also include:
   - the rebuilt-playlist facts from step 8;
   - whether step 6 was needed;
   - any producer the serializer could not resolve to a base.
