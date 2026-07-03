# Kdenlive 26.04 GUI bin-model rejection of serializer output

Date: 2026-07-03
Author: investigation agent (read-only; no source under `workshop-video-brain/src/` modified)
Status: root cause identified, fix specified, 3 candidate repaired files produced

## TL;DR

Our serializer emits a **legacy single-tractor MLT document** that `melt` renders
fine but Kdenlive 26.04.2's GUI bin model rejects. Three independent defects:

1. **Bin producers have no `kdenlive:control_uuid`.** Kdenlive's timeline builder
   correlates each timeline clip to its bin clip through a map keyed on
   `kdenlive:control_uuid`. Our producers carry `kdenlive:uuid` + `kdenlive:id`
   but never `kdenlive:control_uuid` -> the lookup misses -> every timeline clip
   is reported "not found in project bin" and stripped. **This is the corruption
   dialog.**
2. **Effect `kdenlive_id`s are in underscore form** (`avfilter_exposure`,
   `frei0r_glitch0r`) while Kdenlive's effect repository keys on the **dot form**
   (`avfilter.exposure`, `frei0r.glitch0r`). Effects load "broken" and get
   auto-"Fixed". Non-fatal but wrong.
3. **The one user compositing transition has no `kdenlive_id`** -> Kdenlive cannot
   resolve the composition asset -> marked "Remove".

Underlying all three: our output predates Kdenlive's **sequence-based** document
architecture. `melt` (7.40) is architecture-agnostic and so our melt oracle is
blind to every one of these.

Document `version` is **not** the problem: `1.1` is current (both the pristine
empty project and the rescue-save are `1.1`).

---

## Evidence

### Files read
- Ours: `smoke-test/.../working_copies/smoke_test_full.kdenlive`
- Rescue-save (post-recovery): `smoke_test_full_2026-07-03-A.kdenlive`
- **Pristine ground truth** (empty project saved by the user's own 26.04.2, never
  touched by our MCP): `empty_from_user.kdenlive`
- Serializer: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py` (READ-ONLY)

### The corruption message, traced to source

Kdenlive release/26.04, `src/timeline2/model/builders/meltBuilder.cpp`,
`constructTrackFromMelt(...)`:

```cpp
if (clip->parent().get_int("_kdenlive_processed") == 1) {
    binId = QString(clip->parent().get("kdenlive:id"));
} else {
    const QString clipId = clip->parent().get("kdenlive:control_uuid");
    if (binIdCorresp.find(clipId) != binIdCorresp.end()) {
        binId = binIdCorresp.at(clipId);
    }
}
// ...
m_notesLog << i18n("%1 Timeline clip (%2) without bin reference found and removed.",
                   tcInfo, clip->parent().get("id"));
m_errorMessage << i18n("Project corrupted. Clip %1 (%2) not found in project bin.",
                       clip->parent().get("id"), clipId);
```

- The correlation key on a fresh load is **`kdenlive:control_uuid`**, looked up in
  `binIdCorresp`.
- `binIdCorresp` is populated by
  `pCore->projectItemModel()->loadBinPlaylist(&tractor, binIdCorresp, ...)`
  (`src/project/projectmanager.cpp`) while reading `main_bin` — it maps each bin
  clip's `control_uuid` to its internal bin id.
- `%1` in the dialog is the producer element id (`producer0`); `%2`/`clipId` is the
  control_uuid. Our producers have **no** `kdenlive:control_uuid`, so at load MLT
  assigns each unidentified producer a **fresh** uuid — that is the source of the
  braced `{614b69ff-...}` values in the dialog, which appear nowhere in our file.
- `getClipByUrl(resource)` recovery then also fails (the bin clips were registered
  without a resolvable control_uuid), so the clip is removed. On the second open the
  user saw the "Clip Problems" recovery dialog reporting **one removed clip** plus
  the effect/transition fixes below.

The pristine `empty_from_user.kdenlive` confirms the required property: its bin
sequence clip carries `kdenlive:control_uuid` (line 120) equal to its
`kdenlive:uuid`. Real media bin clips carry it too.

### The effect-id underscore defect

`smoke_test_full.kdenlive` filters emit, e.g.:

```xml
<filter mlt_service="frei0r.glitch0r" ...>
  <property name="mlt_service">frei0r.glitch0r</property>
  <property name="kdenlive_id">frei0r_glitch0r</property>   <!-- underscore -->
