# Kdenlive image producers + `qtblend` transform filter

Editable Ken Burns / parallax effects on still-image clips need two pieces in the right shape: an `mlt_service=qimage` producer carrying Kdenlive's expected metadata, and a `qtblend` transform filter living *inside* the playlist `<entry>` with rect keyframes in entry-local time.

## Image producer

Reference: `tests/fixtures/kdenlive_references/image_transform_native.kdenlive` (lines 88-110).

```xml
<producer id="img_compiling" in="00:00:00.000" out="00:00:04.972">
  <property name="length">00:00:05.005</property>      <!-- HH:MM:SS.fff timecode -->
  <property name="eof">pause</property>
  <property name="resource">/abs/path/to/image.png</property>
  <property name="ttl">25</property>                    <!-- always 25 -->
  <property name="aspect_ratio">1</property>
  <property name="meta.media.progressive">1</property>
  <property name="seekable">1</property>
  <property name="format">1</property>
  <property name="meta.media.width">413</property>      <!-- actual image dims -->
  <property name="meta.media.height">360</property>
  <property name="mlt_service">qimage</property>
  <property name="kdenlive:duration">00:00:05.005</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:id">N</property>             <!-- starts at 4 -->
  <property name="kdenlive:control_uuid">{...}</property>
  <property name="kdenlive:clip_type">2</property>      <!-- NOT 5 -->
  <property name="kdenlive:file_size">28315</property>
  <property name="kdenlive:file_hash">...</property>
  <property name="kdenlive:monitorPosition">0</property>
  <property name="kdenlive:kextractor">1</property>     <!-- bin marker -->
</producer>
```

### Critical contract details

1. **`kdenlive:clip_type=2`**, not the legacy `5=Image` enum value. Kdenlive 25.x reuses 2 for kdenlivetitle and qimage producers. Setting 5 makes the bin loader reject the producer.
2. **`length` and `kdenlive:duration` are timecodes** (`HH:MM:SS.fff`), not frame counts. Mismatched format means Kdenlive can't compute the right duration on import.
3. **`ttl=25`**, **`format=1`**, and **`aspect_ratio=1`** are required for image producers. `ttl` is the slideshow loop duration; `format=1` selects the qimage colour pipeline.
4. **`kdenlive:kextractor=1`** + **`kdenlive:monitorPosition=0`** mark the producer as a bin clip. Image producers are *single-instance* (no separate timeline/bin twin like avformat chains) — one element acts as both bin entry and timeline reference. The serializer auto-adds these for `qimage`/`pixbuf` producers.
5. **`kdenlive:control_uuid` only** — no `kdenlive:uuid`. Same trap as the chain twin pattern; see [[kdenlive-uuid-vs-control-uuid]].

### Optional but recommended

- `meta.media.width`/`height`: actual pixel dimensions of the source image. Missing values make Kdenlive read the file at load time, slowing the project open.
- `kdenlive:file_size` and `kdenlive:file_hash`: bin metadata used for "where did the file go?" recovery dialogs.

## `qtblend` transform filter (Ken Burns / parallax)

Reference: `image_transform_native.kdenlive` lines 111-126.

```xml
<playlist id="<track-A>">
  <entry in="0" out="<frames-1>" producer="img_compiling">
    <property name="kdenlive:id">N</property>
    <filter id="filter6">
      <property name="rotate_center">1</property>
      <property name="mlt_service">qtblend</property>      <!-- NOT affine! -->
      <property name="kdenlive_id">qtblend</property>
      <property name="compositing">0</property>
      <property name="distort">0</property>
      <property name="rect">TC0=x y w h opacity;TC1=x y w h opacity;...</property>
      <property name="rotation">TC0=deg;TC1=deg;...</property>
      <property name="kdenlive:collapsed">0</property>
    </filter>
  </entry>
</playlist>
```

### Key facts

1. **The filter lives inside the `<entry>` element**, not at the document root and not on the playlist or tractor. The model represents this with `PlaylistEntry.filters: list[EntryFilter]`.
2. **`mlt_service=qtblend`, NOT `affine`.** Kdenlive's UI exposes the effect as "Transform" but writes it as `qtblend`. `affine` is a different effect (used for shear and 3D-style transforms).
3. **`kdenlive_id=qtblend`** matches the service name.
4. **Keyframes are in entry-local time.** Timestamps run from `00:00:00.000` (entry start) to the entry's local duration timecode — NOT the absolute sequence-frame position. Putting absolute sequence positions here causes keyframes past the first clip to fall beyond their entry's local duration, which Kdenlive clamps to one effective keyframe → animation appears broken on every clip but the first.
5. **`rect` keyframe value format**: `x y w h opacity` (space-separated, opacity is 0.0-1.0 with six decimals). The rect uses canvas coordinates; values outside `(0, 0, canvas_w, canvas_h)` mean the image extends past the visible area (i.e. zoomed in past the edge — the basis of any parallax pan).
6. **`rotation` keyframes mirror the `rect` keyframes' timestamps**, even when there's no rotation. Use `0` at every keyframe time if the clip doesn't rotate. Omitting the rotation property for transforms with rotation keyframes can confuse the editor's UI.

### Computing Ken Burns rects

For a centered zoom from `start_scale` to `end_scale` plus a drift of `(x_drift, y_drift)` pixels:

```
def rect(scale, dx, dy):
    w = canvas_w * scale
    h = canvas_h * scale
    x = (canvas_w - w) / 2 + dx
    y = (canvas_h - h) / 2 + dy
    return f"{x} {y} {w} {h} 1.0"

start = rect(start_scale, 0, 0)
end   = rect(end_scale,   x_drift, y_drift)
```

`scale > 1.0` zooms the image in beyond the canvas (negative `x`/`y` because the image is wider than the visible area). `scale < 1.0` would shrink the image inside the canvas, leaving black borders -- not what you usually want for parallax.

## Implementation in this repo

- Producer emit: `serializer.py` -- `_clip_type()` returns `2` for `qimage`; `_emit_media_element` adds `kdenlive:monitorPosition=0` and `kdenlive:kextractor=1` for image producers.
- Filter emit: `serializer.py` -- the playlist-entry block iterates `entry.filters` and writes each as a `<filter>` child of the `<entry>` element.
- Model: `core/models/kdenlive.py` -- `EntryFilter` class + `PlaylistEntry.filters: list[EntryFilter]`.
- Helpers: `tests/integration/test_v25_kdenlive_smoke_6.py` -- `_qtblend_filter()` builds an `EntryFilter` from `(frame, "x y w h opacity")` keyframe tuples; `_kenburns_rect()` computes start/end rects for zoom + drift.

## Sources

- Reference fixture: `tests/fixtures/kdenlive_references/image_transform_native.kdenlive` (the user's hand-saved 04-image-transform project).

## Related

- [[kdenlive-25-document-shape]]
- [[kdenlive-uuid-vs-control-uuid]]
- [[kdenlive-title-card-pattern]] — the title-card pattern is similar (one producer, no twin) but uses `mlt_service=kdenlivetitle` and an `xmldata` payload.
