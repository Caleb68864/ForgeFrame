# Generic `avfilter` EntryFilter pattern + effect zones

The single biggest leverage point identified by the test-suite coverage audit. ~30 of the 59 KDE-test-suite `.kdenlive` files use a structurally identical shape: one `mlt_service=avfilter.<name>` filter on a single clip, varying only by parameter set. One serializer branch unblocks all of them.

## Pattern: every `avfilter.X` filter

```xml
<entry in="0" out="<frames-1>" producer="<chain>">
  <filter id="<id>">
    <property name="mlt_service">avfilter.<name></property>
    <property name="kdenlive_id">avfilter.<name></property>
    <property name="av.<param>"><value-or-keyframes></property>
    ...
    <property name="kdenlive:collapsed">0</property>
  </filter>
</entry>
```

Where `<name>` is the ffmpeg filter name (`gblur`, `boxblur`, `eq`, `colorbalance`, `huesaturation`, `chromahold`, `hsvhold`, `drawbox`, `drawgrid`, `chromashift`, `edgedetect`, `fillborders`, `fftdnoiz`, `cas`, `deband`, `grayworld`, `colorchannelmixer`, `colormatrix`, `colorspace`, `dilation`, `erosion`, `epx`, `hqx`, `chromanr`, ...).

The parameters use the `av.<param>` naming convention. Scalar params are bare values; animated params are `HH:MM:SS.mmm=value;...` keyframe strings (the same syntax `qtblend` rect uses).

## What we already implement

`PlaylistEntry.filters: list[EntryFilter]` -- our existing model already serializes the right shape. No model changes needed for `avfilter.*`. Just construct an `EntryFilter` with the right properties dict and append it.

The audit's 30 untested files are unblocked by:

```python
from workshop_video_brain.core.models.kdenlive import EntryFilter

entry.filters.append(EntryFilter(
    id="my_filter",
    properties={
        "mlt_service": "avfilter.gblur",
        "kdenlive_id": "avfilter.gblur",
        "av.sigma": "00:00:00.000=0;00:00:05.000=20",
        "kdenlive:collapsed": "0",
    },
))
```

What's NOT yet implemented as a high-level MCP wrapper:

- A generic `effect_avfilter` MCP tool that takes a service name + params dict and constructs the EntryFilter.
- Per-effect convenience tools (`effect_blur(sigma=...)`, `effect_eq(brightness=..., contrast=...)`).

These are mechanical wrappers around the EntryFilter primitive; the underlying serializer/parser path is already correct.

## Effect zones (`kdenlive:zone_in` / `kdenlive:zone_out`)

A filter can be scoped to a sub-range of its clip via `<property name="kdenlive:zone_in">` and `<property name="kdenlive:zone_out">` (entry-local frame indices). Outside the zone, the clip plays untouched. This is how Kdenlive's UI implements the "Effect zone" feature visible in the timeline header.

```xml
<filter id="brightness_zone">
  <property name="mlt_service">brightness</property>
  <property name="kdenlive_id">brightness</property>
  <property name="level">1.4</property>
  <property name="kdenlive:zone_in">30</property>
  <property name="kdenlive:zone_out">89</property>
</filter>
```

`EntryFilter.zone_in_frame` / `zone_out_frame` (added with this pattern) map directly to those properties.

## Native video fades — `brightness` filter, four critical contract bits

Video fade-from-black / fade-to-black uses an EntryFilter with `mlt_service=brightness`. Verified against the user's hand-saved `tests/fixtures/kdenlive_references/video_fade_black_native.kdenlive`. Four contract details that aren't obvious from the audio-fade pattern:

```xml
<filter id="fade_from_black" out="00:00:02.970">
  <property name="start">1</property>
  <property name="level">00:00:00.000=0;00:00:02.970=1</property>
  <property name="mlt_service">brightness</property>
  <property name="kdenlive_id">fade_from_black</property>
  <property name="alpha">1</property>
  <property name="kdenlive:collapsed">0</property>
</filter>
```

```xml
<filter id="fade_to_black" in="00:00:04.705" out="00:00:07.941">
  <property name="start">1</property>
  <property name="level">00:00:00.000=1;00:00:03.237=0</property>
  <property name="mlt_service">brightness</property>
  <property name="kdenlive_id">fade_to_black</property>
  <property name="alpha">1</property>
  <property name="kdenlive:collapsed">0</property>
</filter>
```

1. **`level` carries the keyframe string** (NOT `alpha`). The keyframe value ramps `0 → 1` for fade-from-black, `1 → 0` for fade-to-black.
2. **`alpha` is the scalar `"1"`**, not a keyframe ramp. Constant full-opacity throughout.
3. **`start=1`** is the property the UI's "Fade from Black" / "Fade to Black" toggle reads. Without it the checkbox shows unchecked even though the level keyframes still ramp brightness — the fade visually works but the UI tab is misleading.
4. **`level` keyframe times are FILTER-LOCAL**, not entry-local: they always start at `00:00:00.000` regardless of where the filter window sits inside the entry. The filter's `in`/`out` attributes position the window inside the entry; the keyframes describe what happens *within* that window.

## Implementation in this repo

- `core/models/kdenlive.py::EntryFilter.zone_in_frame` / `zone_out_frame` -- new fields.
- `adapters/kdenlive/serializer.py` -- writes `kdenlive:zone_in` / `kdenlive:zone_out` properties when the fields are non-None.
- Smoke outputs (drop into ``Video Production/tests/mcp_output/``):
  * `027-avfilter-gblur.kdenlive` -- animated gaussian blur via the generic avfilter shape.
  * `028-video-fade-from-to-black.kdenlive` -- fade-from-black at head, fade-to-black at tail (the brightness mirror of the audio-fade pattern).
  * `029-effect-zone-brightness.kdenlive` -- a brightness boost scoped to frames 30-89 of the clip.

## Sources

- KDE test suite: https://github.com/KDE/kdenlive-test-suite/tree/master/projects (search for `avfilter-*.kdenlive`).
- Specifically: `avfilter-gblur`, `avfilter-eq`, `avfilter-colorbalance`, `avfilter-chromashift`, `avfilter-fftdnoiz`, `effect-zones`.
- Test-suite coverage audit: `vault/wiki/kdenlive-test-suite-coverage-audit.md`.

## Related

- [[kdenlive-image-and-qtblend-pattern]] -- qtblend uses the same EntryFilter shape with keyframe-string params.
- [[kdenlive-audio-fade-pattern]] -- audio fades use the same shape with `volume` instead of `brightness`.
- [[kdenlive-test-suite-coverage-audit]] -- the broader gap inventory.
