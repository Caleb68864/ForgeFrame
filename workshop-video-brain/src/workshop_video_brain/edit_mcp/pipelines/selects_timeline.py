"""Selects list abstraction: filter, score, and export review-ready marker lists.

Also provides build_selects_timeline() to generate a Kdenlive project from a
selects list.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

from workshop_video_brain.core.models.markers import Marker, MarkerConfig
from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.utils.naming import slugify
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned

logger = logging.getLogger(__name__)

_EXCLUDED_CATEGORIES = {"dead_air", "repetition"}


class SelectsEntry(BaseModel):
    """A single entry in the selects list, wrapping a Marker with export metadata."""

    marker: Marker
    clip_ref: str
    start_seconds: float
    end_seconds: float
    reason: str
    usefulness_score: float


def build_selects(
    markers: list[Marker],
    config: MarkerConfig,
    min_confidence: float = 0.5,
) -> list[SelectsEntry]:
    """Build a filtered, scored selects list from markers.

    Filters:
    - Confidence >= min_confidence
    - Excludes dead_air and repetition categories

    usefulness_score = confidence_score * category_weight (default weight 0.5)
    """
    entries: list[SelectsEntry] = []
    for marker in markers:
        cat = str(marker.category)
        if cat in _EXCLUDED_CATEGORIES:
            continue
        if marker.confidence_score < min_confidence:
            continue
        weight = config.category_weights.get(cat, 0.5)
        usefulness = marker.confidence_score * weight
        entries.append(
            SelectsEntry(
                marker=marker,
                clip_ref=marker.clip_ref,
                start_seconds=marker.start_seconds,
                end_seconds=marker.end_seconds,
                reason=marker.reason,
                usefulness_score=round(usefulness, 6),
            )
        )
    # Sort by usefulness_score descending for best-first presentation
    entries.sort(key=lambda e: e.usefulness_score, reverse=True)
    return entries


def selects_to_json(selects: list[SelectsEntry]) -> str:
    """Serialize the selects list as a JSON array string."""
    data = [entry.model_dump(mode="json") for entry in selects]
    return json.dumps(data, indent=2)


def selects_to_markdown(selects: list[SelectsEntry]) -> str:
    """Render the selects list as a Markdown table.

    Columns: Time, Category, Reason, Score
    """
    lines: list[str] = [
        "| Time | Category | Reason | Score |",
        "| --- | --- | --- | --- |",
    ]
    for entry in selects:
        start = entry.start_seconds
        end = entry.end_seconds
        time_str = f"{start:.1f}s – {end:.1f}s"
        cat = str(entry.marker.category)
        reason = entry.reason.replace("|", "\\|")
        score = f"{entry.usefulness_score:.3f}"
        lines.append(f"| {time_str} | {cat} | {reason} | {score} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Selects timeline builder
# ---------------------------------------------------------------------------


def _build_asset_map(assets: list[MediaAsset]) -> dict[str, MediaAsset]:
    by_path: dict[str, MediaAsset] = {}
    for asset in assets:
        by_path[asset.path] = asset
        by_path[str(asset.id)] = asset
    return by_path


def build_selects_timeline(
    selects: list[SelectsEntry],
    assets: list[MediaAsset],
    workspace_root: Path,
) -> Path:
    """Build a Kdenlive project containing only selected segments.

    Args:
        selects: Filtered selects list.
        assets:  MediaAsset list for resolving clip paths.
        workspace_root: Root of the workspace directory.

    Returns:
        Path to the written .kdenlive file.
    """
    workspace_root = Path(workspace_root)
    asset_map = _build_asset_map(assets)

    project = KdenliveProject(
        version="7",
        title="Selects Timeline",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
    )

    video_track = Track(id="playlist_video", track_type="video", name="Video")
    audio_track = Track(id="playlist_audio", track_type="audio", name="Audio")
    project.tracks = [video_track, audio_track]

    video_playlist = Playlist(id="playlist_video")
    audio_playlist = Playlist(id="playlist_audio")

    seen_producers: dict[str, Producer] = {}

    for entry in selects:
        clip_ref = entry.clip_ref
        asset = asset_map.get(clip_ref)
        resource = asset.path if asset else clip_ref

        if clip_ref not in seen_producers:
            producer_id = f"producer_{len(seen_producers)}"
            producer = Producer(
                id=producer_id,
                resource=resource,
                properties={"resource": resource},
            )
            seen_producers[clip_ref] = producer
            project.producers.append(producer)
        else:
            producer = seen_producers[clip_ref]

        fps = project.profile.fps
        in_point = int(entry.start_seconds * fps)
        out_point = int(entry.end_seconds * fps)
        if out_point < in_point:
            out_point = in_point

        pe = PlaylistEntry(
            producer_id=producer.id,
            in_point=in_point,
            out_point=out_point,
        )
        video_playlist.entries.append(pe)
        audio_playlist.entries.append(
            PlaylistEntry(
                producer_id=producer.id,
                in_point=in_point,
                out_point=out_point,
            )
        )

        guide = Guide(
            position=in_point,
            label=entry.reason or str(entry.marker.category),
            category=str(entry.marker.category),
        )
        project.guides.append(guide)

    project.playlists = [video_playlist, audio_playlist]
    project.tractor = {"id": "tractor0", "in": "0", "out": "99999"}

    title_slug = slugify("selects_timeline") or "selects_timeline"
    return serialize_versioned(project, workspace_root, title_slug)
