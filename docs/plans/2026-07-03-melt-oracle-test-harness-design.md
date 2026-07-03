---
date: 2026-07-03
topic: "Kdenlive MCP -- melt-as-oracle non-self-referential test harness"
author: Caleb Bennett
status: draft
tags:
  - design
  - kdenlive-mcp
  - testing
  - melt-oracle
---

# Kdenlive MCP -- melt-as-oracle Test Harness -- Design

## Summary

This design builds the external-oracle test foundation from §2 (Tier 1) of the
2026-07-03 Kdenlive MCP improvements plan: an automated harness that feeds every
project our tools write to real `melt` (MLT) and `ffprobe`, so the suite can
finally answer the one question 2,589 existing tests cannot -- *does MLT actually
accept and apply what we wrote?* It is delivered as a new pytest package
(`tests/integration/external/`) with a shared render/probe/hash helper layer, an
`external` marker, and availability-gated fixtures, touching **no runtime source
code**.

## Why this item (leverage argument)

The improvements plan contains three classes of work: correctness fixes (§1),
testing (§2), and features (§3, §5, §6). The melt-oracle harness is the single
highest-leverage item because **everything downstream is gated on it**:

- §4 sequencing step 1 (the verification spike) *is* running melt against our
  outputs, and step 1 explicitly states "Everything else is prioritized by what
  this finds." The harness is the durable, repeatable form of that spike.
- §4 step 2 says to "Land Tier 1 melt-oracle tests in the same wave so the fixes
  are provable." Without the oracle, the correctness wave -- including the
  single most important fix, filter placement (§1.1) -- cannot be shown to work.
- The §1.1 pathology is real and confirmed in code (see Evidence): tools return
  `success` while writing XML that MLT silently ignores. Our current tests pass
  anyway because the serializer is validated only by our own parser. The oracle
  is the *only* mechanism that can distinguish "reports success but MLT ignores
  it" from a genuine fix.
- Every feature wave in §3/§5/§6 mandates "melt-validated integration tests" and
  "non-self-referential, per §2" coverage. They all depend on this harness
  existing.

The filter-placement *fix* is the most important correctness change, but it is
**downstream** of the oracle: you cannot confirm the bug is real, nor that a fix
resolves it, without an external validator. Building the oracle first makes the
filter-placement fix (and every subsequent change) provable. That is maximal
leverage: one cheap piece of infrastructure that unblocks and de-risks the
entire remainder of the roadmap.

## Problem Statement

The Kdenlive MCP server exposes ~136 tools that mutate `.kdenlive` (MLT XML)
projects. The entire test suite is **self-referential**: it writes a project
with the serializer and reads it back with the parser, asserting the two agree.
Nothing ever asks MLT or Kdenlive whether the output is valid or whether an
"applied" effect actually does anything. Given the confirmed §1.1 defects (below),
a large share of the tool surface can report success while producing edits MLT
ignores -- and the suite is structurally incapable of catching it. We need an
automated oracle *outside our own code* before the correctness and feature work
can proceed with confidence.

## Verified Evidence (from the code, not the plan)

Every claim below was read directly from source at the paths/lines given.

1. **All clip effects/filters land at the MLT root, detached from clips.**
   `_apply_add_effect` (`adapters/kdenlive/patcher.py:692-743`) builds
   `<filter mlt_service="..." track="{track_index}" clip_index="{clip_index}">`
   and stores it as an `OpaqueElement(position_hint="after_tractor")`. The
   serializer appends every opaque element to the document root:
   `serializer.py:344-347` -> `elem = ET.fromstring(opaque.xml_string);
   root.append(elem)`. Nothing nests it inside the playlist `<entry>`. The
   custom `track=`/`clip_index=` attributes are not MLT vocabulary. **The whole
   effect-stack API (effect_add, the 22 wrappers, masks, keyframes, stack ops)
   depends on `_iter_clip_filters` (`patcher.py:828-871`) locating these
   root-level filters by those custom attributes -- so the stack is internally
   consistent but almost certainly a no-op in MLT.**

2. **`position_hint` is captured but never honored.** The parser sets hints like
   `"tractor"`, `"playlist:{id}"`, `"guides"` (`parser.py:95, 120, 215`), but the
   serializer's opaque loop (`serializer.py:344-351`) ignores the hint entirely
   and appends everything to root. Tractor-nested and playlist-nested content
   relocates to root on every write.

