# Prompt 06: Kdenlive 26.08 GUI pass, native fixtures, and the 26.x hard-rules rewrite (roadmap step 6)

This prompt has two parts.

- **Part A** is for **Caleb (a human)**. It needs the Kdenlive GUI, so a model
  cannot do it.
- **Part B** is for the implementing model, and starts only after Part A is
  committed.

---

**Summary.** The serializer emits the "E shape", which was GUI-confirmed
against Kdenlive 26.04. But `CLAUDE.md`'s "Kdenlive XML serialization"
section, its 14 hard rules, `AGENTS.md`, and several vault pages still
describe the Kdenlive 25.x **twin-chain** contract. The one 26.04 GUI anchor
the E-shape tests point at
(`smoke-test/.../smoke_test_full_candE_corpus_match.kdenlive`) is **not on
disk**, so `tests/unit/test_serializer_eshape.py::test_candidate_e_*`
silently skip. The only true 26.x native save in the repo is the empty
project `tests/fixtures/projects/real/empty_2604.kdenlive`. The other
"native" fixtures in `tests/fixtures/kdenlive_references/` are 25.08.3 saves.

- **Part A** produces real Kdenlive 26.08 evidence: load dialogs recorded
  verbatim, plus native saves.
- **Part B** diffs our output against those saves, adds golden-fixture tests
  anchored on them, and rewrites the contract docs to match.

Prompts 02-05 must be merged first.

---

## Part A: for Caleb (Kdenlive 26.08 GUI)

Time needed: about 30-45 minutes. Use the real desktop session, not
`xvfb-run`.

1. Rebuild the pack from the merged code:
   `uv run --project /home/caleb/Projects/ForgeFrame python /home/caleb/Projects/ForgeFrame/scripts/kdenlive_check_pack.py /home/caleb/Projects/ForgeFrame/kdenlive-check-pack`
2. Start Kdenlive 26.08.2 and confirm the version under Help > About.
3. In **Settings > Configure Kdenlive**, make sure no proxy clips are
   auto-generated. Proxies change the saved XML.
4. For each `kdenlive-check-pack/NN_*.kdenlive`, in order:
   1. File > Open.
   2. Copy **every** dialog **verbatim** into the *Result* column of
      `kdenlive-check-pack/CHECKLIST.md`. This includes "Project corrupted",
      "Clip ... not found in project bin", "Clip Problems", "non standard
      framerate", effect-removed notices and "document was modified / upgraded"
      prompts. Write the title and the full text. "None" is a valid result.
   3. Check the row's *Expect* column and write `ok` or what differs:
      - **Bin:** exactly one clip per source file (2 media, plus a title in
        07) and a "Sequences" folder. A clip named `*_tw2` in the bin is a
        fail.
      - **Timeline:** V1 and A1 are both populated (audio waveform visible),
        the speed clip is half length, and the dissolve and title are present.
      - **Effect stack:** the blur on the first clip in 06, and the volume
        fade in 05.
      - **Playback:** press play and listen for audio.
   4. If the step opened with **no dialog** and looks right, use
      **File > Save As** to save it to
      `/home/caleb/Projects/ForgeFrame/tests/fixtures/kdenlive_references/checkpack_NN_<slug>_2608_native.kdenlive`
      (for example `checkpack_02_two_clips_2608_native.kdenlive`). Do not save
      over the pack file itself.
   5. If a dialog appeared, do **not** save. Note it and move on.
5. **Hand-made reference** (most valuable). Build the same timeline natively,
   so that nothing of ours is in it:
   1. File > New, profile **HD 1080p 25 fps**.
   2. Import `kdenlive-check-pack/media/a_bars.mp4` and `b_blue.mp4`.
   3. Drag both onto V1, back to back. Their audio lands on A1.
   4. Set the second clip to **200%** speed (right-click > Change Speed).
   5. Add a **Dissolve** composition between them.
   6. Add a 1 s **Fade in** on the first clip's audio.
   7. Add **Gaussian blur** (`avfilter.gblur`) to the first clip.
   8. Add a **Title clip** on V2 at 0.5 s.
   9. Save as `tests/fixtures/kdenlive_references/checkpack_handmade_2608_native.kdenlive`.
6. Fill in the provenance file `tests/fixtures/kdenlive_references/PROVENANCE.txt`.
   Create it if it does not exist. One line per new file: name, Kdenlive
   version, date, and "saved by Caleb from check pack step NN" or "built by
   hand".
7. Commit the fixtures and the filled-in `CHECKLIST.md`. Copy it to
   `docs/testing/2026-10-XX-kdenlive-2608-gui-pass.md`, since the pack folder
   is git-ignored. Then hand Part B to the model.

---

## Part B: for the implementing model

**Read `docs/prompts/00-README.md` first.** Inputs:

- the new `*_2608_native.kdenlive` fixtures;
- `docs/testing/2026-10-XX-kdenlive-2608-gui-pass.md` (Caleb's verbatim
  dialogs).

If either is missing, **stop and report**. Do not invent GUI results.

This part changes **docs, vault pages and tests only**. It does **not** change
the serializer, parser, patcher or validator logic. Any required behaviour
change becomes a follow-up item in your report, and a new prompt file if it is
substantial (step B6).

