"""Easing curves, and baking them into dense linear keyframes (pure).

MLT animates with one operator character per keyframe (``g`` = cubic in, ...;
``pipelines/keyframes``). Baking samples an eased segment every ``step``
frames into plain linear keyframes. That gives curves MLT has no operator for
(CSS ``cubic_bezier``, ``spring``, back/elastic with custom amounts) and a
portable fallback if Kdenlive's keyframe panel mangles an operator.

The family formulas are the standard Penner set (easings.net), which is what
MLT implements; ``tests/unit/test_easing.py`` checks endpoints and midpoints
and an external render proves the baked cubic-in matches MLT's ``g``.
"""
from __future__ import annotations

import math
from typing import Any, Callable

from workshop_video_brain.edit_mcp.pipelines.keyframes import (
    VALID_EASE_FAMILIES,
    Keyframe,
    _format_color,
)

#: Names that only exist baked (no MLT operator).
BAKE_ONLY_NAMES = frozenset({"cubic_bezier", "spring"})

#: Positional order for inline parameters, e.g. "cubic_bezier(0.25,0.1,0.25,1)".
_PARAM_ORDER = {
    "cubic_bezier": ("x1", "y1", "x2", "y2"),
    "spring": ("damping", "omega"),
    "back": ("amount",),
    "elastic": ("amplitude", "period"),
}


def needs_bake(name: str) -> bool:
    """True for an easing with no MLT operator: bake-only names, or any inline parameters."""
    return name in BAKE_ONLY_NAMES or "(" in name


def _bounce_out(t: float) -> float:
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def _power(p: int):
    half = 2 ** (p - 1)
    return (lambda t: t ** p,
            lambda t: 1 - (1 - t) ** p,
            lambda t: half * t ** p if t < 0.5 else 1 - (-2 * t + 2) ** p / 2)


def _elastic(direction: str, t: float, amplitude: float = 1.0, period: float | None = None) -> float:
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    p = period if period is not None else (0.45 if direction == "in_out" else 0.3)
    a = max(1.0, amplitude)
    s = p / (2 * math.pi) * math.asin(1 / a)
    if direction == "out":
        return a * 2 ** (-10 * t) * math.sin((t - s) * 2 * math.pi / p) + 1
    if direction == "in":
        u = t - 1
        return -(a * 2 ** (10 * u) * math.sin((u - s) * 2 * math.pi / p))
    u = 2 * t - 1
    if u < 0:
        return -0.5 * a * 2 ** (10 * u) * math.sin((u - s) * 2 * math.pi / p)
    return a * 2 ** (-10 * u) * math.sin((u - s) * 2 * math.pi / p) * 0.5 + 1