3. **Transitions emit pseudo-XML.** `_apply_add_transition`
   (`patcher.py:786-820`) writes `<transition type="crossfade" track=... left=...
   right=... duration=.../>` -- no `mlt_service`, no `a_track`/`b_track`, not
   placed inside the tractor. `_apply_add_composition` (`patcher.py:746-783`) does
   emit `mlt_service` + `a_track`/`b_track` but still lands at root via the same
   opaque path, not inside `<tractor>`.

4. **Clip speed is a bogus filter.** `_apply_set_clip_speed`
   (`patcher.py:546-581`) writes `<filter type="speed">`; MLT speed requires a
   `timewarp:` producer, so it is a no-op.

5. **Editor-authored clip effects are dropped on round-trip.** `_parse_playlist`
   (`parser.py:77-97`) iterates the *children of `<playlist>`* and only handles
   `<entry>`/`<blank>`, reading `<entry>` via attributes only
   (`parser.py:82-89`). Filters nested inside `<entry>` (how real Kdenlive stores
   clip effects) are never read -> silently lost on parse -> stripped on re-save.

6. **`parse_project` swallows errors.** On `FileNotFoundError`/`ParseError` it
   returns an empty `KdenliveProject()` (`parser.py:150-155`) rather than raising.

7. **Latest-version selection is lexicographic.** `_load_latest_project`
   (`server/tools.py:1843`) uses `sorted(working_copies.glob("*.kdenlive"))[-1]`,
   so `slug_v10` sorts before `slug_v2`.

8. **A working melt render path already exists.** `_build_melt_command`
   (`adapters/render/executor.py:165-185`) invokes
   `melt {project} -consumer avformat:{out} vcodec=... width=... height=...
   frame_rate_num=... frame_rate_den=1`. The harness reuses this invocation
   shape.

9. **Environment/config facts confirmed on this machine.** `melt`, `ffprobe`,
   `ffmpeg` are all on PATH (`/usr/bin`). `pyproject.toml` `[tool.pytest.ini_options]`
   defines only `testpaths=["tests"]` and `pythonpath=["workshop-video-brain/src"]`
   -- **no markers are registered** and there is **no `conftest.py` anywhere under
   `tests/`**. Existing skip guards elsewhere use `shutil.which(...)` (e.g.
   `tests/unit/test_render_final.py`). Every current `tests/integration/*` file is
   a parse/serialize self-referential test.

**Conclusion the harness must be built to expose:** at minimum, the effect-stack,
transition, and speed tools are expected to *fail* an external-application check
today. The harness must fail loudly on those (proving the bug) and pass once the
correctness wave lands (proving the fix) -- without any change to its own
assertions.

## Approach Selected

**Approach A -- Pure pytest external harness with a thin importable validation
helper.** New package `tests/integration/external/` marked `@pytest.mark.external`,
gated by `shutil.which` fixtures, with a shared `conftest.py` exposing
`melt_accepts()`, `render_frame()`, `frame_hash()`, and `probe()` helpers built on
`subprocess` + `melt`/`ffprobe`. Runtime source is untouched. The helper layer is
written as a small importable module so a future runtime `validate_project()`
service (Approach B) can promote it without rework.

Rationale: the plan frames this as "highest value, cheap." Approach A matches the
existing test conventions, keeps runtime code frozen (respecting this task's
"design only, no source changes" boundary and avoiding premature coupling of the
server to melt), and delivers exactly the non-self-referential oracle §2 demands.

## Architecture

