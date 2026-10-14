# Prompt 24: experiment: one producer per timeline placement vs our shared producer + rule 14

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here.

**Summary.** This is an **experiment, not a feature**. Another Kdenlive MCP
project claims that Kdenlive's project loader *silently strips timeline clips*
when one media `<chain>` is referenced from more than one playlist, so every
timeline placement must get its own chain (all copies sharing
`kdenlive:control_uuid`, plus one separate bin chain). ForgeFrame does the
opposite: one media producer per file, referenced by `main_bin` and by every
track and placement, with its `length` raised to cover the largest out-point
(CLAUDE.md hard rule 14). Prompt 02 made this sharing universal (every A/V
clip now puts the same producer on a video track **and** an audio track). Build
layout variants of the same timelines, render each with Kdenlive 26.08 and
melt, prepare a GUI checklist for the human, and write a decision note.
**Do not change the serializer in this task.** If the evidence says it must
change, write a separate follow-up proposal. Depends on prompt 05.

## Ground truth already in the repo

- `tests/fixtures/kdenlive_references/cross_dissolve_native.kdenlive` (saved
  by Kdenlive): one media file is used on an audio track (`playlist0`, entry
  -> `chain0`) and on a video track (`playlist6`, entry -> `chain2`). These
  are **two separate `<chain>` elements** (`avformat-novalidate`) with the
  same `kdenlive:id` (4) and the same `kdenlive:control_uuid`, plus a third
  bin chain (`chain3`, `avformat`) referenced only by `main_bin`.
- `multi_clip_and_title_native.kdenlive`: the same media on two different
  tracks again gets one chain per track (`chain0` on `playlist2`, `chain1` on
  `playlist4`, both `kdenlive:id` 6), plus bin chain `chain5`.
- No native fixture places the **same media twice on the same track**, so
  "one per track" and "one per placement" are not yet distinguished.
