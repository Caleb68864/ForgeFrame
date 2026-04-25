# Kdenlive title card pattern (`mlt_service=kdenlivetitle`)

To produce a title card the user can double-click and edit in Kdenlive's title editor (rather than a flat solid-color block), emit a `<producer mlt_service="kdenlivetitle">` carrying an `xmldata` property whose value is a `<kdenlivetitle>` document describing the text, font, and viewport. Solid color (`mlt_service=color`) clips load fine but are not editable.

## Producer shape

```xml
<producer id="title_intro" out="<frames-1>">
  <property name="mlt_service">kdenlivetitle</property>
  <property name="length"><frames></property>
  <property name="eof">pause</property>
  <property name="aspect_ratio">1</property>
  <property name="seekable">1</property>
  <property name="meta.media.progressive">1</property>
  <property name="meta.media.width"><project-width></property>
  <property name="meta.media.height"><project-height></property>
  <property name="force_reload">0</property>
  <property name="resource"></property>           <!-- empty, NOT a hex color -->
  <property name="kdenlive:clipname"><label></property>
  <property name="kdenlive:duration">HH:MM:SS;FF</property>  <!-- semicolon timecode -->
  <property name="xmldata">&lt;kdenlivetitle ...&gt;...&lt;/kdenlivetitle&gt;</property>
  <property name="kdenlive:control_uuid">{<uuid>}</property>
  <property name="kdenlive:id"><N></property>
  <property name="kdenlive:clip_type">2</property>     <!-- NOT 6 -->
  <property name="kdenlive:folderid">-1</property>
</producer>
```

## `xmldata` schema

The xmldata is a `<kdenlivetitle>` document, escaped as XML in the property value:

```xml
<kdenlivetitle LC_NUMERIC="C" duration="<frames>" height="<H>" out="<frames-1>" width="<W>">
 <item type="QGraphicsTextItem" z-index="0">
  <position x="<px>" y="<py>">
   <transform>1,0,0,0,1,0,0,0,1</transform>
  </position>
  <content alignment="4" box-height="<bh>" box-width="<bw>"
           font="Segoe UI" font-color="255,255,255,255" font-italic="0"
           font-outline="0" font-outline-color="0,0,0,255"
           font-pixel-size="72" font-underline="0" font-weight="400"
           letter-spacing="0" shadow="0;#64000000;3;3;3" tab-width="80"
           typewriter="0;2;1;0;0">Your text here</content>
 </item>
 <startviewport rect="0,0,<W>,<H>"/>
 <endviewport rect="0,0,<W>,<H>"/>
 <background color="0,0,0,0"/>     <!-- transparent background -->
</kdenlivetitle>
```

Width / height inside the `<kdenlivetitle>` document and on the `<startviewport>` / `<endviewport>` rects must match the project's profile resolution. Mismatched sizes render the title at the title's own resolution rather than the project's.

## Font must exist on the host

`font="Sans"` works on Linux and ships nowhere on Windows. Kdenlive on Windows responds to a missing font with a "Clip Problems" dialog at project-load offering to substitute. Practical defaults:

| Platform | Safe font name |
|---|---|
| Windows  | `Segoe UI` (always installed; matches Kdenlive's own UI) |
| Linux    | `DejaVu Sans` |
| macOS    | `Helvetica` |
| Cross-platform | `Arial` (most common shared name, though glyph coverage varies) |

For now the smoke-test helper defaults to `Segoe UI` since this project deploys on Windows. Cross-platform callers should pass `font=` explicitly.

## Critical contract details

1. **`mlt_service=kdenlivetitle`**, not `color`. Color clips display the chosen color; only kdenlivetitle is editable.
2. **`kdenlive:clip_type=2`**, not `6`. The legacy `definitions.h` enum (`6=Text`) is rejected by Kdenlive 25.x's bin loader.
3. **`resource=""`** (empty). The title is rendered from the `xmldata` payload, not a file resource.
4. **No `<chain>` twin.** Title producers are emitted as `<producer>` and referenced directly by `main_bin <entry>` (no `_bin` suffix). Twin chains apply to `<chain>` only.
5. **`meta.media.width` / `meta.media.height` match the project profile.** Mismatch causes the title editor to render at the wrong size.
6. **`kdenlive:duration` uses `HH:MM:SS;FF` timecode** (semicolon between seconds and the frame component, not a colon).
7. The xmldata's inner `width`/`height`/`out` and the viewport `rect`s must agree with each other and with the producer's `length`.

## Implementation

A helper `_register_kdenlivetitle()` in `tests/integration/test_v25_kdenlive_smoke_2.py` builds a centered single-text-item title for given `(label, length_frames, font_px, font)`. Pre-registers the producer in `project.producers`, after which `AddClip` with the matching `producer_id` places an entry without re-creating the producer.

## Sources

- Reference: `tests/fixtures/kdenlive_references/02-hand made multi clip and title.kdenlive` (lines 357-389) -- a Kdenlive-saved project with one editable title card on the timeline.

## Related

- [[kdenlive-25-document-shape]]
- [[kdenlive-twin-chain-pattern]] -- title producers do *not* follow this pattern; they have no bin twin.
