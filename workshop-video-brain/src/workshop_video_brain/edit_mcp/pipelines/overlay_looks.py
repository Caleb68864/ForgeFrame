"""Pure logic for the additive-overlay *look* bundle tools.

Two tutorial-derived looks share the same **additive-overlay** pattern -- put a
second clip on a track *above* the base footage and composite it with a
lightening blend mode (Screen / Lighten / Add) so only the bright parts of the
upper layer show through:

* **Light leaks** -- Fabiano's *"Using Screen/Lighten Blend mode transition to
  include light leaks in KDENLIVE"* (video ``-3TjF3OzECc``). A light-leak /
  lens-flare clip is laid over the footage and blended with **Screen** or
  **Lighten**.
  Source: ``vault/Transcripts/Kdenlive Tutorials/Using Screen-Lighten Blend
  mode transition to include light leaks in KDENLIVE 2020.md``.

* **Day -> night** -- the kdenlivetutorials.com *"From Day to Night"* blog
  (``https://www.kdenlivetutorials.com/2014/11/from-day-to-night/``). A
  hue/saturation/levels grade pushes the plate toward a dark blue night, with an
  optional starry-**sky overlay** composited on a track above.
  Source: ``vault/Transcripts/Kdenlive Tutorials/From Day to Night -
  kdenlivetutorials Blog.md``.

This module is pure logic: it computes ``(mlt_service, property_dict)`` grade
chains and performs *model-level* clip insertion on a ``KdenliveProject`` (the
minimal playlist-targeted insert the ``clip_insert`` tool cannot do -- it always
targets the first video track). It does **not** touch the patcher's intent
handlers or the serializer; it mutates the already-parsed project model the same
way ``_apply_add_clip`` does, then hands off to the shared ``apply_composite``
pipeline for the blend transition.

Honest-subset notes
--------------------
* **Composite-track semantics / filter placement (§1.1/§1.2 of
  docs/plans/2026-07-03-kdenlive-mcp-improvements.md).** ``apply_composite`` and
  clip filters currently address tracks by index and land at the MLT root rather
  than nested in the ``<tractor>`` / playlist ``<entry>``. Both bundle tools
  inherit this known behaviour; it is not a blocker for building the look.
* **Day->night distance-brightness stage omitted.** The blog's final stage keeps
  foreground objects bright with an *animated* Rotoscoping mask + Curves. Per-
  frame roto is a known hard blocker (``masking._spline_json`` emits frame 0
  only), so the whole-frame grade ships and the roto-scoped brightening does not.
* The blog's sky stage layers Darken/Lighten/Invert/Box-Blur passes; the
  additive helper composites the sky with a single lightening blend mode
  (Screen/Lighten/Add), matching the shared pattern.
"""
from __future__ import annotations

import hashlib
from typing import Any

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Producer,
)
from workshop_video_brain.edit_mcp.pipelines import clip_place as _cp
from workshop_video_brain.edit_mcp.pipelines.keyframes import (
    Keyframe,
    _format_scalar,
    build_keyframe_string,
)

# Lightening blend modes that make an additive overlay read as "light on top of"
# the base -- the only honest modes for a light-leak / sky glow overlay.
LIGHT_LEAK_BLEND_MODES: frozenset[str] = frozenset({"screen", "lighten", "add"})


# ---------------------------------------------------------------------------
# Track / geometry helpers
# ---------------------------------------------------------------------------

def video_playlists(project: KdenliveProject) -> list:
    """Return the project's video playlists (mirrors ``_get_video_playlists``)."""
    audio_ids = {t.id for t in project.tracks if t.track_type == "audio"}
    return [p for p in project.playlists if p.id not in audio_ids]


def overlay_geometry(width: int, height: int, opacity: float) -> str:
    """Full-frame composite geometry ``x/y:WxH:opacity`` (opacity 0..100)."""
    op = _check_unit("opacity", opacity)
    return f"0/0:{int(width)}x{int(height)}:{int(round(op * 100))}"


def _check_unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric in [0.0, 1.0]; got {value!r}")
    v = float(value)
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"{name} must be in [0.0, 1.0]; got {v}")
    return v


# ---------------------------------------------------------------------------
# Model-level, playlist-targeted clip insert
# ---------------------------------------------------------------------------

def overlay_producer_id(media_path: str) -> str:
    """Deterministic producer id from a media path (stem + short hash)."""
    from pathlib import Path

    stem = Path(media_path).stem or "overlay"
    h = hashlib.md5(str(media_path).encode()).hexdigest()[:6]
    return f"{stem}_{h}"


