---
date: 2026-07-03
topic: "Kdenlive MCP -- Testing & Improvement Plan"
author: Caleb Bennett
status: draft
tags:
  - planning
  - kdenlive-mcp
  - testing
  - roadmap
---

# Kdenlive MCP — Testing & Improvement Note

Goal: make the workshop-video-brain MCP server a **one-stop shop for video
production in Kdenlive**. This note captures (1) correctness risks found in the
current implementation, (2) how to close the biggest testing gap — nothing today
proves a written project actually works in Kdenlive/MLT — and (3) the feature
gaps between the current ~136-tool surface and a full Kdenlive workflow.

No code was changed for this note; everything below is findings + plan.

---

## 1. Correctness risks (fix before adding features)

These are places where tools report `success` but likely produce edits that
Kdenlive/MLT ignores or that corrupt state. They undermine everything built on
top, so they come first.

### 1.1 Pseudo-XML that MLT does not understand

- **Transitions**: `_apply_add_transition` (`adapters/kdenlive/patcher.py:786-820`)
  emits `<transition type="crossfade" track=... left=... duration=.../>` — no
  `mlt_service`, no `a_track`/`b_track`, not placed inside the tractor. MLT will
  ignore it. All three `transitions_apply*` tools are affected.
- **Clip speed**: `SetClipSpeed` writes `<filter type="speed">` (patcher.py:546-581).
  MLT speed changes require a `timewarp:`/`stretch:` producer (or `timeremap`),
  not a filter. The tool is a no-op in the editor.
