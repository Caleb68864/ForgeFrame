"""Helpers for the preset-bundle MCP tools (Sub-Spec 2).

Three presets are built on top of these helpers:

* ``effect_glitch_stack`` -- a five-filter stack.
* ``effect_fade`` -- keyframed opacity fade via the ``affine``/``transform``
  filter's ``rect`` property.
* ``flash_cut_montage`` -- splits a clip into ``n`` roughly equal pieces and
  stamps each with a directional-blur filter (plus optional alternating
  ``avfilter.negate``).

This module is pure logic: no XML I/O, no MCP decorators, no filesystem.

Notes on the glitch stack
-------------------------

The original spec called for ``frei0r.exposer`` as the 5th filter; that MLT
service is not present in the shipped catalog, so per the phase-spec
escalation we substitute ``avfilter.exposure``.
"""
from __future__ import annotations

from typing import Any

from .keyframes import Keyframe


# Ordered 5-tuple -- the canonical glitch stack order.
GLITCH_SERVICES: tuple[str, ...] = (
    "frei0r.pixeliz0r",
    "frei0r.glitch0r",
    "frei0r.rgbsplit0r",
    "frei0r.scanline0r",
    "avfilter.exposure",
)


def glitch_stack_params(intensity: float) -> list[tuple[str, dict[str, str]]]:
    """Return a list of ``(mlt_service, property_dict)`` tuples for the stack.

    ``intensity`` is in ``[0.0, 1.0]`` and scales each filter's primary
    parameter. Specifically:

    * ``frei0r.pixeliz0r`` -- ``0`` and ``1`` (Block Width/Height) both scale
      linearly in ``[0.02, 0.22]``.
    * ``frei0r.glitch0r`` -- ``0`` (Glitch Frequency) scales in ``[0.0, 1.0]``
      and ``3`` (Color Glitching Intensity) in ``[0.0, 1.0]``.
    * ``frei0r.rgbsplit0r`` -- horizontal/vertical split distance (``1`` and
      ``0``) scales in ``[0.5, 0.7]`` around the default 0.5.
    * ``frei0r.scanline0r`` -- has no tuneable params in catalog so we pass
      an empty dict.
    * ``avfilter.exposure`` -- ``av.exposure`` scales in ``[0.0, 1.5]``.

    Returns a list (not a dict) so that insertion order is preserved and
    matches ``GLITCH_SERVICES``.
    """
    if not isinstance(intensity, (int, float)) or isinstance(intensity, bool):
        raise ValueError(f"intensity must be numeric in [0.0, 1.0]; got {intensity!r}")
    if intensity < 0.0 or intensity > 1.0:
        raise ValueError(f"intensity must be in [0.0, 1.0]; got {intensity}")
    i = float(intensity)

    pix_block = f"{0.02 + i * 0.20:.4f}"
    glitch_freq = f"{i:.4f}"
    glitch_color = f"{i:.4f}"
    split = f"{0.5 + i * 0.20:.4f}"
    exposure = f"{i * 1.5:.4f}"

    return [
        ("frei0r.pixeliz0r", {"0": pix_block, "1": pix_block}),
        ("frei0r.glitch0r", {"0": glitch_freq, "3": glitch_color}),
        ("frei0r.rgbsplit0r", {"1": split, "0": split}),
        ("frei0r.scanline0r", {}),
        ("avfilter.exposure", {"av.exposure": exposure}),
    ]


