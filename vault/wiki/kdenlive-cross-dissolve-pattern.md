# Kdenlive cross-dissolve pattern (stacked clips, no same-track support)

A cross-dissolve in Kdenlive 25.x is **always** the stacked-clips pattern: clip A on a lower video track, clip B on a higher one starting `overlap` frames before A ends, plus a `<transition mlt_service="luma" kdenlive_id="dissolve">` inside the main sequence tractor whose `in`/`out` span the overlap and whose `a_track`/`b_track` are the 1-based ordinals of the two tracks. Same-track dissolves are **not** supported at the XML level even though the UI suggests otherwise.

## The XML pattern

```xml
<!-- Inside the main sequence tractor (after the <track> declarations,
     after the auto-internal mix/qtblend transitions) -->
<transition id="dissolve_v1_v2" in="<frame>" out="<frame>">
  <property name="a_track">1</property>           <!-- 1-based ordinal -->
  <property name="b_track">3</property>           <!-- 1-based ordinal -->
  <property name="factory">loader</property>
  <property name="resource"/>
  <property name="mlt_service">luma</property>
  <property name="kdenlive_id">dissolve</property>
  <property name="softness">0</property>
  <property name="reverse">0</property>
  <property name="alpha_over">1</property>
  <property name="fix_background_alpha">1</property>
</transition>
```

## Track ordinal semantics

`a_track` and `b_track` are 1-based positions in the main sequence tractor's `<track>` list, with index 0 reserved for the black background track:

```
<track producer="black_track"/>             index 0  (always)
<track producer="tractor_track_v1"/>        index 1
<track producer="tractor_track_a1"/>        index 2
<track producer="tractor_track_v2"/>        index 3
```

**Hard rule**: `a_track < b_track`. Always. The lower-numbered track ordinal goes into `a_track`; the higher-numbered into `b_track`. This is independent of which clip is fading in vs out.

Direction (which clip is the outgoing one) is encoded by the `reverse` property:

- `reverse=0` — the default. The upper track (b_track) fades *in* over the lower track. Use when the outgoing clip is on the lower track and the incoming clip is on the upper.
- `reverse=1` — flip. The upper track (b_track) fades *out*, revealing the lower track. Use when the outgoing clip is on the upper track and the incoming clip is on the lower.

**Putting the outgoing track in `a_track` when it's the upper one** produces the warning *"Incorrect composition <id> found on track N at <frame>, compositing with track M was set to forced track."* at project-load. Kdenlive auto-corrects (the dissolve still plays), but the dialog appears every time.

## In/out frame semantics

Both attributes are absolute frame indices on the *sequence* timeline (not relative to the clips). Compute as:

```
overlap_frames    = duration of the visual fade
clip_a_end_frame  = frame at which clip A ends on its track
in_frame  = clip_a_end_frame - overlap_frames
out_frame = clip_a_end_frame - 1
```

For the upper clip B to actually overlap A, the playlist on B's track needs a leading `<blank length="(clip_a_end_frame - overlap_frames)"/>` so B starts `overlap` frames before A ends.

## Same-track dissolves are not implemented

Direct evidence from `src/transitions/transitionsrepository.cpp:113-115` (Kdenlive `master`):

```cpp
QSet<QString> TransitionsRepository::getSingleTrackTransitions()
{
    // Disabled until same track transitions is implemented
    return {QStringLiteral("slide"), QStringLiteral("dissolve"),
            QStringLiteral("wipe"),  QStringLiteral("mix")};
}
```

The function exists and lists the four transition families that *would* be single-track-capable if implemented. The return value is only consumed by `TransitionsRepository::parseType()` for UI labelling (`VideoTransition` vs `VideoComposition`). **No call site wires this into actual placement logic.** `meltBuilder.cpp` (the composition placement path) only handles cross-track compositions, validating `a_track != b_track` against `videoTracksIndexes`.

Practical consequence: even when Kdenlive's UI lets you drag a dissolve onto a single-track cut, the saved `.kdenlive` always emits the stacked-clip pattern. The single-drag UX is convenience that compiles down to the two-track XML.

## Audio crossfades

For audio tracks the same shape applies but with `mlt_service="mix"` (not `luma`) and `kdenlive_id="mix"`. Audio mix transitions also need `accepts_blanks="1"` and `sum="1"` so MLT can sum the two audio streams across the overlap.

## Implementation in this repo

- Model: `core/models/kdenlive.py::SequenceTransition`. `KdenliveProject.sequence_transitions: list[SequenceTransition]`.
- Serializer: emits each `SequenceTransition` into the main sequence tractor right after the auto-internal per-track transitions, before the audio filters.
- Smoke test: `tests/integration/test_v25_kdenlive_smoke_3.py` (single dissolve) and `test_v25_kdenlive_smoke_4.py::test_010_three_clip_dissolves` (multiple).

## Sources

- Reference: `tests/fixtures/kdenlive_references/03-Crappy hand made cross disolve.kdenlive` (lines 384-395).
- Kdenlive source: `src/transitions/transitionsrepository.cpp:113-115`, `src/timeline2/model/builders/meltBuilder.cpp:347-387`.

## Related

- [[kdenlive-25-document-shape]]
- [[kdenlive-per-track-tractor-pattern]]
