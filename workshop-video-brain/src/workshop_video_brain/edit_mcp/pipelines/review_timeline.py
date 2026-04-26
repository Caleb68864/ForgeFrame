"""Ranking and ordering utilities for Marker objects, plus review timeline
and chapter marker generation."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

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
from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.utils.naming import slugify
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ranking helpers (original API, preserved)
# ---------------------------------------------------------------------------


def rank_markers(markers: list[Marker], config: MarkerConfig) -> list[Marker]:
    """Return markers sorted by (confidence_score * category_weight) descending.

    Categories missing from config.category_weights default to a weight of 0.5.
    """
    def score(marker: Marker) -> float:
        weight = config.category_weights.get(str(marker.category), 0.5)
        return marker.confidence_score * weight

    return sorted(markers, key=score, reverse=True)


def chronological_order(markers: list[Marker]) -> list[Marker]:
    """Return markers sorted by start_seconds ascending (chronological)."""
    return sorted(markers, key=lambda m: m.start_seconds)


def group_by_clip(markers: list[Marker]) -> dict[str, list[Marker]]:
    """Group markers by their clip_ref, preserving insertion order within groups."""
    groups: dict[str, list[Marker]] = {}
    for marker in markers:
        groups.setdefault(marker.clip_ref, []).append(marker)
    return groups


# ---------------------------------------------------------------------------
# Chapter marker helpers
# ---------------------------------------------------------------------------


def generate_chapter_markers(markers: list[Marker]) -> list[Guide]:
    """Filter chapter_candidate markers and create Guide objects."""
    guides: list[Guide] = []
    for marker in markers:
        if str(marker.category) == MarkerCategory.chapter_candidate.value:
            position = int(marker.start_seconds * 25)  # default 25 fps
            label = marker.suggested_label or marker.reason or "Chapter"
            guides.append(Guide(position=position, label=label, category="chapter"))
    return guides


def _seconds_to_timestamp(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS string."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def export_chapters_to_markdown(chapters: list[Guide], fps: float = 25.0) -> str:
    """Format chapter guides as markdown with timestamps."""
    if not chapters:
        return "# Chapters\n\n_No chapters found._\n"
    lines = ["# Chapters", ""]
    for guide in sorted(chapters, key=lambda g: g.position):
        seconds = guide.position / fps if fps > 0 else 0.0
        ts = _seconds_to_timestamp(seconds)
        lines.append(f"- `{ts}` — {guide.label}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Review timeline builder
# ---------------------------------------------------------------------------


def _build_asset_map(assets: list[MediaAsset]) -> dict[str, MediaAsset]:
    """Build path→asset and id→asset lookup."""
    by_path: dict[str, MediaAsset] = {}
    for asset in assets:
        by_path[asset.path] = asset
        by_path[str(asset.id)] = asset
    return by_path


def build_review_timeline(
    markers: list[Marker],
    assets: list[MediaAsset],
    workspace_root: Path,
    mode: str = "ranked",
) -> Path:
    """Build a Kdenlive review timeline from markers.

    Args:
        markers: Markers to include.
        assets:  MediaAsset list for resolving clip paths.
        workspace_root: Root of the workspace directory.
        mode: "ranked" (by confidence) or "chronological".

    Returns:
        Path to the written .kdenlive file.
    """
    workspace_root = Path(workspace_root)

    # Order markers
    if mode == "ranked":
        ordered = sorted(markers, key=lambda m: m.confidence_score, reverse=True)
    else:
        ordered = chronological_order(markers)

    asset_map = _build_asset_map(assets)

    project = KdenliveProject(
        version="7",
        title="Review Timeline",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
    )

    # Create video + audio track pair
    video_track = Track(id="playlist_video", track_type="video", name="Video")
    audio_track = Track(id="playlist_audio", track_type="audio", name="Audio")
    project.tracks = [video_track, audio_track]

    video_playlist = Playlist(id="playlist_video")
    audio_playlist = Playlist(id="playlist_audio")

    seen_producers: dict[str, Producer] = {}

    for marker in ordered:
        clip_ref = marker.clip_ref
        asset = asset_map.get(clip_ref)
        resource = asset.path if asset else clip_ref

        in_point = int(marker.start_seconds * project.profile.fps)
        out_point = int(marker.end_seconds * project.profile.fps)
        if out_point < in_point:
            out_point = in_point

        if clip_ref not in seen_producers:
            from workshop_video_brain.edit_mcp.adapters.kdenlive.producers import (
                make_avformat_producer,
            )
            producer_id = f"producer_{len(seen_producers)}"
            length_frames = (
                int(asset.duration * project.profile.fps)
                if (asset and asset.duration)
                else (out_point + 1)
            )
            producer = make_avformat_producer(
                producer_id, resource, length_frames=max(1, length_frames),
            )
            seen_producers[clip_ref] = producer
            project.producers.append(producer)
        else:
            producer = seen_producers[clip_ref]

        entry = PlaylistEntry(
            producer_id=producer.id,
            in_point=in_point,
            out_point=out_point,
        )
        video_playlist.entries.append(entry)
        audio_playlist.entries.append(
            PlaylistEntry(
                producer_id=producer.id,
                in_point=in_point,
                out_point=out_point,
            )
        )

        # Add guide for the marker
        cat = str(marker.category)
        label = (
            f"{cat}: {marker.reason} (conf: {marker.confidence_score:.2f})"
        )
        guide = Guide(
            position=in_point,
            label=label,
            category=cat,
        )
        project.guides.append(guide)

    project.playlists = [video_playlist, audio_playlist]
    project.tractor = {"id": "tractor0", "in": "0", "out": "99999"}

    # Derive a slug from the project title
    title_slug = slugify("review_timeline") or "review_timeline"
    kdenlive_path = serialize_versioned(project, workspace_root, title_slug)

    # Generate companion markdown report
    _write_review_report(markers, workspace_root)

    return kdenlive_path


def _write_review_report(markers: list[Marker], workspace_root: Path) -> None:
    """Write a markdown review report alongside the timeline."""
    reports_dir = workspace_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"review_report_{timestamp}.md"

    lines = [
        "# Review Report",
        "",
        f"Generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "## Markers",
        "",
        "| Time | Category | Reason | Confidence |",
        "| --- | --- | --- | --- |",
    ]
    for m in sorted(markers, key=lambda x: x.start_seconds):
        t = f"{m.start_seconds:.1f}s – {m.end_seconds:.1f}s"
        cat = str(m.category)
        reason = (m.reason or "").replace("|", "\\|")
        conf = f"{m.confidence_score:.2f}"
        lines.append(f"| {t} | {cat} | {reason} | {conf} |")

    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Review report written to %s", report_path)