```
tests/integration/external/
  conftest.py            # markers, availability fixtures, tool-path discovery
  _oracle.py             # pure helpers: melt_accepts / render_frame / frame_hash / probe
  builders.py            # tiny in-memory KdenliveProject factories (solid-color clips)
  test_melt_accepts_output.py   # parametrized over every project-writing tool
  test_render_probe.py          # clip+effect+transition+composite -> render -> ffprobe
  test_effect_visible.py        # differential frame-hash: effect changes pixels
  test_fade_luma.py             # signalstats/astats on rendered fades
  test_speed_duration.py        # ffprobe duration after clip_speed (xfail today)
  test_transition_renders.py    # mid-cut frame differs from both sources
  test_kdenlive_fixture_roundtrip.py  # real-Kdenlive fixtures -> parse/serialize/diff -> melt
  test_mcp_transport.py         # FastMCP stdio client, string-encoded-JSON params

           tool under test
                 |
        writes .kdenlive (real serializer)
                 |
                 v
   +----------- _oracle.py ------------+
   | melt_accepts(path) -> (ok,stderr) |  melt {path} -consumer null  (or 1s avformat)
   | render_frame(path,N) -> Path      |  melt {path} -consumer avformat:frame.png ...
   | frame_hash(png) -> str            |  perceptual/exact hash of decoded pixels
   | probe(media) -> dict              |  ffprobe -show_format -show_streams -of json
   +-----------------------------------+
                 |
        assert against EXTERNAL truth (exit code, pixels, container metadata)
```

External oracles used: melt exit code + stderr, decoded frame pixels, ffprobe
container/stream metadata, real-Kdenlive fixture files, and a real JSON-RPC
transport. None can pass by the parser and serializer merely agreeing.

## Components

- **`conftest.py` (harness infrastructure).** Registers the `external` marker
  (must also be added to `pyproject.toml` `[tool.pytest.ini_options].markers` so
  `-m external` works and `--strict-markers` stays clean). Provides session
  fixtures `melt_bin`, `ffprobe_bin`, `ffmpeg_bin` via `shutil.which`, and
  autouse skip logic: a test requesting `melt_bin` is `pytest.skip`-ped when melt
  is absent. Owns nothing about *what* is correct -- only tool discovery and
  gating. Does NOT own project construction or assertions.

- **`_oracle.py` (external-truth helpers).** The load-bearing module.
  - `melt_accepts(project_path, timeout=60) -> OracleResult(ok, returncode,
    stderr)`: runs `melt {path} -consumer null:` (validate-only, no output file);
    treats non-zero exit **or** known MLT error substrings in stderr (e.g.
    `"failed to load"`, `"Invalid"`, `"cannot"`) as failure. Rationale for
    stderr scanning: melt can exit 0 while emitting non-fatal load warnings; the
    plan explicitly wants "stderr errors = fail," so we classify, not just check
    the exit code.
  - `render_frame(project_path, frame, out_dir) -> Path`: renders exactly one
    frame to PNG via `melt {path} in={N} out={N} -consumer
    avformat:{out}.png`, reusing the profile-argument shape from
    `executor._build_melt_command`.
  - `frame_hash(png_path) -> str`: decodes the PNG (Pillow, already an indirect
    dep via other tooling; else `ffmpeg -i ... -f rawvideo`) and returns a hash.
    Uses an **average/perceptual hash with a Hamming-distance comparator**, not a
    byte hash, so codec-level nondeterminism doesn't cause flakes; exposes
    `frames_differ(a, b, threshold)` and `frames_similar(a, b, threshold)`.
  - `probe(media_path) -> dict`: wraps `ffprobe -v error -show_format
    -show_streams -of json`; returns duration, width, height, avg_frame_rate,
    and per-type stream counts.
  - Owns: subprocess orchestration and external-truth extraction. Does NOT own:
    knowledge of our models or tools (imports nothing from the effect stack).

- **`builders.py` (deterministic fixtures-in-code).** Small factories returning
  in-memory `KdenliveProject`s backed by MLT `color:` producers (solid colors,
  no media files needed) plus optional real generated media (ffmpeg `testsrc`)
  for motion/transition tests. Guarantees hermetic, distro-independent inputs.
  Owns test-project construction; does NOT own oracle logic.

- **Test modules.** One per row of the §2 table. Each: build project -> invoke
  the real tool/pipeline (via the in-process pipeline functions or the
  serializer path) -> assert against `_oracle.py`. They own scenario-specific
  assertions only.

- **`tests/fixtures/projects/real/` + `make_real_fixtures.md`.** Checked-in
  projects saved by *actual* Kdenlive (24.12 and 25.x) for the round-trip test,
  plus a regeneration runbook. This is the one component requiring a
  human-in-the-loop step to produce the fixtures (see Open Questions).

## Data Flow