### B1. Inventory

For each new fixture, record:

- `kdenlive:docproperties.kdenliveversion`, which must be 26.08.x;
- the profile;
- the element counts: `chain`, `producer`, `playlist`, `tractor`, and
  `main_bin` entries.

Put the table in your report.

### B2. Structural diff: our output vs native

Write a throwaway diff script in your scratch dir. Do not commit it unless
step B3 needs it as a test helper.

Compare `kdenlive-check-pack/NN_*.kdenlive` with its `checkpack_NN_*` native
save, and the pack's final step with `checkpack_handmade_2608_native`. Compare
**structure, not bytes**. At minimum, answer each of these with
evidence (file and line):

1. **Media element.** Native 25.08 writes, per media file:
   - one `<chain>` per **track placement**, with `avformat-novalidate`;
   - plus one bin `<chain>` with `avformat`.

   We write one `<producer mlt_service=avformat>` that is shared by all tracks
   and by the bin. What does 26.08 save?
2. **`kdenlive:control_uuid` on media.**
   - The E-shape tests forbid it, and the serializer comment cites
     `projectitemmodel.cpp` L1463/L1503.
   - The 25.08 native files carry it on every chain, and on the timewarp
     variant.
   - What does 26.08 save? Does Kdenlive accept our files without it (per the
     Part A dialogs)?
3. **`kdenlive:id` numbering.** Is the sequence 3 and are clips 4 and up
   (prompt 04)? Does the speed variant share the base id, with no bin entry
   (prompt 05)? Do entries carry ids (prompt 05)?
4. **`kdenlive:clip_type`.**
   - Native AV chains have `0`, and the native title has `2`.
   - Our serializer (`_clip_type`, `serializer.py` around line 110) writes `3`
     for AV and `6` for titles. It also writes `2` on the sequence, where
     native has `0`.
   - Hard rule 10 says "`clip_type=2` (not 6)" for titles, which contradicts
     the serializer. Which is right for 26.08?
5. **Audio tracks.** Native audio playlists and tractors carry
   `kdenlive:audio_track=1` (see `clip_speed_400_native.kdenlive`
   lines 159-166). Ours do not. Does it matter (dialog, or A/V track
   classification in the GUI)?
6. **`main_bin` entry ranges** and the sequence entry `out`.
7. **Timewarp** `resource` format (`4.000000:` vs `2:`) and `length`.
8. **Sequence tractor properties.** Native has `audioTarget`, `videoTarget`,
   `tracks`, `zoom` and others; ours has a subset. Also compare the
   compositing transition service: ours is `frei0r.cairoblend`, native
   26.04/25.08 is `qtblend`.
9. **Effects** (after prompt 03): the filter property set vs the native gblur.
10. **Audio fade** (after prompt 02): native fade filter vs ours.
11. Anything else Kdenlive adds or drops on save, such as `docproperties`,
    `kdenlive:file_hash` or `meta.media.*`.

For each difference, classify it as one of:

- **(R) required.** A Part A dialog, a GUI misbehaviour, or a
  Kdenlive-vs-melt render difference proves it.
- **(C) cosmetic.** Kdenlive regenerates it on load. Prove it with the
  rebuilt-playlist capture below.
- **(U) unknown.**

The rebuilt-playlist capture is the second evidence source. During
`xvfb-run -a kdenlive --render`, Kdenlive writes the playlist it rebuilt to
`/tmp/kdenlive-XXXX-1.mlt`. Copy it while the render runs; the poll loop is
in `docs/prompts/04-bin-clip-ids-and-ranges.md` step 7.

### B3. Golden-fixture tests

1. **New file `tests/unit/test_kdenlive_2608_golden.py`.** Hermetic: parse the
   fixtures with `xml.etree.ElementTree`, not the project parser, because
   native files use timecodes.
   - Define one predicate per **(R)** invariant and per invariant that a hard
     rule states (B4). Each predicate is a small function taking a root
     element.
   - Assert that every predicate holds on **every** `*_2608_native` fixture.
     This proves the rule is real.
   - Assert that every predicate holds on our serializer output for an
     equivalent model. Build it with the `tests/_testkit.py` builders, or with
     the check-pack builder under `requires_ffmpeg_ffprobe`.
   - If an (R) invariant fails on our output, mark that test
     `pytest.mark.xfail(strict=True, reason="<follow-up prompt>")`. Do not fix
     the serializer here.
2. **`tests/unit/test_serializer_eshape.py`.** `_CAND_E` points at a missing
   file, so two tests always skip. Repoint it at
   `checkpack_handmade_2608_native.kdenlive`.
   - If `assert_e_shape` then fails on the native file, the E-shape contract is
     wrong somewhere. Do not loosen the assertion silently. Record exactly
     which clause fails, mark the test `xfail(strict=True)` with that reason,
     and report it. The most likely clause is (1): "media carry no
     `control_uuid`".
3. **`tests/unit/test_serialized_xml_validation.py`.** Run
   `validate_serialized_xml` over every new native fixture. Any blocking item
   it reports on a genuine Kdenlive save is a validator false positive.
   - Assert there are none, **or** `xfail(strict=True)` with the item text,
     and list it in your report.

