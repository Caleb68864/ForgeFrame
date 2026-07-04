# `frei0r.curves` requires ALL 15 numbered control-point properties

The `frei0r.curves` filter encodes its Bezier control points as
**numbered properties `1` through `15`**.  Kdenlive also writes a
human-readable `kdenlive:curve` string for the editor UI, but the
**renderer reads the numbered properties at render time**, NOT the
string.

If you set only the props referenced by your `kdenlive:curve` string
(e.g. `8`, `9`, `10`, `11` for two interior control points) the
remaining numbered props default to 0/uninitialised and the curve
flatlines to white -- the panel shows your curve correctly, but
playback renders a totally washed-out frame.

## What the 15 properties mean

Inferred from `qtblend-freeze.kdenlive` and other upstream test
fixtures.  Treat these as opaque -- copy verbatim from a working
upstream reference, do not try to hand-derive them.

| Prop | Role |
|---|---|
| `1`-`5` | Curve type / endpoint anchor / channel-internal flags |
| `6`-`7` | First control point (default 0,0) |
| `8`-`9` | Second control point |
| `10`-`11` | Third control point |
| `12`-`13` | Fourth control point (default 1,1) |
| `14`-`15` | Reserved / boundary |

## Failure mode

Smoke 043 first attempt: only set props `3, 4, 6, 7, 8, 9` plus a
`kdenlive:curve` string with two interior points.  Result: the
Curves effect panel showed a correct S-curve, but playback rendered
**every frame as solid white** because props `10`-`15` were unset
and the renderer interpreted them as a flat top.

## Fix

Copy ALL 15 numbered properties verbatim from the upstream
reference.  The actual curve shape is determined by props `8`-`11`
(the two interior control points); the others must be present at
their reference defaults even when "unused".

```python
properties = {
    "version": "0.4",
    "mlt_service": "frei0r.curves",
    "kdenlive_id": "frei0r.curves",
    "Channel": "0.5",
    "1": "1", "2": "0.1", "3": "0.4", "4": "1",
    "6": "0", "7": "0",
    "8": "0.136364", "9": "0.248062",
    "10": "0.909091", "11": "0.844961",
    "12": "1", "13": "1",
    "14": "0", "15": "0",
    "kdenlive:curve": "0/0;0.136364/0.248062;0.909091/0.844961;1/1;",
}
```

## General principle for frei0r control-point arrays

If a frei0r filter encodes any control-point or coordinate array
as numbered properties, you MUST set every numbered prop the
upstream reference sets, even if your "logical" curve only uses a
subset.  Numbered-property arrays are positional, not sparse.

## Related

- [[kdenlive-not-all-avfilter-shapes-registered]] -- frei0r.curves
  is the registered substitute for the unregistered avfilter.curves
- [[kdenlive-color-producer-pattern]]
