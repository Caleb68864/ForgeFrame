"""Color analysis and LUT application pipeline."""
from __future__ import annotations

import logging
from pathlib import Path

from workshop_video_brain.core.models.color import ColorAnalysis
from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddEffect
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher as _patcher

logger = logging.getLogger(__name__)

# Transfer characteristics that indicate HDR content
_HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


def analyze_color(file_path: Path) -> ColorAnalysis:
    """Probe a media file and return color metadata with recommendations.

    Uses probe_media() from Sub-Spec 1 to read extended color fields.
    """
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

    asset = probe_media(file_path)

    color_space = getattr(asset, "color_space", None)
    color_primaries = getattr(asset, "color_primaries", None)
    color_transfer = getattr(asset, "color_transfer", None)
    bit_depth = getattr(asset, "bit_depth", None)

    is_hdr = False
    if color_transfer and any(h in color_transfer for h in _HDR_TRANSFERS):
        is_hdr = True

    recommendations = _build_recommendations(
        color_space, color_primaries, color_transfer, is_hdr
    )

    return ColorAnalysis(
        file_path=str(file_path),
        color_space=color_space,
        color_primaries=color_primaries,
        color_transfer=color_transfer,
        bit_depth=bit_depth,
        is_hdr=is_hdr,
        recommendations=recommendations,
    )


def _build_recommendations(
    color_space: str | None,
    color_primaries: str | None,
    color_transfer: str | None,
    is_hdr: bool,
) -> list[str]:
    """Generate actionable color recommendations."""
    recs: list[str] = []

    if is_hdr:
        recs.append(
            "Source is HDR -- consider tone-mapping to BT.709 for SDR delivery"
        )
        if color_transfer and "smpte2084" in color_transfer:
            recs.append("HDR format: PQ (HDR10). Use a PQ-to-SDR LUT for YouTube SDR.")
        elif color_transfer and "arib-std-b67" in color_transfer:
            recs.append("HDR format: HLG. Use an HLG-to-SDR LUT for YouTube SDR.")
        return recs

    if color_space is None and color_primaries is None:
        recs.append(
            "No color metadata found -- assuming BT.709"
        )
        return recs

    if color_primaries and "bt2020" in color_primaries:
        recs.append(
            "Source is BT.2020 -- consider BT.709 conversion for SDR delivery"
        )
    elif color_primaries and "bt709" in color_primaries:
        recs.append(
            "Source is BT.709 SDR -- no conversion needed for YouTube"
        )
    elif color_primaries and "smpte170m" in color_primaries:
        recs.append(
            "Source is BT.601 (SD) -- upconvert color space if targeting HD delivery"
        )

    if color_space and "bt709" in color_space:
        recs.append("Color matrix: BT.709 -- standard for HD content")
    elif color_space and "bt2020" in color_space:
        recs.append("Color matrix: BT.2020 -- wide gamut, verify display compatibility")

    return recs


def apply_lut_to_project(
    project: KdenliveProject,
    track_index: int,
    clip_index: int,
    lut_path: str,
    effect_name: str = "avfilter.lut3d",
) -> KdenliveProject:
    """Apply a LUT file to a clip in a Kdenlive project.

    Creates an AddEffect intent with the given effect_name and
    patches the project. Returns a new KdenliveProject (deep-copy).

    Parameters
    ----------
    project:
        Parsed Kdenlive project.
    track_index:
        Zero-based track index.
    clip_index:
        Zero-based clip index within the track.
    lut_path:
        Absolute path to the .cube / .3dl LUT file.
    effect_name:
        MLT service name for the LUT effect. Default is "avfilter.lut3d".
        Some Kdenlive builds use "frei0r.lut3d" instead.
    """
    intent = AddEffect(
        track_index=track_index,
        clip_index=clip_index,
        effect_name=effect_name,
        params={"av.file": lut_path},
    )
    return _patcher.patch_project(project, [intent])
