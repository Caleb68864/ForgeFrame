# MLT Keyframe Operator Reference

Source of truth for abstract-name → MLT operator character mapping.

**Authoritative source:** `mltframework/mlt` — `src/framework/mlt_animation.c`,
`keyframe_type_map[]` (array at lines 68–107 of current master; schema stable
since MLT 7.22 when `smooth_natural` / `smooth_tight` were added).

**Target MLT version:** 7.36 (matches Kdenlive 25.12).

## Wire format

Keyframes are serialized inside `<property>` elements as
`<position><op>=<value>` pairs separated by `;`. The `=` is always present;
the single character before it (if any) is the easing operator prefix. Linear
has no prefix — just `position=value`.

Example (rect, animated transform): `00:00:00.000=0 0 1920 1080 1;00:00:02.000~=100 50 1920 1080 0.5`

Position formats accepted by MLT: integer frames, `HH:MM:SS.mmm` timestamps,
seconds as float. Kdenlive projects use `HH:MM:SS.mmm`.

## Enum → operator table

Exact transcription of `keyframe_type_map[]`. Operator column is the single
character written immediately before `=` in the serialized form.

| Enum | Operator | Description |
|---|---|---|
| `mlt_keyframe_discrete` | `\|` (also `!` accepted on parse) | Step/hold — no interpolation |
| `mlt_keyframe_linear` | *(empty)* → bare `=` | Straight-line interpolation |
| `mlt_keyframe_smooth` | `~` | Deprecated alias of `smooth_loose` |
| `mlt_keyframe_smooth_loose` | `~` | Catmull-Rom spline (may overshoot) |
| `mlt_keyframe_smooth_natural` | `$` | Centripetal CR, natural slope |
| `mlt_keyframe_smooth_tight` | `-` | Centripetal CR, zero slope |
| `mlt_keyframe_sinusoidal_in` | `a` | Sine easing in |
| `mlt_keyframe_sinusoidal_out` | `b` | Sine easing out |
| `mlt_keyframe_sinusoidal_in_out` | `c` | Sine easing in-out |
| `mlt_keyframe_quadratic_in` | `d` | t² easing in |
| `mlt_keyframe_quadratic_out` | `e` | t² easing out |
| `mlt_keyframe_quadratic_in_out` | `f` | t² easing in-out |
| `mlt_keyframe_cubic_in` | `g` | t³ easing in |
| `mlt_keyframe_cubic_out` | `h` | t³ easing out |
| `mlt_keyframe_cubic_in_out` | `i` | t³ easing in-out |
| `mlt_keyframe_quartic_in` | `j` | t⁴ easing in |
| `mlt_keyframe_quartic_out` | `k` | t⁴ easing out |
| `mlt_keyframe_quartic_in_out` | `l` | t⁴ easing in-out |
| `mlt_keyframe_quintic_in` | `m` | t⁵ easing in |
| `mlt_keyframe_quintic_out` | `n` | t⁵ easing out |
| `mlt_keyframe_quintic_in_out` | `o` | t⁵ easing in-out |
| `mlt_keyframe_exponential_in` | `p` | 2^t easing in |
| `mlt_keyframe_exponential_out` | `q` | 2^t easing out |
| `mlt_keyframe_exponential_in_out` | `r` | 2^t easing in-out |
| `mlt_keyframe_circular_in` | `s` | Circular arc easing in |
| `mlt_keyframe_circular_out` | `t` | Circular arc easing out |
| `mlt_keyframe_circular_in_out` | `u` | Circular arc easing in-out |
| `mlt_keyframe_back_in` | `v` | Overshoot-back easing in |
| `mlt_keyframe_back_out` | `w` | Overshoot-back easing out |
| `mlt_keyframe_back_in_out` | `x` | Overshoot-back easing in-out |
| `mlt_keyframe_elastic_in` | `y` | Spring/elastic easing in |
| `mlt_keyframe_elastic_out` | `z` | Spring/elastic easing out |
| `mlt_keyframe_elastic_in_out` | `A` | Spring/elastic easing in-out |
| `mlt_keyframe_bounce_in` | `B` | Bounce easing in |
| `mlt_keyframe_bounce_out` | `C` | Bounce easing out |
| `mlt_keyframe_bounce_in_out` | `D` | Bounce easing in-out |

## Parser behavior

From `str_to_keyframe_type` (line ~126 of `mlt_animation.c`): parser matches
via `strncmp(s, map[i].s, 1)` — it reads the single character immediately
before `=` (`p = strchr(value, '=') - 1`).

Practical consequences:
- `linear` serializes with no prefix — just `position=value`.
- `smooth` and `smooth_loose` both map to `~`; round-tripping loses the
  `smooth` alias (they're semantically identical).
- `discrete` accepts either `|` or `!` on parse; `keyframe_type_to_str`
  emits `|`. Canonical serialized form is `|=`.
- Operators `$` and `-` (smooth_natural / smooth_tight) require MLT ≥ 7.22.
  Older MLT will fail to parse them.

## Color values

MLT animated color properties use the form `0xRRGGBBAA` (hex integer literal,
8 hex digits, alpha in low byte). Example: opaque red at frame 0 →
`00:00:00.000=0xff0000ff`.

## Value formats

- **scalar:** single number (int or float), e.g. `0.5`
- **rect:** five space-separated numbers `x y w h opacity`, e.g.
  `100 50 1920 1080 0.5`. 4-tuple `x y w h` is accepted on input; opacity
  defaults to `1`.
- **color:** `0xRRGGBBAA`.

## Version guard

If a project targets MLT < 7.22, operators `$` and `-` (smooth_natural,
smooth_tight) must be rejected with a clear error. Current ForgeFrame target
is MLT 7.36, so the guard is a cold path — implement but do not block common
paths on it.