### B4. Rewrite the CLAUDE.md "Kdenlive XML serialization" section

1. Retarget the opening paragraph to **Kdenlive 26.x / MLT 7.x**. Name the
   verified versions: 26.04.2 (E shape), 26.08.2 (this pass).
2. Rewrite the hard rules so that **every rule cites its evidence**: a
   fixture file and element, or a Part A dialog.
   - Drop or rewrite each twin-chain-specific rule: rule 1 (the
     `control_uuid` clause), rule 2 (twin chains), and the `kextractor` and
     `monitorPosition` wording. Base them on B2 items 1-2.
   - Keep rules 3-9, rewritten where B2 shows a 26.x difference:
     - rule 4: the profile name we emit is `1920x1080_fps25`, not a canonical
       name;
     - rule 5: the sequence entry is `out=0` natively;
     - rule 7: entry ids;
     - rule 9: the id numbering from prompt 04.
   - Rule 10: fix the `clip_type` statement from B2 item 4.
   - Keep the effect rules (11-14) unless B2 contradicts them.
   - Add a rule for speed variants (prompt 05): the same id as the base,
     with no `main_bin` entry.
3. Add a short "25.x twin-chain documents" paragraph. State that the parser
   and `validate_serialized_xml` still accept them (the validator's
   `twin_shape` branch), but the serializer no longer emits them.
4. Fix the "Files" list: the reference fixture becomes the new handmade
   26.08 file, and list the golden test.
5. In "When Kdenlive rejects a file", add the rebuilt-playlist capture as a
   diagnostic step.

### B5. Vault and AGENTS.md

1. **Mark superseded, do not delete**, in `vault/wiki/`:
   - `kdenlive-25-document-shape.md`
   - `kdenlive-twin-chain-pattern.md`
   - `kdenlive-uuid-vs-control-uuid.md`, if B2 changes the `control_uuid`
     rule

   Add a banner directly under the title, for example:

   `> **Superseded 2026-10-XX** for Kdenlive 26.x -- see [[kdenlive-26-document-shape]]. Kept as the 25.x reference; the parser and validator still accept this shape.`

   Update `golden-fixture-testing.md` and `kdenlive-clip-speed-pattern.md`
   where they state the old contract.
2. **New page `vault/wiki/kdenlive-26-document-shape.md`.** The 26.x
   structural contract, in the same style as the 25.x page: an annotated XML
   skeleton plus the evidence table from B2.
3. **`AGENTS.md`.** It is a stale 101-line copy for Codex. Its Kdenlive
   section:
   - still states the 25.x contract;
   - cites deleted tests (`tests/unit/test_kdenlive_v25_shape.py`,
     `tests/integration/test_v25_kdenlive_smoke.py`);
   - names `.Codex-plugin`.

   The roadmap's "Implementation notes and follow-up" calls this the
   "AGENTS.md vs serializer contract mismatch". Resolve it as follows:
   - Replace AGENTS.md's whole "Kdenlive XML serialization" section with the
     new CLAUDE.md section, verbatim.
   - Fix the dead test-file references.
   - Leave the rest of AGENTS.md alone, except: if `.Codex-plugin` does not
     exist (`ls -a`), report it; do not rename it yourself.
4. **Roadmap.** Edit the follow-up bullet that begins "XML checks run against
   the final tree": say the contract is reconciled, with the date and the
   fixture names. Mark step 6 done.

### B6. Follow-ups

For every **(R)** difference that remains, append one line to the report.
Where it is more than a small fix, also write a new prompt file
`docs/prompts/09-<slug>.md` in the style of prompts 04 and 05, and add it to
the README order table. Number 09 is free.

The likely candidates are:

- per-placement chains (already prompt 24: cross-reference it, do not
  duplicate);
- `control_uuid`;
- `clip_type`;
- `kdenlive:audio_track`;
- the compositor service.

## Acceptance criteria

- Every `*_2608_native` fixture has a PROVENANCE line, and passes the golden
  predicates.
- No `test_serializer_eshape.py` test silently skips any more.
- The CLAUDE.md and AGENTS.md Kdenlive sections are identical, and every hard
  rule cites evidence.
- The superseded vault pages carry the banner, and the new 26.x page exists.
- The unit and full suites pass, apart from any new `xfail(strict=True)`
  items, each of which is listed with its follow-up.

## Do NOT

- Do not modify `serializer.py`, `parser.py`, `patcher_intents.py` or
  `validator.py` logic in Part B. Diagnose and write follow-ups instead.
- Do not edit or "clean" the native fixtures. They are ground truth exactly as
  Kdenlive saved them.
- Do not delete superseded vault pages or the validator's twin-shape branch.
- Do not record a GUI result you did not get from Caleb's file.
- Do not touch the dissolve (commit `38fe0e1`), audio placement (02) or
  effects (03).

## When done

Report, using the 00-README format. Also include:

- the B1 inventory table;
- the B2 difference list, with R/C/U and evidence;
- the xfails added;
- the follow-up prompts written.
