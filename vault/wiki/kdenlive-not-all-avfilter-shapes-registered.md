# Not all `avfilter.X` shapes are registered in Kdenlive's effect UI

The generic ``avfilter.<name>`` EntryFilter shape (verified by smoke
027 gblur and dozens of others) loads cleanly in Kdenlive 25.x for
**most** ffmpeg filters -- but **not all** of them.  When Kdenlive's
effect registry doesn't have a UI definition for a particular
``avfilter.X``, the loader flags the effect as missing and removes
it on project open with the dialog:

> Clip Problems
> Type: Effect | Status: Remove
> The project contains: One removed clip

## Filters confirmed NOT registered (use a substitute)

| Wanted | Substitute | Why |
|---|---|---|
| `avfilter.crop` | `crop` (native MLT) | Kdenlive's "Crop" effect wraps native `crop` w/ top/left/bottom/right scalars, NOT avfilter.crop's av.w/av.h |
| `avfilter.curves` | `frei0r.curves` | Kdenlive's "Curves" effect wraps frei0r.curves w/ Channel + indexed control points + a `kdenlive:curve` serialised string |
| `avfilter.boxblur` | `box_blur` (native MLT, UI label "Planes Blur") | avfilter.boxblur loads but the param mapping is broken (luma_power gets stuck at 0 = no blur). Native takes plain hradius/vradius/iterations |

## Filters confirmed registered (avfilter shape works)

* `avfilter.gblur` (smoke 027)
* `avfilter.hflip` (035)
* `avfilter.colorchannelmixer` (037)
* `avfilter.negate` (038)
* `avfilter.drawbox` (039)
* `avfilter.drawgrid` (040)
* `avfilter.eq` (041)
* `avfilter.huesaturation` (042) -- but needs `av.strength=1` set explicitly, default 0 is silent no-op
* `avfilter.chromahold` (045)
* `avfilter.edgedetect` (046)

## How to recover when a smoke produces "missing effect" on load

1. Note which avfilter id failed.
2. Look up the substitute shape in upstream KDE test suite:
   * `mlt-core-video-effects.kdenlive` for native MLT filters (crop, mirror, sepia, charcoal, ...)
   * `qtblend-freeze.kdenlive` for frei0r.* filters
   * `mlt-plus-video-effects.kdenlive` for chroma/lumakey/dynamictext/timer
3. Update the smoke to use the registered substitute.

## Trap: `av.strength` silent no-op for avfilter.huesaturation

If using `avfilter.huesaturation`, ALWAYS set `av.strength=1` (or
higher).  ffmpeg's huesaturation gates ALL of hue/saturation/intensity
through `strength`, which defaults to 0 -- meaning the filter loads,
the panel shows your hue/saturation values, but the effect does
nothing visually until the user manually drags the strength slider.

## Related

- [[kdenlive-color-producer-pattern]]
- [[kdenlive-test-suite-coverage-audit]]