- `mix_slide_upstream_kde.kdenlive` (KDE's own test data, older format):
  `color` producers `producer0` etc. are shared by `main_bin` and two tracks.
- Our serializer (`edit_mcp/adapters/kdenlive/serializer.py`, producer loop
  ~514) emits one `<producer>` (or `<chain>` when it has links) per
  `project.producers` entry, used everywhere. `tests/unit/test_serializer_eshape.py`
  documents why (GUI-confirmed "E shape" on Kdenlive 26.04; media producers
  carry neither `kdenlive:uuid` nor `kdenlive:control_uuid`).
- Kdenlive 26.08 renders our shared-producer projects correctly for
  `01_single_clip` and `02_two_clips` (`docs/testing/2026-10-13-kdenlive-2608-differential.md`).
  `kdenlive --render` returns 0 even when it drops things; only measuring the
  output reveals a drop.
- Rule 14 evidence: `vault/wiki/kdenlive-producer-length-must-cover-all-uses.md`.

## Steps

1. **Media.** Generate one test file with ffmpeg: four 2 s solid segments
   (red, green, blue, white) at 25 fps, 320x180, joined with the `concat`
   filter, plus a sine audio track (`-shortest`). The colour at a frame tells
   you which source in-point was played.
2. **Scenarios** (build each as a `KdenliveProject` with the testkit model
   classes or through the MCP tools, then serialize with the normal
   serializer):
   - **S1 A/V**: one placement of source frames 0-49 via `clip_insert`
     (video entry + audio entry sharing the producer, from prompt 02).
   - **S2 twice on one track**: video entries `[0-49]` then `[100-149]` of the
     same producer (green expected second). Two sub-cases: producer `length`
     covering 150+ (rule 14 applied) and `length=50` (rule 14 violated).
   - **S3 two video tracks**: frames 0-49 on one video track and 150-199 on
     a second video track at the same time (use `two_track_project` from the
     testkit as the model). The upper track should win; confirm which
     playlist is on top with one V0 melt render first and record it.
   - **S4 speed**: one normal placement plus one `clip_speed` 2x placement of
     the same media (timewarp variant from prompt 05).
3. **Layout variants**, produced by an experiment script that **post-processes
   the serialized XML** (`ET`), not by touching the serializer:
   - **V0 shared** (our current output, unchanged);
   - **V1 per track**: for each (media, track) clone the producer element
     (new id `<id>_t<n>`, same properties including `kdenlive:id`) and repoint
     that track's entries; `main_bin` keeps the original;
   - **V2 per placement**: one clone per entry (`<id>_p<n>`);
   - **V1u / V2u**: as V1/V2 but every copy and the bin element also get one
     shared `kdenlive:control_uuid` (`{uuid4}`), like the native fixtures;
   - In V1/V2 set each clone's `length` to cover only its own entries; keep
     the bin element's `length` covering everything.
4. **Script** `scripts/chain_placement_experiment.py [OUT_DIR]` (default
   `./kdenlive-chain-experiment`, add it to `.gitignore` next to
   `kdenlive-check-pack/`). Model it on `scripts/kdenlive_check_pack.py`. It
   writes `<scenario>_<variant>.kdenlive`, then for each file:
   - `melt <file> -consumer avformat:<x>_melt.mp4 terminate_on_pause=1`
     under `xvfb-run -a`;
   - `xvfb-run -a kdenlive --render <file> <x>_kdenlive.mp4`;
   - every `subprocess.run` has `timeout=` (use the constants in
     `adapters/ffmpeg/runner.py`) and captures stderr; save logs next to the
     outputs;
   - measure: duration (ffprobe), the mean colour at the middle frame of
     every expected placement (ffmpeg single-frame extract or `_oracle`
     helpers), audio mean volume (`volumedetect`), and any stderr line
     containing "missing", "removed", "invalid" or "corrupt";
   - write `results.json` and `RESULTS.md` (one row per file: expected vs
     observed colours per placement, duration, dB, verdict) and
     `CHECKLIST.md` for the human (step 5).
   - Add `--analyze-resaved` that, for every `*_resaved.kdenlive` in the
     folder, counts producer/chain elements per media resource and per
     playlist, and prints which layout Kdenlive itself chose.
5. **GUI checklist for the human** (`CHECKLIST.md`, you cannot do this
   headless). For each file: open in Kdenlive 26.08; copy any dialog text
   verbatim; count clips per track against the expected list; count bin
   clips (expected: one per media; duplicates are a defect); check Project
   Notes for "removed" warnings; then **Save As `<name>_resaved.kdenlive`**
   in the same folder. The re-saved files are the strongest evidence: they
   show the layout Kdenlive rewrites our file into, especially for S2.
6. **Optional source check** (only if network access works): shallow-clone
   `https://invent.kde.org/multimedia/kdenlive` into the session scratchpad
   and read how the timeline builder resolves an entry's producer back to a
   bin clip (`src/timeline2/model/builders/meltBuilder.cpp`) and how
   `src/bin/projectclip.cpp` creates per-track timeline producers. Quote
   file and line numbers in the note. Skip without network; do not guess.

## Decision rules (write them into the note with the numbers)

- **Claim refuted**: V0 matches melt in Kdenlive renders for S1-S4 (every
  placement shows the expected colour, audio above -60 dB) and the human's
  GUI pass shows no dialog and no missing clips. Keep the shared producer and
  rule 14; record that Kdenlive re-saves it into per-track chains (if the
  resaved files show that) as cosmetic.
- **Claim confirmed** (for some scenario): V0 loses or mis-renders a placement
  in Kdenlive while V1 or V2 is correct. Prefer the smallest change that
  works, in this order: V1 (matches the native fixtures), then V1u, then V2.
  Write the follow-up proposal (below); still do not edit the serializer.
- S2 with `length=50` is the rule-14 control: it should fail in every
  variant where the over-range entry still points at a short element. If it
  does not fail in Kdenlive 26.08, say so: rule 14 may be obsolete.
- Inconclusive (renders fine, GUI not yet done): write the note with status
  "pending GUI pass" and stop.

## Tests

- Add one external test `tests/integration/external/test_chain_layout_variants.py`
  (`requires_melt`; and the `requires_kdenlive` mark if prompt 01 added it)
  that builds S1 and S2 in V0 and V1 and asserts melt renders the expected
  colours. It guards the experiment harness, not the serializer.
- Unit-test the XML post-processor (clone counts, repointed entries, ids
  unique, `kdenlive:id` preserved) in `tests/unit/test_chain_layout_variants.py`.

## Acceptance criteria

- `RESULTS.md` has a filled row for every scenario x variant, with melt and
  Kdenlive results side by side.
- `vault/wiki/kdenlive-chain-per-placement.md` exists with: the claim, the
  native-fixture evidence above, the results table, the decision, and what
  the human still has to check.
- The serializer and its tests are unchanged (`git diff` on
  `serializer.py` is empty).

## Do NOT

- Do not change `serializer.py`, `parser.py`, `patcher_intents.py` or any
  hard rule in `CLAUDE.md`.
- Do not adopt any other habit from the other project (bin ids from 2, no
  bin twin, no control_uuid on the main tractor, `dynamictext` titles,
  non-canonical 29.97 profile, unsorted dissolve tracks, single-sequence
  save).
- Do not commit the generated media or projects.

## When done

1. If the decision is "change needed": write
   `docs/plans/2026-10-14-serializer-producer-layout-proposal.md` with the
   chosen variant, the exact XML shape (copy from the native fixture and the
   resaved files), affected code (`serializer.py` producer loop, parser
   round-trip of clones back to one model producer, rule 14 helpers,
   `test_serializer_eshape.py`), and a test plan. Otherwise skip.
2. Add a row to `vault/index.md` for the new note; add a line under
   CLAUDE.md's vault list **only** pointing to the note (no rule changes).
3. Mark Phase 4 item 9 in `docs/plans/2026-10-13-media-mcp-expansion.md` as
   "experiment run, see note" (or "pending GUI pass").
4. Report as in `00-README.md`: the results table, the decision, and the
   exact list of files the human must open.
