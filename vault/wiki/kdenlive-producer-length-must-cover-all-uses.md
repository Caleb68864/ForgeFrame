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

## Long-term fix

`AddClip` should probe the source file's actual duration and use
that as the producer's `length`.  Today it doesn't probe -- it just
sets length to the entry's range.  That's a latent bug for any
multi-use scenario.

## Related

- [[kdenlive-test-suite-coverage-audit]]
- [[kdenlive-color-producer-pattern]]
