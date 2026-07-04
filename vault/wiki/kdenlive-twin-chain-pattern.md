# Twin chain pattern — every media file needs two `<chain>` elements

In Kdenlive 25.x's project XML, every avformat media file (mp4 / mov / mkv / wav / mp3 / ...) is emitted **twice** as `<chain>`: once as the *timeline* representation that playlist entries reference, and once as the *bin* representation that `main_bin` references. They are linked by sharing a `kdenlive:control_uuid` property.

A single shared chain causes Kdenlive to either drop the bin entry or drop the timeline clip, depending on which one it processes first. Two chains is the contract.

## The two chains

```xml
<!-- Timeline twin: referenced by <entry> children of timeline playlists -->
<chain id="myclip" out="148">
  <property name="resource">/abs/path/to/clip.mp4</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="length">149</property>
  <property name="seekable">1</property>
  <property name="audio_index">1</property>
  <property name="video_index">0</property>
  <property name="kdenlive:control_uuid">{shared-uuid}</property>
  <property name="kdenlive:id">2</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:folderid">-1</property>
</chain>

<!-- Bin twin: referenced by <entry> in main_bin -->
<chain id="myclip_bin" out="148">
  <!-- same resource / mlt_service / length / etc. -->
  <property name="kdenlive:control_uuid">{shared-uuid}</property>   <!-- SAME -->
  <property name="kdenlive:id">2</property>                          <!-- SAME -->
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:monitorPosition">0</property>             <!-- BIN ONLY -->
  <property name="kdenlive:kextractor">1</property>                  <!-- BIN ONLY -->
</chain>
```

## Critical rules

1. **Same `kdenlive:control_uuid`** on both. This is how Kdenlive maps timeline → bin (`binIdCorresp[control_uuid] = bin_id` then `binIdCorresp.count(control_uuid)` lookup; see [[kdenlive-bin-loader-source-pointers]]).
2. **Same `kdenlive:id`** on both (the small integer Kdenlive assigns sequentially per bin clip).
3. **Different element `id` attributes**. Pick a stable convention; this repo uses `<producer.id>` for the timeline twin and `<producer.id>_bin` for the bin twin.
4. **Bin twin gets `kdenlive:kextractor=1`** and `kdenlive:monitorPosition=0`. These mark it as the bin-side representation.
5. **Neither carries `kdenlive:uuid`** — see [[kdenlive-uuid-vs-control-uuid]] for why.
6. **Timeline `<entry>`s reference the timeline twin**; `main_bin <entry>` references the bin twin.

## Why two and not one

Kdenlive's bin loader builds a `control_uuid → bin_id` map by scanning `main_bin` entries. The timeline loader resolves clip references via that map. If a chain serves double duty:
- Either the bin loader registers it (and the timeline still references the same id, but Kdenlive's internal "clip use" model wants a separate Mlt::Producer instance per use),
- Or the timeline loader's `<entry>` finds the chain but Kdenlive can't construct a second `Mlt::Producer` from the same XML element.

The reference Kdenlive emits two chains. Empirically, doing the same is what makes the project open without "not found in project bin" or "modified to fix the conflicts" errors.

## Bin entry duration

The `main_bin <entry>` referencing the bin twin must have `out` equal to the clip's last frame index (i.e., `length - 1`), **not** `out="0"`. Zero-length entries get rejected as malformed.

```xml
<entry producer="myclip_bin" in="0" out="148"/>   <!-- 149-frame clip -->
```

## Implementation

- Emission: `serializer.py::_emit_media_element` is called twice per avformat producer with `is_bin=True/False`.
- Bin entry duration: same file, in the `main_bin` build block, reads `length` from the producer's properties.
- Patcher seeds the timeline producer with `length`, `seekable`, `audio_index`, etc. so the bin twin inherits them.

## Sources

- Reference fixture: `tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive` — `chain0` (timeline) and `chain1` (bin) at lines 88-147 and 270-328.

## Related

- [[kdenlive-25-document-shape]]
- [[kdenlive-uuid-vs-control-uuid]]
- [[kdenlive-bin-loader-source-pointers]]