def _back(direction: str, t: float, amount: float = 1.70158) -> float:
    c1, c3 = amount, amount + 1
    if direction == "in":
        return c3 * t ** 3 - c1 * t ** 2
    if direction == "out":
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
    c2 = c1 * 1.525
    if t < 0.5:
        return ((2 * t) ** 2 * ((c2 + 1) * 2 * t - c2)) / 2
    return ((2 * t - 2) ** 2 * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2


def _expo(direction: str, t: float) -> float:
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    if direction == "in":
        return 2 ** (10 * t - 10)
    if direction == "out":
        return 1 - 2 ** (-10 * t)
    return 2 ** (20 * t - 10) / 2 if t < 0.5 else (2 - 2 ** (-20 * t + 10)) / 2


_SIMPLE: dict[str, tuple[Callable[[float], float], ...]] = {
    "sine": (lambda t: 1 - math.cos(t * math.pi / 2),
             lambda t: math.sin(t * math.pi / 2),
             lambda t: -(math.cos(math.pi * t) - 1) / 2),
    "quad": _power(2),
    "cubic": _power(3),
    "quart": _power(4),
    "quint": _power(5),
    "circ": (lambda t: 1 - math.sqrt(max(0.0, 1 - t * t)),
             lambda t: math.sqrt(max(0.0, 1 - (t - 1) ** 2)),
             lambda t: (1 - math.sqrt(max(0.0, 1 - (2 * t) ** 2))) / 2 if t < 0.5
             else (math.sqrt(max(0.0, 1 - (-2 * t + 2) ** 2)) + 1) / 2),
    "bounce": (lambda t: 1 - _bounce_out(1 - t),
               _bounce_out,
               lambda t: (1 - _bounce_out(1 - 2 * t)) / 2 if t < 0.5 else (1 + _bounce_out(2 * t - 1)) / 2),
}


def _family_direction(name: str, family_default: str) -> tuple[str, str] | None:
    """('cubic', 'in') for ease_in_cubic / cubic_in / ease_in (+ default family)."""
    for direction in ("in_out", "in", "out"):
        if name == f"ease_{direction}":
            return family_default, direction
        for family in VALID_EASE_FAMILIES:
            if name in (f"ease_{direction}_{family}", f"{family}_{direction}"):
                return family, direction
    return None


def _cubic_bezier(t: float, x1: float = 0.42, y1: float = 0.0, x2: float = 0.58, y2: float = 1.0) -> float:
    def bez(u: float, p1: float, p2: float) -> float:
        return 3 * (1 - u) ** 2 * u * p1 + 3 * (1 - u) * u * u * p2 + u ** 3
    lo, hi = 0.0, 1.0
    for _ in range(30):  # x(u) is monotonic for x1, x2 in [0, 1]
        mid = (lo + hi) / 2
        if bez(mid, x1, x2) < t:
            lo = mid
        else:
            hi = mid
    return bez((lo + hi) / 2, y1, y2)


def _spring(t: float, damping: float = 6.0, omega: float = 12.0) -> float:
    def raw(x: float) -> float:
        return 1 - math.exp(-damping * x) * math.cos(omega * x)
    return raw(t) / raw(1.0)


def ease(name: str, t: float, family_default: str = "cubic", **params: Any) -> float:
    """Eased progress for normalised time *t* in [0, 1]; ``ease(name, 0) == 0`` and ``ease(name, 1) == 1``."""
    t = min(1.0, max(0.0, float(t)))
    if "(" in name and name.endswith(")"):
        # Inline parameters: "cubic_bezier(0.25,0.1,0.25,1)", "back_out(2.5)", "spring(8,20)".
        base, _, args = name[:-1].partition("(")
        values = [float(v) for v in args.split(",") if v.strip()]
        family = _family_direction(base, family_default)
        keys = _PARAM_ORDER.get(base) or (_PARAM_ORDER.get(family[0], ()) if family else ())
        if len(values) > len(keys):
            raise ValueError(f"{base} takes at most {len(keys)} parameters ({', '.join(keys) or 'none'})")
        return ease(base, t, family_default, **{**params, **dict(zip(keys, values))})
    if name == "linear":
        return t
    if name in ("hold", "discrete", "step"):
        return 1.0 if t >= 1 else 0.0
    if name.startswith("smooth"):
        raise ValueError(f"'{name}' is an MLT spline across several keyframes; it cannot be baked per segment.")
    if name == "cubic_bezier":
        return _cubic_bezier(t, **params)
    if name == "spring":
        return _spring(t, **params)
    found = _family_direction(name, family_default)
    if found is None:
        # A raw MLT operator ("g", "g=") -> its canonical name, once.
        from workshop_video_brain.edit_mcp.pipelines.keyframes import (
            _reverse_operator_lookup,
            resolve_easing,
        )
        try:
            raw = name + "=" if len(name) == 1 else name
            canonical = _reverse_operator_lookup(resolve_easing(raw, family_default))
        except ValueError:
            raise ValueError(f"unknown easing {name!r}") from None
        if canonical == name:
            raise ValueError(f"unknown easing {name!r}")
        return ease(canonical, t, family_default, **params)
    family, direction = found
    index = {"in": 0, "out": 1, "in_out": 2}[direction]
    if family == "back":
        return _back(direction, t, **params)
    if family == "elastic":
        return _elastic(direction, t, **params)
    if family == "expo":
        return _expo(direction, t)
    return _SIMPLE[family][index](t)


def _interpolate(a: Any, b: Any, y: float) -> Any:
    if isinstance(a, bool) or isinstance(b, bool):
        raise ValueError("boolean keyframe values cannot be interpolated")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return round(a + (b - a) * y, 4)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        pa, pb = list(a) + [1.0] * (5 - len(a)), list(b) + [1.0] * (5 - len(b))
        if len(a) not in (4, 5) or len(b) not in (4, 5):
            raise ValueError("rect keyframes need 4 or 5 numbers")
        return [round(x + (z - x) * y, 4) for x, z in zip(pa, pb)]
    if isinstance(a, str) and isinstance(b, str):
        ca, cb = int(_format_color(a), 16), int(_format_color(b), 16)
        channels = []
        for shift in (24, 16, 8, 0):
            x, z = (ca >> shift) & 0xFF, (cb >> shift) & 0xFF
            channels.append(max(0, min(255, round(x + (z - x) * y))))
        return "0x" + "".join(f"{c:02x}" for c in channels)
    raise ValueError(f"cannot interpolate keyframe values {a!r} and {b!r}")


def bake_keyframes(
    keyframes: list[Keyframe],
    step: int = 1,
    params: dict | None = None,
    max_keyframes: int = 3000,
    family_default: str = "cubic",
) -> list[Keyframe]:
    """Every eased segment sampled into linear keyframes, every *step* frames.

    The original keyframes stay exactly (as ``linear``); linear segments get no
    samples. ``params`` go to the easing (``cubic_bezier`` handles, ``amount``...).
    """
    if step < 1:
        raise ValueError(f"bake step must be >= 1 frame (got {step})")
    params = params or {}
    ordered = sorted(keyframes, key=lambda k: k.frame)
    out: list[Keyframe] = []
    for a, b in zip(ordered, ordered[1:]):
        out.append(Keyframe(frame=a.frame, value=a.value, easing="linear"))
        if a.easing in ("linear", "") or b.frame - a.frame < 2:
            continue
        span = b.frame - a.frame
        frames = list(range(a.frame + step, b.frame, step))
        if a.easing in ("hold", "discrete", "step") and frames[-1:] != [b.frame - 1]:
            frames.append(b.frame - 1)  # hold right up to the next keyframe
        for frame in frames:
            y = ease(a.easing, (frame - a.frame) / span, family_default, **params)
            out.append(Keyframe(frame=frame, value=_interpolate(a.value, b.value, y), easing="linear"))
        if len(out) > max_keyframes:
            raise ValueError(f"baking makes more than {max_keyframes} keyframes; use a larger bake_step")
    if ordered:
        last = ordered[-1]
        out.append(Keyframe(frame=last.frame, value=last.value, easing="linear"))
    if len(out) > max_keyframes:
        raise ValueError(f"baking makes more than {max_keyframes} keyframes; use a larger bake_step")
    return out