```

But the installed effect metadata keys on the dot form (verified against
`/usr/share/kdenlive/effects/*.xml` on this machine — note the *filenames* use
underscores, the `id=` inside uses dots):

| our `kdenlive_id` | file | repository `id=` |
|---|---|---|
| `avfilter_exposure` | `avfilter_exposure.xml` | `avfilter.exposure` |
| `frei0r_glitch0r` | `frei0r_glitch0r.xml` | `frei0r.glitch0r` |
| `frei0r_pixeliz0r` | `frei0r_pixeliz0r.xml` | `frei0r.pixeliz0r` |
| `frei0r_rgbsplit0r` | `frei0r_rgbsplit0r.xml` | `frei0r.rgbsplit0r` |
| `frei0r_scanline0r` | `frei0r_scanline0r.xml` | `frei0r.scanline0r` |
| `rotoscoping` | `rotoscoping.xml` | `rotoscoping` (already correct) |
| `transform` (mlt_service `affine`) | — | resolved via `affine` service |

This exactly matches the "Clip Problems" dialog: **six effects "Fixed"** with
Original Path values shown in underscore form. Kdenlive resolves the asset by
`kdenlive_id`; failing that, it re-derives from `mlt_service` (correct dot form) and
marks the effect "Fixed". Root of the defect: our effect catalog/wrapper layer names
assets in underscore form (matching MCP tool names like `effect_frei0r_glitch0r`)
and that internal id leaks into the emitted `kdenlive_id`.

### The rejected transition

The single non-internal composition in our file:

```xml
<transition mlt_service="frei0r.cairoblend">
  <property name="a_track">0</property>
  <property name="b_track">1</property>
  <property name="in">0</property><property name="out">120</property>
  <property name="geometry">0/0:1920x1080:100</property>
  <property name="1">screen</property>
</transition>
```

has **no `kdenlive_id`**. Compositions are resolved by `kdenlive_id` against the
transition repository (`/usr/share/kdenlive/transitions/frei0r_cairoblend.xml`,
`id="frei0r.cairoblend"`). With no id and ambiguous track mapping in the rebuilt
sequence, Kdenlive cannot map it to a composition asset -> "Remove". (The many
`internal_added="237"` cairoblend transitions are treated as track compositors and
handled separately — they are not what was flagged.)

### Structural diff: ours vs. pristine `empty_from_user.kdenlive`

| Aspect | Ours (`smoke_test_full`) | Pristine 26.04.2 (`empty_from_user`) |
|---|---|---|
| `version` docproperty | `1.1` | `1.1` (same — not the issue) |
| root `<mlt>` | `version="7"`, no `root=` | `version="7.40.0"`, `root="..."` |
| black background | separate `<producer id="black_track">` | `producer0`, `mlt_service=color`, `kdenlive:playlistid=black_track` |
| bin clip `control_uuid` | **absent** | present (`==` uuid) |
| timeline | flat: playlists are direct tracks of a lone root `tractor0` | **sequence tractor** id=`{uuid}` w/ `kdenlive:uuid`+`control_uuid`+`producer_type=17`+`sequenceproperties.*` |
| timeline tracks | `<playlist>` per track + `_kdpair` sibling | each track is a **`<tractor>`** wrapping two `<playlist>` lanes |
| `main_bin` | entries for media only; no Sequences folder | `kdenlive:folder.-1.2=Sequences`, `kdenlive:sequenceFolder`, `opensequences`, `activetimeline`, entry -> sequence uuid |
| render root | none (nothing references `tractor0`) | `tractor4` with `kdenlive:projectTractor=1` -> sequence uuid |
| producers vs chains | `<producer>` | `<producer>`/`<chain>` (chains for AV; producer OK) |

Kdenlive tolerates a legacy single-tractor doc through an importer path
(`ProjectManager::updateTimeline`, "pre-nesting project file" branch), which is how
it managed to construct a timeline at all — but that path is exactly where the
control_uuid correlation is absent, so every clip is dropped.

---

## Version audit (task 2)

- `kdenlive --version` -> **26.04.2** (confirmed).
- `melt --version` -> **7.40.0**.
- `/usr/share/kdenlive/` present; `effects/` holds **386** definitions.
- Effect catalog was generated from 25.12.3. **No evidence of missing/moved effects**
  that would matter here — the exposure/frei0r/rotoscoping/transform assets all still
  exist. The catalog is **not stale in coverage**; the defect is that our
  catalog/wrapper id convention (underscore) is emitted verbatim as `kdenlive_id`,
  whereas the repository id is dot form. Do **not** regenerate the catalog to fix
  this; fix the emit mapping (below).
- Verdict: **version bump is unnecessary and would be wrong.** `1.1` is the current
  document version in 26.04.2.

---

## Fix spec (serializer changes)

Ground truth for the target shape is `empty_from_user.kdenlive`. Changes are ordered
minimal-first; the recommended end state is the full sequence architecture (matches
Candidate B).

### FIX-1 (required, smallest) — emit `kdenlive:control_uuid` on every bin producer
In `serialize_project`, in the producer loop (currently emits `kdenlive:uuid`,
`kdenlive:id`, `kdenlive:clip_type`, `kdenlive:folderid`), also emit:

```python
_set_prop(p_elem, "kdenlive:control_uuid", _producer_uuid(producer.id))
```

Use the **same** value as `kdenlive:uuid` (the pristine file does exactly this for
its sequence clip). Add `kdenlive:control_uuid` to `_MANAGED_PROPS`. This is the
single change that stops the clip stripping on the legacy structure (proven by
Candidate A loading in melt; user to confirm GUI).

### FIX-2 (required) — emit dot-form effect / transition `kdenlive_id`
Wherever the serializer/effect layer writes `kdenlive_id` (and the composition
`kdenlive_id`), translate the internal underscore asset id to the repository id.
Safest rule: **the `kdenlive_id` must equal the `mlt_service`** for `avfilter.*` and
`frei0r.*` effects (both are dot form and identical), except for hand-named Kdenlive
effects (`transform`->service `affine`, `rotoscoping`->`rotoscoping`) which keep
their catalog id. Practically: build a `{underscore_id: repository_id}` map from the
effect catalog's known dot-form ids, or derive `kdenlive_id = mlt_service` when the
service is `avfilter.*`/`frei0r.*`. Emit `kdenlive_id` on user compositions too
(`frei0r.cairoblend` -> `frei0r.cairoblend`).

### FIX-3 (recommended) — emit the sequence-based architecture
Convert the writer to the modern layout mirroring `empty_from_user.kdenlive`:
1. black background as `producer0` (color, `kdenlive:playlistid=black_track`) rather
   than a bare `<producer id="black_track">`.
2. Each timeline track = a `<tractor>` wrapping two `<playlist>` lanes (clips lane +
   empty lane); audio tracks get the internal `volume`/`panner`/`audiolevel` filters.
3. A **sequence tractor** whose element `id` **is** the sequence uuid, carrying
   `kdenlive:uuid`, `kdenlive:control_uuid`, `kdenlive:producer_type=17`,
   `kdenlive:clip_type=2`, `kdenlive:id`, `kdenlive:folderid=2`,
   `kdenlive:clipname`, and the `kdenlive:sequenceproperties.*` set; its tracks are
   the black producer + the track-tractors; compositing `qtblend` transitions live
   here (`internal_added=237`, `always_active=1`), not at document root.
4. `main_bin` gains `kdenlive:folder.-1.2=Sequences`, `kdenlive:sequenceFolder`,
   `kdenlive:docproperties.opensequences` + `activetimeline` (= sequence uuid), and an
   `<entry producer="{sequence-uuid}">` in addition to the media-clip entries.
5. A `<tractor kdenlive:projectTractor="1">` whose single track references the
   sequence uuid — this is the render root.

With FIX-3, timeline clips are matched via the `_kdenlive_processed`/`kdenlive:id`
path and the whole legacy-import branch is bypassed.

### Migration implications for the parser
- The parser must **read** `kdenlive:control_uuid` and round-trip it (don't drop it,
  or a re-serialize regresses FIX-1).
- The parser must recognise the **sequence tractor** (`producer_type=17` /
  `kdenlive:uuid` on a tractor) and the `projectTractor`, and not mistake the
  track-tractors for bin clips. Timeline extraction must descend into the sequence
  tractor's track-tractors' playlists rather than reading root-level playlists.
- `main_bin` entries now include a sequence-clip entry that is **not** a media
  producer — the parser must exclude it from the media/producer list.
- Effect `kdenlive_id` normalisation must be symmetric: parse dot form, keep the
  internal underscore id for MCP naming, re-emit dot form.

---

## Extending the external test suite

There is **no** pure-headless GUI bin validator, but two mechanisms close the gap:

### 1. Headless load-through `kdenlive --render` (exercises the real bin loader)
`kdenlive` exposes `--render` (confirmed: `kdenlive [options] file rendering`,
`--render  Directly render the project and exit.`). Unlike `melt`, this routes
through Kdenlive's own document/bin/sequence construction — the exact code that
strips clips. Run under a virtual display:

```
xvfb-run -a kdenlive --render <project.kdenlive> /tmp/out.mp4 2>stderr.log
```

Assert on `stderr.log` / the project's `kdenlive:documentnotes`: **fail** the test if
it contains `not found in project bin` or `without bin reference` or `Project
corrupted`. Optionally assert the rendered clip is non-black / of expected duration
(stripped clips render as gaps). Caveats to verify in CI: needs `xvfb`, a writable
`$HOME`/config, and it is slower than melt — gate it behind an integration marker.

### 2. Structural assertions against real-fixture ground truth (fast, CI-default)
Check `empty_from_user.kdenlive` into the test fixtures as the canonical 26.04.2
skeleton. For any serialized project, assert:
- every bin `<producer>`/`<chain>` referenced by a `main_bin` `<entry>` has a
  non-empty `kdenlive:control_uuid`, and every timeline clip's producer resolves to
  one of those control_uuids;
- exactly one tractor carries `kdenlive:producer_type=17` + `kdenlive:uuid`, it is
  referenced by a `main_bin` entry, and a `kdenlive:projectTractor` tractor
  references the same uuid;
- every emitted effect/transition `kdenlive_id` exists in the installed repository
  (dot form) — parse `/usr/share/kdenlive/effects|transitions/*.xml` `id=` at test
  time and assert membership;
- keep the existing `melt out=<len> -consumer null:` smoke check as a **rendering**
  gate (it catches MLT-level breakage but, as this incident proves, must not be the
  only gate).

---

## Candidate repaired files

Generator: `docs/research/2026-07-03-tutorial-effect-analysis/scratch/build_candidates.py`
Location: `smoke-test/.../working_copies/candidates/`
All three are XML-well-formed and load in `melt out=824 -consumer null:` (exit 0,
full 825-frame timeline renders, no fatal producer errors).

- **A — `smoke_test_full_candA_control_uuid.kdenlive`**
  Hypothesis: the corruption is *only* missing `kdenlive:control_uuid` + underscore
  effect ids; the legacy single-tractor structure is tolerated by 26.04's importer.
  Changes vs original: adds `kdenlive:control_uuid` to producer0/1/2, rewrites the 5
  frei0r/avfilter `kdenlive_id`s to dot form, adds `kdenlive_id` to the user
  transition. Nothing else. **melt: exit 0, 824 frames.**

- **B — `smoke_test_full_candB_full_sequence.kdenlive`** (strongest hypothesis)
  Hypothesis: 26.04 requires the full sequence-clip architecture. Rebuilt to mirror
  `empty_from_user.kdenlive`: black as `producer0`, media as producers w/
  control_uuid, two video track-tractors (2 lanes each) holding the clips, the 6
  effects (dot-form) nested in the first clip, a sequence tractor
  (`producer_type=17`, control_uuid) with `qtblend` compositors, `main_bin` with
  Sequences folder + sequence entry + opensequences/activetimeline, and a
  `projectTractor` render root. **melt: exit 0, timeline renders to frame ~820.**

- **C — `smoke_test_full_candC_seq_registered.kdenlive`** (discriminator)
  Hypothesis: sequence *registration* is enough without the nested track-tractor
  lanes. = Candidate A **plus** the legacy `tractor0` promoted in place to a
  registered sequence (element id renamed to the uuid; `producer_type=17` +
  `sequenceproperties`), a `main_bin` sequence entry + Sequences folder +
  opensequences/activetimeline, and a `projectTractor` wrapper — but the flat
  playlist-as-track structure is kept. **melt: exit 0, 824 frames.**

### How the outcomes discriminate
- **A opens clean** -> only FIX-1 + FIX-2 are needed; the sequence rearchitecture
  (FIX-3) is optional. Cheapest path.
- **A fails, C opens clean** -> sequence *registration* wiring is required (FIX-3
  items 3-5) but the nested track-tractor lanes (FIX-3 item 2) are not.
- **A & C fail, B opens clean** -> the full modern architecture (all of FIX-3) is
  mandatory.
- **all fail** -> deeper issue; re-investigate against `empty_from_user.kdenlive`
  byte-for-byte.

The user opens A, B, C in Kdenlive 26.04.2 and reports which load without the
corruption/Clip-Problems dialog; that selects the minimum serializer change set.