- **Track mute/visibility**: `SetTrackMute`/`SetTrackVisibility` emit root-level
  `<property>` elements — meaningless in MLT XML. (Should set `hide` on the
  track's tractor entry.)
- **Audio fade**: `AudioFade` emits `type="volume"` with custom attrs rather
  than a proper `volume`/`brightness` filter with keyframed `level`.
- **Effect placement**: the effect-stack machinery (effect_add, all 22 wrappers,
  masks, keyframes, stack ops) attaches filters at the **MLT root** tagged with
  custom `track=`/`clip_index=` attributes, not nested inside the playlist
  `<entry>` where Kdenlive stores clip effects. Root-level filters are not
  associated with clips by MLT — the entire elaborate stack API may not render.
  **This is the single most important thing to verify with real melt/Kdenlive.**
- **effect_fade** builds `mlt_service="affine"` with property `rect`; MLT affine
  animates `transition.rect` — property-name mismatch to verify.

### 1.2 Round-trip data loss on editor-authored projects

- `_parse_playlist` reads only `<entry>` attributes — `<filter>` children nested
  inside entries (how real Kdenlive stores clip effects) are **silently dropped**
  on round-trip. Opening a user's real project and re-saving it strips their effects.
- OpaqueElements are re-appended at MLT root; `position_hint` is captured by the
  parser but **never read by the serializer** (`serializer.py:344-351`), so
  tractor-nested content relocates to root on every write.
- Serializer regenerates deterministic UUIDs and sequential `kdenlive:id`s, which
  can desync from an existing Kdenlive document.

### 1.3 Assorted bugs

- **Lexicographic latest-version bug**: `_load_latest_project` (`server/tools.py:1838`)
  uses `sorted(glob(...))[-1]`, so `slug_v10` sorts before `slug_v2` — after v9
  the wrong file gets edited. (`render_final` uses mtime — inconsistent; pick one,
  probably numeric-suffix parse.)
- **render_final ffmpeg path broken by design**: `_build_render_command` runs
  `ffmpeg -i project.kdenlive`; ffmpeg can't demux MLT XML. Only the melt path in
  `adapters/render/executor.py` works — render_final should route through it.
- **Swallowed parse errors**: `parse_project` returns an *empty* project on
  FileNotFound/ParseError. A downstream tool can then "patch" the empty project
  and serialize it over a corrupt-but-recoverable file. Should raise / return an
  error result instead.
- **Silent no-op intents**: patcher log-and-skips bad refs (e.g. AddClip with
  unknown playlist) but the tool still writes a new version and reports success.
- **Units inconsistency**: seconds (clip_insert/trim/split/gap/audio_fade) vs
  frames (composite/mask/effect/keyframe) vs presets (transitions), with
  truncating `int(seconds*fps)` in some paths and `round()` in others, and an
  `fps or 25.0` fallback. Standardize (accept both with an explicit unit param,
  or seconds everywhere with consistent rounding) and document per tool.
- **Rotoscoping / ParamType gap** (known, from commit 7726d23): `roto-spline`
  param type missing from the `ParamType` enum → rotoscoping excluded from
  effect_catalog → `effect_stack_preset` can't save stacks containing masks.
  Currently documented only in a commit message and a script comment — belongs
  in the backlog.
- Hardcoded profile assumptions: 1920×1080@25 fallbacks, forced `progressive=1`
  / SAR 1:1, transition frame-count presets assuming ~25 fps.

---

## 2. Testing plan

Current state: 2,589 tests (107 unit files, 15 integration files), all XML-level
and self-referential — our serializer is validated by our parser. **No test ever
asks MLT or Kdenlive whether the output is valid.** The smoke scripts end with
"open in Kdenlive to verify visually." Given §1.1, that gap is where the real
risk lives.

### Tier 1 — melt as an automated oracle (highest value, cheap)

`melt` is already a runtime dependency for rendering; use it as a validator:

- **`melt project.kdenlive -consumer null`** (or render 1 second to a tmp file)
  after every integration scenario that writes a project. Non-zero exit or
  stderr errors = fail. Gate with `skipif melt missing`, same pattern as the
  existing ffmpeg guards.
- **Render-and-probe test**: one integration test that builds a small project
  (clip + effect + transition + composite), renders via the executor's melt
  path, then `ffprobe`s the output — duration, resolution, fps, stream count.
  This catches "filter written but not applied" classes of bugs that XML
  assertions can't.
- **Effect-application proof**: render a frame with and without an applied
  effect and assert the frames differ (e.g. ffmpeg `signalstats`/hash). This is
  the only automated way to prove §1.1's root-level filters actually do
  something once fixed.

### Tier 2 — real-Kdenlive fixtures and round-trip fidelity

- Add **fixtures saved by actual Kdenlive** (e.g. 24.12 and 25.x): empty
  project, project with clip effects, keyframed effect, same-track mix,
  subtitle track, multi-sequence project. Today every fixture is hand-crafted
  minimal XML (19–35 lines) with no `kdenliveversion`.
- **Round-trip fidelity tests against those fixtures**: parse → serialize →
  diff. Assert no element loss (specifically entry-nested filters, §1.2) and
  that positions are preserved. Then feed the round-tripped file to melt (Tier 1).
- **Cross-version matrix**: parametrize the round-trip suite over fixture
  versions so a Kdenlive document-format bump becomes a fixture drop-in.

### Tier 3 — protocol, property, and regression hardening

- **One real MCP-transport test**: spin up the FastMCP server over stdio with a
  client and call ~5 representative tools. Today nothing exercises JSON-RPC
  serialization of the string-encoded JSON params (`keyframes=json.dumps(...)`),
  which is exactly where an agent-facing server breaks.
- **Property-based tests (hypothesis)** for the pure layers: random intent
  sequences → patch → serialize → parse → invariants hold (well-formed XML,
  track/clip counts, in ≤ out); random keyframe strings survive parse/format
  round-trip including NTSC rates (catches the truncation-vs-round issue).
- **Unit-conversion table tests**: seconds↔frames at 23.976/25/29.97/60 fps for
  every tool that converts.

### Concrete non-self-referential test suite (proposed files)

Every test below uses an oracle **outside our own code** — melt, ffprobe,
frame pixels, or a file saved by real Kdenlive. None of them can pass by
parser/serializer agreeing with each other. New module:
`tests/integration/external/` (marked `@pytest.mark.external`, skipped when
melt/ffmpeg are absent, always run in CI).

| Test file | What it does | External oracle |
|---|---|---|
| `test_melt_accepts_output.py` | Parametrized over every project-writing tool (clip_insert, effect_add, each wrapper family, mask_apply, composite_set, transitions_apply, clip_speed, track_mute...): build a tiny project, apply the tool, run `melt out.kdenlive -consumer null`. | melt exit code + stderr |
| `test_render_probe.py` | Build clip+effect+transition+composite project, render 2 s via the executor's melt path, ffprobe the file: duration ±1 frame, resolution, fps, v/a stream count. | melt + ffprobe |
| `test_effect_visible.py` | Render frame N of the same project with and without an applied effect (e.g. `frei0r.scanline0r`, tcolor, letterb0xed); assert frame hashes differ. Also the inverse control: no effect → hashes equal. Proves filters are *attached where MLT applies them* (§1.1). | rendered pixels |
| `test_fade_luma.py` | Apply effect_fade / audio_fade; render; assert first-frame mean luma ≈ 0 and audio RMS ramps (ffmpeg `signalstats` / `astats`). | rendered pixels/audio |
| `test_speed_duration.py` | clip_speed 2× on a 4 s clip; render; ffprobe duration ≈ 2 s. Fails today (§1.1) — lands with the timewarp fix. | ffprobe |
| `test_kdenlive_fixture_roundtrip.py` | Parse fixtures **saved by real Kdenlive** (24.12, 25.x — checked into `tests/fixtures/projects/real/`), serialize, XML-diff: no lost elements (esp. entry-nested filters), guides/docproperties intact; then melt-validate the round-tripped file. | real-Kdenlive files + melt |
| `test_transition_renders.py` | Two clips + transitions_apply_between; render across the cut; assert mid-transition frame differs from both source frames (an actual blend happened). | rendered pixels |
| `test_title_renders.py` (§6) | Insert a title card; render its frame; assert frame is not solid background (text pixels present). | rendered pixels |
| `test_mcp_transport.py` | FastMCP stdio client calls ~5 representative tools end-to-end, incl. string-encoded-JSON params (`keyframes=...`). | real JSON-RPC transport |

Supporting work: a shared `render_frame(project, frame) -> Path` helper +
`frame_hash()` in `tests/integration/external/conftest.py`; a
`make_real_fixtures.md` doc describing how to regenerate the real-Kdenlive
fixtures when a new Kdenlive version ships (open Kdenlive, build the six
scenarios from Tier 2, save, copy in).

### Tier 4 — CI and smoke-test hygiene

- **No CI exists** (no `.github/`). Add a workflow: lint + `uv run pytest` on
  push; melt/ffmpeg installed in the job so Tier 1 runs, guarded tests actually
  execute instead of silently skipping (8 integration files skip when fastmcp
  missing, whole modules skip without ffmpeg).
- **Promote the smoke script** (`scripts/smoke_test_kdenlive_mcp.py`) into a
  pytest integration module with real assertions + melt validation, and add a
  cleanup/reset step — the untracked `smoke-test/` tree has 52 stale versioned
  working copies. Also note `tests/smoke-test/run_smoke_tests.py` is inside
  pytest's testpaths with `test_*` function names returning values — a latent
  collection hazard; move it or rename functions.
- Add `pytest-timeout`, and a coverage floor (pytest-cov is installed but
  unconfigured).

---

## 3. Feature gaps for "one-stop shop"

Grouped by how much they block a real end-to-end workshop-video workflow.

### High — core editing workflow blockers

- **AI subject focus & auto-zoom** ("zoom in on the guitar") — see §5 for the
  detailed design. Kdenlive/MLT's `opencv.tracker` filter plus a vision model
  makes this feasible with mostly-existing infrastructure.
- **Title clips**: `title_cards_generate` only writes guides — there is no
  on-screen text capability at all. See §6 for the detailed plan. This is the
  biggest visible gap for tutorial videos.
- **Real subtitle track**: subtitles land as SRT files in `reports/`; nothing
  attaches them to the project (`kdenlive:docproperties.subtitleFile`), no
  styling, no burn-in render option. `AddSubtitleRegion` degrades to a guide.
- **Project guides as first-class tools**: `guide_add/remove/list` on the
  project. Model + intent exist, but no tool exposes them — and modern Kdenlive
  stores guides in `kdenlive:docproperties.guides` JSON, not the legacy
  `<guide>` element the serializer writes. Markers tools currently use side-car
  JSON, disconnected from the editor.
- **Track-level audio**: volume/pan/EQ filters on tracks, audio level
  keyframing on timeline clips. All current audio tools operate on standalone
  files in `media/processed/`, disconnected from the timeline. A "one-stop
  shop" needs mixer-style control in the project itself.
- **Insert-at-time / overwrite semantics**: timeline placement is
  playlist-index only. Add place-clip-at-frame-T-on-track-N (blank padding),
  overwrite vs insert modes, and cross-track `clip_move` (currently same-track
  only).
- **Working speed control**: replace the bogus speed filter with `timewarp`
  producers; later add time-remap keyframes for speed ramps.
- **Same-track transitions (mixes)**: Kdenlive's native `mix` concept is absent
  and the current crossfade XML is invalid (§1.1). Fix transitions to emit real
  `luma`/`mix` transitions in the tractor with proper a/b tracks.

### Medium — round out production

- **Proxy wiring**: `proxy_generate` creates files but never sets
  `kdenlive:proxy` on producers, so Kdenlive doesn't use them.
- **Bin organization**: folders (`kdenlive:folderid` is always -1), clip color
  tags/renaming, zones.
- **Render upgrades**: in/out or guide-zone range rendering, audio-only export,
  two-pass, chapter export from guides (YouTube chapters pair naturally with
  the publish_* tools).
- **Stabilization (vidstab), lens correction, motion tracking
  (opencv.tracker)** wrappers — common workshop-footage needs; catalog
  infrastructure already exists for wrapper generation.
- **Keyframable effect wrappers**: generated wrappers accept static values
  only; allow passing keyframe strings through to any animatable param.
- **image_alpha mask type** (explicitly deferred in the masking spec) and
  animated/keyframed rotoscoping splines.
- **Audio channels/sample-rate project settings, vertical-video profile
  presets** (Shorts/Reels are already a target via social_* tools).

### Low / later

- Sequences & nested timelines (Kdenlive ≥23.04 multi-sequence tractors) —
  parser currently assumes a single tractor; needed eventually for opening
  users' real projects, big lift.
- Multicam.
- Reverse clip, freeze frame.
- Color management (OCIO) settings.
- `keyframe_from_markers`, `png_overlay_insert`, selective effects_copy,
  keyframe shift-on-paste (already listed as future work in the 2026-04-13
  specs).

---

## 4. Suggested sequencing

1. **Verification spike (1 day)**: run melt + real Kdenlive against outputs of
   effect_add / transitions_apply / composite_set / mask_apply. Confirms or
   refutes §1.1. Everything else is prioritized by what this finds. Add to the
   spike: `melt -query filter=opencv.tracker` and a headless tracker analysis
   attempt (§5 feasibility gate).
2. **Correctness wave**: fix filter/transition placement, speed, mute/fade XML;
   fix latest-version sort, render_final melt routing, parse-error swallowing.
   Land Tier 1 melt-oracle tests in the same wave so the fixes are provable.
3. **Fidelity wave**: real-Kdenlive fixtures + round-trip tests (Tier 2); fix
   entry-nested filter loss and position_hint. This unlocks "safe to point at a
   user's own project," which the one-stop-shop goal requires.
4. **Feature waves**: High list in §3 (titles §6 → subtitles → guides →
   track audio → insert-at-time → speed → mixes → AI subject focus §5), each
   with melt-validated integration tests. Then Medium. AI subject focus goes
   last in the wave because it depends on the correctness fixes (filter
   placement, keyframed transform) and benefits from the §6 render-frame test
   helpers.
5. **CI** can land any time after (2) — earlier is better.

---

## 5. AI subject focus & auto-zoom (detailed design)

**User story**: "Focus on the guitar in this shot and zoom in on it." An agent
should be able to name a subject in natural language and get a smooth,
tracked punch-in that follows it.

### What Kdenlive/MLT already provides

- **Motion Tracker** — the MLT `opencv.tracker` filter. Given a seed rectangle
  and an algorithm (CSRT is the accurate default; KCF/MOSSE/MIL/DaSIAM are
  faster), it tracks the rect across frames and stores the result as keyframed
  rects in its `results` property. Kdenlive's own UI offers "copy tracked data
  to Transform" — exactly the follow/zoom behavior we want, so we are
  automating an established Kdenlive workflow, not inventing one.
- **SAM2 object mask** (Kdenlive 25.04+) — AI segmentation ("mask around
  people and things"). Note: this runs as a Kdenlive *application* plugin with
  its own Python venv, not as an MLT filter, so it is **not** directly
  scriptable through our file-based integration. For mask-shaped output we
  run our own segmentation instead (see "later" below).

### Pipeline

```
subject description ("the guitar")
  │ 1. ffmpeg: extract frame(s) at the target region   [exists: adapters/ffmpeg]
  │ 2. vision model → bounding box                     [new: subject locator]
  │ 3. seed opencv.tracker, run analysis headless      [new: melt analysis run]
  │ 4. tracked rect keyframes → padded/smoothed        [new: pure pipeline fn]
  │    transform-rect keyframes (zoom + follow)
  └ 5. apply via keyframed transform on the clip       [exists: effect_keyframe_set_rect]
```

1. **Frame extraction** — existing ffmpeg adapter; grab 1–3 frames from the
   clip region the user is pointing at.
2. **Subject → bbox**. Two modes:
   - *Agent-in-the-loop* (default, zero new deps): the MCP tool returns the
     extracted frame path; the calling agent (Claude) looks at the image and
     passes the bbox back. Ship as `subject_locate_frames` (extract + return
     paths) and let the agent supply `rect` to the tracking tool.
   - *Local model* (optional extra): `ultralytics` YOLO/SAM as an opt-in
     dependency group for fully autonomous runs; open-vocabulary text prompt
     → bbox.
3. **Headless tracking**: write a temp MLT XML with the source clip +
   `opencv.tracker` (rect, algo, steps), run `melt ... -consumer null`, read
   the keyframed `results` back. **Feasibility gate**: verify melt actually
   populates `results` outside the Kdenlive GUI, and that the distro's MLT is
   built with the opencv module (`melt -query filter=opencv.tracker`). Do this
   in the §4 verification spike before committing to the feature. Fallback if
   melt can't persist results: run OpenCV tracking directly in Python
   (`opencv-python-headless`) on frames we extract — same output format,
   heavier dependency.
4. **Track → camera move** (pure function, unit-testable): pad the subject
   rect to a target composition (e.g. subject fills 60% of frame, rule-of-thirds
   placement), clamp to frame bounds, smooth (moving average / Savitzky-Golay)
   so the zoom doesn't jitter, ease in/out at the punch-in boundaries, emit an
   MLT rect keyframe string. Reuses the easing operators from
   `docs/reference/mlt/keyframe-operators.md`.
5. **Apply** via the existing keyframed-rect machinery
   (`effect_keyframe_set_scalar/rect` → `qtblend`/`transform`) — which is why
   the §1.1 filter-placement fix is a prerequisite.

### Proposed tools

- `subject_locate_frames(project_file, track, clip_index, at_seconds)` →
  extracted frame paths + clip metadata (for agent-vision mode).
- `subject_track(project_file, track, clip_index, rect, algorithm, start, end)`
  → tracked keyframe data saved to `reports/tracks/*.json`.
- `subject_zoom(project_file, track, clip_index, track_data | rect, fill=0.6,
  smoothing, ease)` → applies the keyframed transform. Composable: `rect` alone
  gives a static punch-in (works even before tracking lands).

### Later

- Mask around the subject (not just zoom): feed our own SAM/YOLO segmentation
  output in as luma-matte video via the `image_alpha` mask type — which is the
  same deferred `image_alpha` work already listed in §3 Medium; these two items
  should be designed together.
- Auto-reframe to vertical (9:16 social crops following the subject) — falls
  out of the same tracked data + a different target composition; pairs with the
  existing social_* tools.

### Tests (non-self-referential, per §2)

- Synthetic tracking fixture: ffmpeg-generate a clip of a colored square moving
  on a plain background (`testsrc`/`drawbox` filters, deterministic); track it;
  assert tracked rects follow the known path within tolerance.
- `subject_zoom` output rendered via melt; assert frame N center-crop matches
  the subject region of the source frame (the zoom actually zoomed).
- Pure-function tests for padding/clamping/smoothing at 23.976/25/30 fps.

---

## 6. Title cards: detailed plan

**Current state** (`pipelines/title_cards.py`): reads `chapter_candidate`
markers, builds `TitleCard` objects, writes `reports/title_cards.json`, and
adds `TITLE: <name>` **guides** to the project. Nothing is ever rendered on
screen. The `TitleCard` model (title + subtitle + timestamp) is a fine input
contract — keep it and give it a real visual backend.

### How Kdenlive titles work

A title is a producer with `mlt_service=kdenlivetitle` whose `xmldata`
property holds a Title XML document (`<kdenlivetitle>` root: width/height,
`<item type="QGraphicsTextItem">` with content/font/color/position/alignment,
optional background items, `duration`/`out`). Kdenlive also supports on-disk
`.kdenlivetitle` template files with `%s`-style text substitution.

### Plan

1. **Title XML builder** (`pipelines/titles.py`, pure functions):
   `build_title_xml(spec) -> str` from a `TitleSpec` model — text items (title,
   subtitle), font family/size/weight, fill + outline colors, alignment,
   position (with safe-area margins computed from the project profile, not
   hardcoded 1080p), optional background rect/color/opacity. Profile-aware:
   width/height/fps from `project.profile`.
2. **Template system**: `templates/titles/*.yaml` (mirrors the existing
   `templates/render/*.yaml` pattern) defining named styles — `chapter-card`,
   `lower-third`, `end-card`, `social-hook` — with the same two-tier
   workspace/vault storage already built for effect stack presets
   (`stack_presets` machinery is directly reusable).
3. **Producer + timeline insertion**: register the kdenlivetitle producer in
   the bin (serializer already handles producer registration /
   `kdenlive:clip_type`; titles are clip_type 2 — verify against a
   real-Kdenlive fixture) and place it on a dedicated top video track
   (`track_add` exists) at the card timestamp. Duration default 4 s,
   per-card override.
4. **Animation**: fade in/out via the existing `effect_fade` machinery once
   §1.1 is fixed; optional slide-in for lower-thirds via keyframed transform
   (same infra as §5 step 5).
5. **Rewire `title_cards_generate`**: keep marker → TitleCard generation and
   the JSON report; replace the guides-only "apply" with real title insertion
   (keep writing the guides too — they double as chapter markers for §3's
   chapter-export feature). Add `title_card_add` for one-off manual cards
   (text, style, at_seconds, duration) — not everything comes from markers.

### Proposed tools

- `title_card_add(project_file, text, subtitle?, style, at_seconds, duration,
  track?)` — single card.
- `title_cards_generate(...)` — existing tool, upgraded to insert real titles
  from markers.
- `title_style_list()` / styles honored by both, from the template tiers.

### Tests

- Unit: TitleSpec → XML (parse with ElementTree, assert items/fonts/geometry;
  safe-area math parametrized over 1080p / 4K / 9:16 vertical profiles).
- Fixture: a title saved by **real Kdenlive** in the Tier 2 fixture set; assert
  our builder's XML carries the same required structure, and round-trip
  preserves theirs.
- Rendered (per §2 table, `test_title_renders.py`): insert a card on a solid
  black clip, melt-render the card's midpoint frame, assert non-black pixels
  exist (text rendered); control frame after the card ends is black.
- melt-accepts: every title-writing tool joins the §2 parametrized
  `test_melt_accepts_output.py` list.

### Risks

- kdenlivetitle rendering requires MLT's Qt module (`melt -query
  producer=kdenlivetitle` in the verification spike).
- Font availability differs across machines — templates should default to a
  widely-available family (DejaVu Sans) and allow override.
