# Lumakey threshold tuning for visible effect

The MLT `lumakey` filter (`mlt_service=lumakey`) generates an alpha
channel based on each pixel's luma value:

* Luma below `threshold - slope/2` → alpha = `prelevel`
* Luma above `threshold + slope/2` → alpha = `postlevel`
* In between → linear gradient

With the typical default `prelevel=0` / `postlevel=255`, this means
**dark pixels become transparent, bright pixels stay opaque**.

## The "silent no-op" failure mode

If the threshold doesn't intersect the actual luma range of the
source clip, the lumakey loads cleanly and shows in the effect panel
but does **nothing visible** — no transparency, no alpha output.
Smoke 055 hit this initially: threshold=80 with a green-screen clip
whose dominant background luma is ~182 (BT.709 of pure RGB green) and
whose darkest area (a black-suit jacket) is ~20 luma.  Result: only
the small dark-suit region became transparent, easy to miss.

**Lesson:** when adding a lumakey demo, sample the luma of the source
content first.  Threshold should sit BETWEEN the luma you want to keep
and the luma you want to drop.

## BT.709 luma quick-reference for common content

| RGB | Luma (BT.709) |
|---|---|
| Pure green `(0, 255, 0)` | 182 |
| Pure red `(255, 0, 0)` | 54 |
| Pure blue `(0, 0, 255)` | 18 |
| Caucasian skin `(180, 140, 100)` | 145 |
| Dark fabric `(20, 20, 20)` | 20 |
| White shirt `(240, 240, 240)` | 240 |

For a green-screen clip where you want to drop the green background:
threshold needs to be **above 182** -- e.g. threshold=200, slope=20
(the value smoke 055 settled on).

## When to use chroma key vs lumakey

* **Chroma key** (smoke 054) -- key by HUE.  Right tool for
  green-screen / blue-screen content.  Tolerates skin, hair, dark
  clothing without affecting them.
* **Lumakey** (smoke 055) -- key by LUMA.  Right tool for "isolate
  brights" or "isolate darks" workflows: removing a black mask,
  isolating a glowing element, dropping a bright-sky background.
  NOT a substitute for chroma key on coloured backgrounds, because
  it'll drop everything dark / bright in the subject too.

For green-screen footage in particular, prefer chroma key.  Smoke 055
uses green-screen footage just because it's the only test clip we
have with strong luma contrast -- the tuned threshold makes the demo
work, but a real workflow would use chroma key 054 for this.

## Related

- [[kdenlive-color-producer-pattern]] -- the cyan background that
  makes lumakey transparency visible
- [[kdenlive-test-suite-coverage-audit]] -- coverage status