def build_fade_keyframes(
    fade_in_frames: int,
    fade_out_frames: int,
    clip_duration_frames: int,
    fps: float,
    easing: str = "ease_in_out",
) -> list[Keyframe]:
    """Return the opacity keyframes for a ``transform`` filter's ``rect`` prop.

    The rect is always ``0 0 W H opacity``; only the 5th (opacity) value is
    animated. Emits 2-4 keyframes depending on which fades are non-zero:

    * ``fade_in`` only -> 2 keyframes: ``(0, 0)`` and ``(fade_in, 1)``.
    * ``fade_out`` only -> 2 keyframes: ``(total - fade_out, 1)`` and
      ``(total - 1, 0)``.
    * both -> 4 keyframes.

    ``fps`` is currently unused by this helper (callers keep the canonical
    rect size 0 0 W H outside). It is accepted so the signature mirrors other
    helpers that may become fps-sensitive later.

    Parameters
    ----------
    fade_in_frames: non-negative int.
    fade_out_frames: non-negative int.
    clip_duration_frames: clip length in frames. Must be > 0.
    fps: accepted but not consumed here.
    easing: passed through to ``Keyframe.easing``. Callers should pre-resolve
        to a name acceptable to ``resolve_easing``.

    Raises
    ------
    ValueError: on invalid fade frames / duration.
    """
    if fade_in_frames < 0 or fade_out_frames < 0:
        raise ValueError(
            f"fade_in_frames and fade_out_frames must be >= 0; "
            f"got {fade_in_frames}, {fade_out_frames}"
        )
    if fade_in_frames + fade_out_frames == 0:
        raise ValueError("at least one of fade_in_frames / fade_out_frames must be > 0")
    if clip_duration_frames <= 0:
        raise ValueError(
            f"clip_duration_frames must be > 0; got {clip_duration_frames}"
        )
    if fade_in_frames + fade_out_frames > clip_duration_frames:
        raise ValueError(
            f"fade_in_frames + fade_out_frames ({fade_in_frames + fade_out_frames}) "
            f"exceeds clip_duration_frames ({clip_duration_frames})"
        )

    # Rect: 0 0 0 0 <opacity> -- dimensions are filled in by the caller
    # (they know width/height). Here we only emit opacity; the caller builds
    # the full 5-tuple.
    out: list[Keyframe] = []
    last_frame = clip_duration_frames - 1

    def _rect(opacity: float) -> tuple[int, int, int, int, float]:
        # Placeholder dimensions; the preset caller fills in W/H via the
        # keyframe values directly (see `_rect_values_for_fade` below).
        return (0, 0, 0, 0, opacity)

    if fade_in_frames > 0 and fade_out_frames > 0:
        out.append(Keyframe(frame=0, value=_rect(0.0), easing=easing))
        out.append(Keyframe(frame=fade_in_frames, value=_rect(1.0), easing=easing))
        out.append(
            Keyframe(
                frame=max(fade_in_frames + 1, last_frame - fade_out_frames),
                value=_rect(1.0),
                easing=easing,
            )
        )
        out.append(Keyframe(frame=last_frame, value=_rect(0.0), easing=easing))
    elif fade_in_frames > 0:
        out.append(Keyframe(frame=0, value=_rect(0.0), easing=easing))
        out.append(Keyframe(frame=fade_in_frames, value=_rect(1.0), easing=easing))
    else:
        # fade_out only
        out.append(
            Keyframe(
                frame=max(0, last_frame - fade_out_frames),
                value=_rect(1.0),
                easing=easing,
            )
        )
        out.append(Keyframe(frame=last_frame, value=_rect(0.0), easing=easing))

    return out


def montage_split_offsets(n_cuts: int, clip_duration_frames: int) -> list[int]:
    """Return ``n_cuts - 1`` evenly-spaced split offsets.

    Raises
    ------
    ValueError: if ``n_cuts < 2`` or ``n_cuts > clip_duration_frames``.
    """
    if n_cuts < 2:
        raise ValueError(f"n_cuts must be >= 2; got {n_cuts}")
    if clip_duration_frames <= 0:
        raise ValueError(
            f"clip_duration_frames must be > 0; got {clip_duration_frames}"
        )
    if n_cuts > clip_duration_frames:
        raise ValueError(
            f"n_cuts ({n_cuts}) exceeds clip_duration_frames "
            f"({clip_duration_frames})"
        )
    step = clip_duration_frames / n_cuts
    return [int(round(step * (i + 1))) for i in range(n_cuts - 1)]