1. A test constructs a `KdenliveProject` via `builders.py` (color producers, so
   no external media required for the acceptance tier).
2. The test applies the tool under test through the **real** code path -- either
   the pipeline function that the MCP tool calls, or `patch_project` +
   `serialize_project` -- producing a `.kdenlive` file in `tmp_path`.
3. The file is handed to `_oracle.py`:
   - Acceptance tier: `melt_accepts()` -> assert `ok`.
   - Render tier: `render_frame()`/full render -> `frame_hash()` or `probe()`.
4. Assertions compare against external truth (exit code, pixel-hash distance,
   ffprobe metadata, or a diff against a real-Kdenlive fixture).
5. Nothing persists; `tmp_path` is discarded. Generated media (testsrc clips) are
   created once per session in a session-scoped tmp dir and reused.

## Error Handling and Edge Cases

- **melt/ffprobe absent (CI without codecs, contributor laptop).** Availability
  fixtures `pytest.skip` the test with a clear reason. CI installs melt+ffmpeg so
  these run there (Tier 4); local runs skip gracefully -- same pattern as
  existing `shutil.which` guards. `-m external` selects/deselects the whole tier.
- **melt exits 0 but emits load warnings.** `melt_accepts` classifies stderr
  against a known-error substring list, not exit code alone. The substring list
  is a maintained constant with a comment; false-negative risk is called out as
  a risk below.
- **Frame-render nondeterminism across melt/codec versions.** Never assert exact
  pixel equality against checked-in goldens. Use *differential* assertions
  (effect-on vs effect-off hashes must differ; control frames must match within
  threshold) so the tests are version-robust. Thresholds are module constants.
- **Slow renders / hangs.** Every subprocess call passes an explicit `timeout`;
  the package also relies on `pytest-timeout` (added in Tier 4) as a backstop.
  Acceptance uses `-consumer null` (no encode) to stay fast; render tests cap at
  ~2 s of footage.
- **Tests that must fail today (proving the bug).** `test_speed_duration.py` and
  the effect-visible / transition-render cases are expected to fail against
  current code (§1.1). They are marked `@pytest.mark.xfail(strict=True,
  reason="§1.1 filter/speed placement -- flips to pass with the correctness
  wave")` so the suite is green now and the xfail auto-fails (alerting us) the
  moment the fix makes them pass. This is the mechanism that makes the fix
  "provable."
- **Real-Kdenlive fixtures unavailable at authoring time.** The round-trip test
  is written to `skip` (not fail) when `tests/fixtures/projects/real/` is empty,
  with a message pointing at `make_real_fixtures.md`, so the harness lands before
  the fixtures do and activates when they arrive.