def insert_overlay_clip(
    project: KdenliveProject,
    overlay_track: int,
    media_path: str,
    at_frame: int,
    duration_frames: int,
) -> int:
    """Insert ``media_path`` onto the ``overlay_track``-th video playlist.

    Appends the overlay entry ``[0, duration_frames - 1]`` after the playlist's
    existing content, preceded by a blank gap of ``at_frame`` frames (so the clip
    lands ``at_frame`` frames past the current track end). Ensures a producer
    exists for the media. Mutates ``project`` in place and returns the *real*-clip
    index of the inserted entry on that playlist (usable as ``(overlay_track,
    index)`` for clip-filter ops).

    The placement runs through the canonical ``clip_place`` engine
    (``pipelines/clip_place.plan_overwrite``): the append-with-leading-gap is
    expressed as an overwrite placement at absolute frame ``track_end + at_frame``
    (past the track end, so the engine emits the pad blank + clip), replacing the
    former hand-rolled model-level blank-pad insert (SYNTHESIS gap #6 migration).
    """
    if at_frame < 0:
        raise ValueError(f"at_frame must be >= 0; got {at_frame}")
    if duration_frames <= 0:
        raise ValueError(f"duration_frames must be > 0; got {duration_frames}")

    vps = video_playlists(project)
    if not vps:
        raise ValueError("No video playlists found in project")
    if overlay_track < 0 or overlay_track >= len(vps):
        raise ValueError(
            f"overlay_track {overlay_track} out of range "
            f"(project has {len(vps)} video track(s)); add a track above the "
            f"base footage first (track_add)"
        )
    playlist = vps[overlay_track]

    producer_id = overlay_producer_id(media_path)
    if producer_id not in {p.id for p in project.producers}:
        project.producers.append(
            Producer(
                id=producer_id,
                resource=media_path,
                properties={"resource": media_path},
            )
        )

    clip = _cp.PlacedClip(
        producer_id=producer_id, in_point=0, out_point=duration_frames - 1
    )
    at = _cp.playlist_length(playlist.entries) + at_frame
    result = _cp.plan_overwrite(playlist.entries, at, clip)
    playlist.entries = result.entries
    return result.placed_index


# ---------------------------------------------------------------------------
# Day -> night grade chain
# ---------------------------------------------------------------------------

# Ordered chain: video-equalizer (darken + desaturate + contrast) then a blue
# night tint. Mirrors the blog's Saturation + Levels(darken) + Hue-toward-blue.
DAY_TO_NIGHT_SERVICES: tuple[str, ...] = ("avfilter.eq", "frei0r.colorize")

NIGHT_HUE = 0.62  # normalized frei0r hue ~ blue


def _ramp(neutral: float, night: float, keyframed: bool, end_frame: int, fps: float) -> str:
    """Return a static night value, or a neutral->night keyframe ramp string."""
    if not keyframed or end_frame <= 0:
        return _format_scalar(night)
    kfs = [
        Keyframe(frame=0, value=neutral, easing="linear"),
        Keyframe(frame=end_frame, value=night, easing="linear"),
    ]
    return build_keyframe_string("scalar", kfs, fps=fps)


def day_to_night_chain(
    intensity: float = 0.5,
    keyframed: bool = True,
    duration_frames: int = 0,
    fps: float = 25.0,
) -> list[tuple[str, dict[str, str]]]:
    """Return the ordered ``(mlt_service, property_dict)`` day->night grade.

    ``intensity`` in ``[0.0, 1.0]`` scales how far the plate is pushed toward
    night. When ``keyframed`` is true (and ``duration_frames`` > 1), the animated
    parameters ramp from a neutral "day" at frame 0 to full night at the last
    frame, so the shot visibly darkens over the clip; otherwise static night
    values are written.
    """
    if isinstance(intensity, bool) or not isinstance(intensity, (int, float)):
        raise ValueError(f"intensity must be numeric in [0.0, 1.0]; got {intensity!r}")
    i = float(intensity)
    if not 0.0 <= i <= 1.0:
        raise ValueError(f"intensity must be in [0.0, 1.0]; got {i}")

    end = max(0, int(duration_frames) - 1)

    # avfilter.eq night targets (neutral -> night)
    brightness_night = -0.06 - 0.24 * i   # darken: -0.06 .. -0.30
    saturation_night = 1.0 - 0.5 * i      # desaturate: 1.0 .. 0.50
    contrast_night = 1.0 + 0.15 * i       # slight contrast: 1.0 .. 1.15

    # frei0r.colorize blue tint (neutral saturation 0 -> night)
    tint_sat_night = 0.15 + 0.35 * i      # blue cast: 0.15 .. 0.50

    eq_props = {
        "av.brightness": _ramp(0.0, brightness_night, keyframed, end, fps),
        "av.saturation": _ramp(1.0, saturation_night, keyframed, end, fps),
        "av.contrast": _ramp(1.0, contrast_night, keyframed, end, fps),
    }
    colorize_props = {
        "hue": _format_scalar(NIGHT_HUE),
        "saturation": _ramp(0.0, tint_sat_night, keyframed, end, fps),
        "lightness": _format_scalar(0.5),
    }
    return [
        ("avfilter.eq", eq_props),
        ("frei0r.colorize", colorize_props),
    ]


# ---------------------------------------------------------------------------
# Catalog + filter-XML helpers (self-contained; replicate tools.py privates so
# this module never imports the giant server.tools module).
# ---------------------------------------------------------------------------

def lookup_catalog_id(mlt_service: str) -> str | None:
    """Return the ``kdenlive_id`` for an ``mlt_service``, or ``None``."""
    try:
        from workshop_video_brain.edit_mcp.pipelines import effect_catalog as _catalog
    except ModuleNotFoundError:
        return None
    for kid, eff in _catalog.CATALOG.items():
        if eff.mlt_service == mlt_service:
            return kid
    return None


def build_filter_xml(
    mlt_service: str,
    kdenlive_id: str,
    track: int,
    clip: int,
    props: list[tuple[str, str]],
) -> str:
    """Build a Kdenlive/MLT ``<filter>`` XML string (mirrors ``_build_filter_xml``)."""
    import xml.etree.ElementTree as ET

    root = ET.Element(
        "filter",
        {"mlt_service": mlt_service, "track": str(track), "clip_index": str(clip)},
    )
    svc = ET.SubElement(root, "property", {"name": "mlt_service"})
    svc.text = mlt_service
    kid = ET.SubElement(root, "property", {"name": "kdenlive_id"})
    kid.text = kdenlive_id
    for name, value in props:
        prop = ET.SubElement(root, "property", {"name": name})
        prop.text = value
    return ET.tostring(root, encoding="unicode")
