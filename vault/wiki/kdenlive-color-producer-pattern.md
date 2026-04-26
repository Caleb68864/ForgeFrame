# Kdenlive `mlt_service=color` producer pattern

The MLT `color` service generates a solid-colour clip useful as a
background for layered compositing.  Verified end-to-end in
Kdenlive 25.08.3 by smokes 054 and 055 (chroma-key / lumakey demos
that layer a keyed clip over a solid background).

Reference: `tests/fixtures/kdenlive_references/qtblend_freeze_upstream_kde.kdenlive`.

## Hard rule: resource MUST be hex `0xRRGGBBAA`

Named colour strings (`"magenta"`, `"cyan"`, `"red"`, etc.) silently
render as **black** in Kdenlive 25.x even though MLT's color service
nominally accepts them.  The only format that produces the expected
colour is hex RGBA in `0xRRGGBBAA` form (NOT `#RRGGBB`).

```python
Producer(
    id="bg_color",
    resource="0xff00ffff",   # opaque magenta
    properties={
        "length": str(duration_frames),
        "eof": "pause",
        "resource": "0xff00ffff",
        "aspect_ratio": "1",
        "mlt_service": "color",
        "mlt_image_format": "rgb",       # NOT rgba (per reference)
        "seekable": "1",                  # required for bin display
        "kdenlive:clipname": "Colour Clip",
        "kdenlive:duration": "00:00:05;00",  # SMPTE-style with semicolon
    },
)
```

## Property contract (from upstream reference)

The minimum properties for a colour producer that displays correctly
in the project bin and renders the right colour during playback:

* `mlt_service=color`
* `resource=0xRRGGBBAA` (hex with alpha; same value duplicated as the
  producer's `resource` attribute and as a `<property name="resource">`
  child)
* `mlt_image_format=rgb` -- `rgba` was wrong; the reference uses `rgb`
* `aspect_ratio=1`
* `length=<frames>` -- enables Kdenlive to compute the bin clip length
* `eof=pause` (vs `continue` for the special `black_track` producer)
* `seekable=1` -- without it the bin preview can't scrub
* `kdenlive:clipname` -- shown in the bin
* `kdenlive:duration` -- shown in the bin (use semicolon between
  seconds and frames for drop-frame: `00:00:05;00`)

`kdenlive:clip_type` is auto-set to `4` by the serializer for color
generators.  The upstream reference uses `2`, but `4` does not break
playback in 25.08.3 -- it's a cosmetic mismatch only.  No action
needed unless smoke verification reveals a load-time issue.

## Common hex-RGBA values for testing

| Colour | Hex |
|---|---|
| Magenta | `0xff00ffff` |
| Cyan | `0x00ffffff` |
| Yellow | `0xffff00ff` |
| Red | `0xff0000ff` |
| Green | `0x00ff00ff` |
| Blue | `0x0000ffff` |
| White | `0xffffffff` |
| Black | `0x000000ff` |
| 50% grey | `0x808080ff` |

Last byte is alpha (`ff` = opaque).

## Why this matters

Solid-colour backgrounds are critical for verifying any
transparency-producing filter (chroma key, lumakey, mask, alpha
adjust, pip, etc.) -- without a known background colour, you can't
tell whether transparent areas are actually transparent or just
black.  Smokes 054 and 055 prove this end-to-end.

## Related

- [[kdenlive-25-document-shape]] -- top-level document structure
- [[kdenlive-test-suite-coverage-audit]] -- coverage status table
