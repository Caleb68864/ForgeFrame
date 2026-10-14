# Producer `length` must cover every entry's in/out range

When the same media producer is referenced by multiple playlist
entries with different `in`/`out` ranges (e.g. an audio-mix
crossfade that uses the SAME source music at different in-points
for clip A and clip B), the producer's `length` property MUST be
≥ the maximum out-point used by any entry referencing it.

## The silent failure mode

Kdenlive's project loader treats out-of-range entries as broken and
**removes them**, then surfaces a "Clip with missing mix found and
removed" warning in the Project Notes tab.  The clip vanishes from
the timeline, the mix transition is silently dropped, and only the
remaining clip plays back.

Smoke 047 hit this:

* Music producer `length=119` (set by `AddClip` from the first
  entry's range, 0..118)
* kdpair sub-playlist B entry references the same producer with
  `in=299 out=417` for the second clip in the mix
* On load: `299 > 119` → entry rejected → mix removed → user sees
  a single clip, no crossfade, no error in the main UI

## How to fix

Override the producer's `length` after `AddClip` creates it:

```python
project = patch_project(project, [AddClip(...)])
producer = next(p for p in project.producers if p.id == "music_a")
producer.properties["length"] = "6300"  # cover the full media file
```

## When this matters

* **Same-track audio crossfade** (smoke 047) -- both sides of the
  mix reference the same source at different in-points
* **Speed ramps** -- the timewarp variant producer needs length
  covering the full retimed duration
* **Multi-region selects** -- if the same source is used for
  multiple non-overlapping selects on the timeline at different
  in-points, the producer length must reach the largest out-point
  across all uses

For most smokes one entry per producer is fine because `AddClip`'s
default length (= entry duration) is sufficient.  This is only a
problem when a single producer is reused with different ranges.

## Central enforcement

The serializer now enforces this centrally with `_effective_length`: it takes
the maximum of a plain integer declared length and the largest `out_point + 1`
across every playlist use of that producer. This covers builders that do not
set a length themselves and prevents a later use from exceeding the producer.

`clip_insert` also records the probed media duration as `producer_length` in
project-profile frames. Its in/out conversion uses the project FPS, since MLT
producer frame ranges are expressed in the project timebase.

## Related

- [[kdenlive-test-suite-coverage-audit]]
- [[kdenlive-color-producer-pattern]]
