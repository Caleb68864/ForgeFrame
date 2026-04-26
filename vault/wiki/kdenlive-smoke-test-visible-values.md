# Smoke tests must use parameter values that are obviously visible

A smoke test's job is to verify "this filter applies and renders".
That verification depends on the **user being able to see the
effect** when they open the file in Kdenlive.  Default / "natural"
parameter values often render correctly but invisibly, which can
not be distinguished from the filter silently no-op'ing.

## The trap

Smoke 041 (`avfilter.eq`) originally shipped with `brightness=0.08,
contrast=1.15, saturation=1.1`.  Technically correct -- a mild
warming grade.  The filter loaded, the panel showed the values, and
playback rendered the correct grade.  **But the user could not
visually tell the difference between "working" and "filter not
applied" because the change was too subtle.**

Smoke 042 (`avfilter.huesaturation`) had the same issue compounded
by the `av.strength=0` silent no-op gate -- visually it looked
identical to no filter at all, even though the gate trap was a
real bug.

## The rule

For every smoke that ships parameters, ask:

> If I open this in Kdenlive and the filter silently failed to
> apply, would the playback look different from the filter
> applying as intended?

If the answer is "no" or "barely", **bump the parameter values
aggressively** until the difference is unambiguous on a single
frame of the source clip.

## Heuristics by filter family

| Family | "Subtle" | "Visible in smoke" |
|---|---|---|
| Brightness/contrast | ±0.1 | ±0.25 to ±0.4 |
| Saturation multiplier | 1.1× | 1.5× to 2.0× |
| Hue rotation | ±15° | ±60° to ±90° |
| Blur sigma | 2-5 | 15-25 |
| Curves S-curve interior | small bumps | obvious crush + lift |
| Chromahold similarity | 0.1-0.2 | 0.4-0.5 |

## Source clip content matters

Don't pick parameter values blindly -- check what's actually IN the
source clip.  Smoke 045's chromahold originally targeted "red" on a
butterfly+flowers clip that has zero red.  Result: the smoke ran
correctly but desaturated the whole frame, which looked identical
to a generic desaturate filter.  Fixed by changing the target to
"orange" (the butterfly's actual colour).

## Why not just rely on automated assertions?

The structural tests already verify that the EntryFilter is in the
output and the properties are set.  The smoke's purpose is the
**visual / runtime** assertion -- "this actually renders the way I
expect" -- which only the user, opening the file in Kdenlive 25.x,
can verify.

A smoke that opens clean but renders invisibly defeats its own
purpose.  Aggressive parameter values are not a violation of "test
realistic conditions"; they are the test's whole point.

## Related

- [[kdenlive-smoke-verification-checklist]]
- [[kdenlive-not-all-avfilter-shapes-registered]] -- the
  `av.strength` gate is one example of a filter that looks like it
  no-ops at default parameters