- **`parse_project` swallowing errors (evidence #6) hides corruption from the
  oracle.** The round-trip test reads the fixture, asserts the parsed project is
  non-empty *before* trusting a round-trip, so a silently-empty parse surfaces as
  an assertion failure rather than a false pass.

## Test Strategy (this IS a test deliverable -- non-self-referential per §2)

The harness is the test strategy. The non-negotiable property: **no test may pass
by the parser and serializer agreeing.** Concretely, the deliverable includes
these modules (mirroring the §2 table), each bound to an external oracle:

| Module | Assertion | External oracle |
|---|---|---|
| `test_melt_accepts_output.py` | Parametrized over every project-writing tool family (clip_insert, effect_add + each wrapper family, mask_apply, composite_set, transitions_apply, clip_speed, track_mute, audio_fade): build tiny project, apply tool, `melt_accepts`. | melt exit + stderr |
| `test_render_probe.py` | Build clip+effect+transition+composite; render ~2 s; `probe`: duration ±1 frame, resolution, fps, v/a stream counts. | melt + ffprobe |
| `test_effect_visible.py` | Render frame N with vs without an effect (e.g. `frei0r.scanline0r`, tcolor); `frames_differ`. Control: no effect -> `frames_similar`. Directly tests the §1.1 filter-placement outcome. | rendered pixels |
| `test_fade_luma.py` | Apply effect_fade / audio_fade; first-frame mean luma ~0 and audio RMS ramps (ffmpeg `signalstats`/`astats`). | pixels/audio |
| `test_speed_duration.py` | clip_speed 2x on 4 s clip; ffprobe duration ~2 s. `xfail(strict)` until timewarp fix. | ffprobe |
| `test_transition_renders.py` | Two clips + transition; mid-cut frame differs from both sources. | rendered pixels |
| `test_kdenlive_fixture_roundtrip.py` | Parse real-Kdenlive fixtures -> serialize -> XML-diff (no lost elements, esp. entry-nested filters) -> `melt_accepts` the round-tripped file. | real files + melt |
| `test_mcp_transport.py` | FastMCP stdio client calls ~5 tools incl. string-encoded-JSON params (`keyframes=json.dumps(...)`). | real JSON-RPC transport |

Supporting deliverables: `_oracle.py` + `builders.py`; the `external` marker
registered in `pyproject.toml`; `make_real_fixtures.md`; and a CI note (Tier 4)
that melt+ffmpeg must be installed so these execute rather than skip.

Acceptance criteria for the harness itself:
- `uv run pytest tests/integration/external -m external` runs green on current
  `main` (bug-exposing cases are `xfail`, not failures; fixture-dependent cases
  `skip` cleanly when real fixtures are absent).
- Temporarily reverting the eventual filter-placement fix (or, as a pre-landing
  proof, pointing a probe test at a deliberately root-detached filter) causes
  `test_effect_visible.py` to fail -- demonstrating the oracle detects the §1.1
  class of bug and is not itself self-referential.
- No file under `workshop-video-brain/src/` is modified by this work.

## Risks

- **stderr classification false negatives/positives.** melt's warning vocabulary
  varies by build. Mitigation: start strict (exit code + a small curated error
  list), iterate; log full stderr on failure for triage.
- **Frame-hash flakiness.** Mitigated by perceptual hashing + Hamming thresholds
  and differential (not golden) assertions; still the most likely source of CI
  flake -- thresholds may need tuning per codec.
- **Distro MLT feature coverage.** Some frei0r/opencv/Qt modules may be missing
  on a given box; acceptance tests should `skip` (via `melt -query`) rather than
  fail when a specific service is unavailable, so the harness reflects "is this
  wired correctly" not "is this build fully featured."
- **Real-Kdenlive fixtures are a manual, versioned artifact.** They drift as
  Kdenlive's document format bumps. Mitigated by `make_real_fixtures.md` and the
  cross-version parametrization; accepted as ongoing maintenance.
- **Runtime never gains validation from this work.** By choice (Approach B
  rejected for now) the server still can't self-validate writes. Accepted:
  premature; revisit after the correctness wave. The `_oracle.py` shape keeps the
  door open.
- **CI cost/time.** Real renders are slower than unit tests. Mitigated by
  `-consumer null` acceptance, 1-frame/2 s render caps, session-scoped media
  reuse, and `pytest-timeout`.

## Out of Scope

- Any change to `patcher.py`, `serializer.py`, `parser.py`, `server/tools.py`, or
  the render executor. The §1.1/§1.2/§1.3 *fixes* are separate work this harness
  exists to validate.
- A runtime `validate_project()` service or auto-validate-on-write in the MCP
  tools (Approach B) -- deferred.
- Golden-frame snapshot testing against checked-in reference PNGs (Approach C) --
  rejected as primary.
- Property-based (hypothesis) tests, unit-conversion tables (§2 Tier 3) -- valuable
  but a different, self-contained workstream; not part of the oracle foundation.
- CI workflow authoring (§2 Tier 4) -- consumes this harness; tracked separately.
  This design only notes the marker/skip contract CI must honor.
- Smoke-script promotion and `smoke-test/` cleanup (§2 Tier 4).
- Producing the real-Kdenlive fixture *files* (a manual capture step); this design
  specifies the runbook and the test that consumes them.

## Approaches Considered

- **Approach A -- Pure pytest external harness (SELECTED).** New
  `tests/integration/external/` package + thin `_oracle.py`; runtime untouched.
  Pros: cheap, matches existing conventions, delivers the non-self-referential
  oracle immediately, no runtime coupling, honors the design-only boundary. Cons:
  duplicates a little subprocess logic the executor already has; runtime still
  can't self-validate. Chosen because it maximizes leverage per unit of risk and
  keeps the server code frozen while the correctness wave is designed.

- **Approach B -- Promote a `validate_project()` into the render adapter and have
  both tests and tools call it.** Pros: reusable, could let the server reject bad
  writes. Cons: couples the runtime server to melt availability and adds
  latency/failure modes to every write *before* the correctness fixes exist;
  larger blast radius; violates this task's no-source-change boundary. Rejected
  now, but `_oracle.py` is structured so its functions can be lifted into such a
  service later.

- **Approach C -- Golden-frame snapshot tests.** Pros: highest-fidelity "did the
  pixels come out right." Cons: brittle across melt/codec/distro versions, large
  binary artifacts in git, high maintenance, frequent false failures. Rejected as
  the primary mechanism; its robust core idea survives as *differential*
  frame-hash comparisons in `test_effect_visible.py`/`test_transition_renders.py`.

## Open Questions

- Which Pillow-vs-ffmpeg path for frame decoding in `frame_hash` (dependency
  footprint vs simplicity)? Leaning ffmpeg-only to avoid adding a dep; decide at
  implementation. Does not change the design.
- Exact perceptual-hash thresholds -- empirical, tuned during first CI runs.
- Who captures the initial real-Kdenlive fixtures and at which versions (24.12 +
  which 25.x)? Needs a human with Kdenlive installed; `make_real_fixtures.md`
  documents the procedure.

## Next Steps

- [ ] Turn this design into a Forge spec (`/forge docs/plans/2026-07-03-melt-oracle-test-harness-design.md`)
- [ ] Land `_oracle.py` + `conftest.py` + `builders.py` + the `external` marker first (infra), then the test modules.
- [ ] File the correctness-wave (§1.1) work as the consumer that flips the `xfail`s to passing.
- [ ] Capture the real-Kdenlive fixtures per `make_real_fixtures.md`.

## Empirical findings 2026-07-03

First real melt run of our outputs (melt 7.40.0, ffmpeg/ffprobe on PATH). The
harness landed green: **19 passed, 8 xfailed (strict), 1 skipped, 0 failed** in
~10 s. The evidence below drives the next (correctness) wave.

- **Root-placed clip filters are a confirmed no-op.** A solid clip rendered with
  vs without a root-level `avfilter.negate` (the exact `_build_filter_xml` +
  `insert_effect_xml` path) produced **pixel-identical** frames (mean RGB
  unchanged). The oracle is not blind to this: the control test that injects the
  *same* filter **nested inside the clip `<entry>`** flips the frame from black
  to white. So §1.1's placement pathology is real and the fix target is exactly
  "nest the filter in the entry." (`test_effect_visible.py`)
- **Transitions, clip-speed, and audio-fade emit XML melt rejects at *load*
  time**, not merely no-op renders. melt logs `failed to load transition
  "(null)"` for the pseudo-`<transition type=crossfade …>` (no `mlt_service`),
  and analogously fails to load `<filter type="speed">` / `<filter
  type="volume">` (custom `type=` attr, no `mlt_service`). These three are the
  only acceptance-tier scenarios that fail today; all are `xfail(strict)`.
  (`test_melt_accepts_output.py`)
- **2x `clip_speed` does not change duration.** A 4 s clip with a 2x speed
  filter still renders to 4.01 s (the bogus speed filter is ignored during
  render). Confirms speed needs a `timewarp:` producer, not a filter.
  (`test_speed_duration.py`)
- **The rest of the surface is structurally sound.** 12 project-writing families
  (clip_insert, effect_add + a frei0r wrapper + a param'd filter, composite_set,
  track_mute, track_visibility, audio-adjacent edits, trim/gap/split/create_track/
  guide) all load cleanly in melt, and a clip+effect+composite project renders to
  a well-formed 2 s H.264+AAC file with correct resolution/fps/stream counts. So
  the serializer's document skeleton is valid; the defects are localized to
  filter/transition **placement and vocabulary**, exactly as §1.1 predicted.
- **A gotcha for future builders:** an MLT `color` producer's `resource` must be
  the bare colour (`0xff0000ff`); prefixing it (`color:0xff0000ff`) renders solid
  black. Also every serialized project carries a `black_track` producer with
  `out=2147483646`, so a bare `-consumer null:` hangs on ~2e9 frames -- the
  harness bounds every run with `out=<frames-1>`.
