# Kdenlive clip-speed (timewarp) pattern

To play a clip at non-default speed in Kdenlive 25.x, the timeline references a separate `<producer mlt_service="timewarp">` whose `resource` is `"<speed>:<original_path>"`. The original chain stays in place as the bin clip; only the timeline entry is redirected to the timewarp variant. Putting a `<filter type="speed">` on the entry or as an opaque XML fragment at root level is rejected by Kdenlive's bin loader (it strips the clip with "Effect: Remove" + "One removed clip").

## The XML pattern

```xml
<!-- 1. The original chain stays as the bin clip (this is what's shown
        in the project bin).  It carries kextractor=1 and monitorPosition=0
        like any chain bin twin. -->
<chain id="<clip>_kdbin" out="<original_out>">
  <property name="resource">/abs/path/to/source.mp4</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="length">119</property>             <!-- original frames -->
  <property name="kdenlive:control_uuid">{...}</property>
  <property name="kdenlive:id">N</property>
  <property name="kdenlive:kextractor">1</property>
  <property name="kdenlive:monitorPosition">0</property>
  ...
</chain>

<!-- 2. The timewarp variant for the timeline use.  Same control_uuid +
        kdenlive:id as the bin chain so Kdenlive ties them to the same
        source.  NO kextractor / NO monitorPosition (it's not a bin clip). -->
<producer id="<clip>_speed_<token>" in="0" out="<new_out>">
  <property name="length">30</property>              <!-- original / speed -->
  <property name="eof">pause</property>
  <property name="resource">4.000000:/abs/path/to/source.mp4</property>
  <property name="mlt_service">timewarp</property>
  <property name="warp_speed">4</property>
  <property name="warp_resource">/abs/path/to/source.mp4</property>
  <property name="warp_pitch">0</property>
  <property name="seekable">1</property>
  <property name="audio_index">1</property>
  <property name="video_index">0</property>
  <property name="vstream">0</property>
  <property name="astream">0</property>
  <property name="kdenlive:control_uuid">{<same as bin chain>}</property>
  <property name="kdenlive:id">N</property>           <!-- same as bin chain -->
</producer>

<!-- 3. The timeline entry references the timewarp variant. -->
<playlist id="<track>">
  <entry in="0" out="29" producer="<clip>_speed_<token>">
    <property name="kdenlive:id">N</property>
  </entry>
</playlist>

<!-- 4. main_bin still points at the bin chain. -->
<playlist id="main_bin">
  ...
  <entry producer="<clip>_kdbin"/>
</playlist>
```

## Critical contract details

1. **`mlt_service=timewarp`** on the variant; the original stays as `avformat-novalidate`.
2. **`resource` includes the speed prefix**: `"<speed>:<original_path>"`. The numeric format Kdenlive writes is `%.6f` (e.g. `4.000000:`).
3. **`warp_speed`** — typically the integer or short float of the speed (Kdenlive emits `4`, not `4.000000`, here).
4. **`warp_resource`** — the original file path without the speed prefix.
5. **`warp_pitch=0`** — keeps the audio pitch at the original frequency. Set to `1` to let pitch follow speed (chipmunk audio at 4×).
6. **`length` = `original_length / speed`** rounded to the nearest int. For a 119-frame source at 4× → 30 frames.
7. **The variant does NOT carry `kextractor` or `monitorPosition`** — those mark a producer as a bin clip; the timewarp variant is timeline-only.
8. **Same `kdenlive:control_uuid` and `kdenlive:id` as the bin chain.** Kdenlive uses these to associate the variant with its source bin clip in the UI.
9. **Timeline `<entry>` references the timewarp variant id**, not the bin chain. The entry's `out` is `(in_point + new_count - 1)` where `new_count = original_count / speed`.

## Implementation in this repo

- `core/models/kdenlive.py::PlaylistEntry.speed` — defaults to `1.0`. Setting it triggers the timewarp variant.
- `adapters/kdenlive/serializer.py` — walks all entries, collects unique `(producer_id, speed)` pairs with `speed != 1.0`, emits one `<producer mlt_service="timewarp">` per pair, and rewrites the entry's `producer` reference at emit time.
- `adapters/kdenlive/patcher.py::_apply_set_clip_speed` — sets `entry.speed` and rescales `entry.out_point` based on the new frame count. The previous opaque-XML implementation was rejected by Kdenlive 25.x.

## Sources

- Reference fixture: `tests/fixtures/kdenlive_references/clip_speed_400_native.kdenlive` (the user's hand-saved 4× speed-up project).

## Related

- [[kdenlive-twin-chain-pattern]] — the bin/timeline twin-chain pattern; timewarp doesn't replace it, it adds a third producer for the speed-changed timeline use.
- [[kdenlive-uuid-vs-control-uuid]] — control_uuid links the timewarp variant back to the source bin clip.
