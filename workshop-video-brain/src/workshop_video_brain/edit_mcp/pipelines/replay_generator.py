"""Build Replay Generator pipeline.

Generates a highlight-reel replay .kdenlive project by greedily selecting the
highest-scored non-overlapping marker segments, padding each by 2 s, merging
adjacent segments (gap < 3 s), and ordering them chronologically.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.markers import Marker, MarkerConfig
from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.core.utils.naming import slugify
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
from workshop_video_brain.edit_mcp.pipelines.marker_rules import default_config
from workshop_video_brain.edit_mcp.pipelines.review_timeline import rank_markers

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PADDING_SECONDS: float = 2.0
_MERGE_GAP_SECONDS: float = 3.0
_CROSSFADE_FRAMES: int = 24  # medium preset


# ---------------------------------------------------------------------------
# Report model
# ---------------------------------------------------------------------------


class ReplaySegment(BaseModel):
    """Metadata for a single segment included in the replay."""

    start: float
    end: float
    reason: str
    source_clip: str


class ReplayReport(BaseModel):
    """Summary report for a generated replay."""

    segment_count: int
    total_duration: float
    target_duration: float
    segments_used: list[ReplaySegment]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_markers(workspace_root: Path) -> list[Marker]:
    """Load all *_markers.json files from the markers/ directory."""
    markers_dir = workspace_root / "markers"
    if not markers_dir.exists():
        return []
    markers: list[Marker] = []
    for path in sorted(markers_dir.glob("*_markers.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for item in raw:
                markers.append(Marker(**item))
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not load markers from %s: %s", path, exc)
    return markers


def _load_assets(workspace_root: Path) -> list[MediaAsset]:
    """Load media assets from workspace manifest (best-effort)."""
    try:
        from workshop_video_brain.workspace.manifest import read_manifest  # noqa: F401
        # Assets are discovered from media/raw; we return an empty list when no
        # probe data is available — the generator falls back to clip_ref paths.
        raw_dir = workspace_root / "media" / "raw"
        if not raw_dir.exists():
            return []
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
        return scan_directory(raw_dir)
    except Exception as exc:
        logger.debug("Could not load assets: %s", exc)
        return []


def _select_segments(
    ranked: list[Marker],
    target_duration: float,
    padding: float = _PADDING_SECONDS,
) -> list[Marker]:
    """Greedily select highest-scored non-overlapping markers.

    Each marker is padded by *padding* seconds on each side when checking for
    overlap, but the *original* marker boundaries are stored so that the merge
    step can apply its own padding.

    Returns markers in the order they were selected (score-ranked), not
    chronological — chronological reordering happens later.
    """
    selected: list[Marker] = []
    # Store padded (start, end) of already-selected segments for overlap checks
    occupied: list[tuple[float, float]] = []
    total = 0.0

    for marker in ranked:
        if total >= target_duration:
            break
        padded_start = max(0.0, marker.start_seconds - padding)
        padded_end = marker.end_seconds + padding

        # Skip if this padded window overlaps any already-selected padded window
        overlap = False
        for occ_start, occ_end in occupied:
            if padded_start < occ_end and padded_end > occ_start:
                overlap = True
                break
        if overlap:
            continue

        selected.append(marker)
        occupied.append((padded_start, padded_end))
        total += (padded_end - padded_start)

    return selected


def _apply_padding(markers: list[Marker], padding: float) -> list[tuple[float, float, Marker]]:
    """Return (padded_start, padded_end, marker) triples sorted chronologically."""
    result = []
    for m in markers:
        start = max(0.0, m.start_seconds - padding)
        end = m.end_seconds + padding
        result.append((start, end, m))
    return sorted(result, key=lambda x: x[0])


def _merge_adjacent(
    segments: list[tuple[float, float, Marker]],
    merge_gap: float = _MERGE_GAP_SECONDS,
) -> list[tuple[float, float, list[Marker]]]:
    """Merge segments whose gap is less than *merge_gap* seconds.

    Returns a list of (merged_start, merged_end, [markers_in_group]).
    """
    if not segments:
        return []

    merged: list[tuple[float, float, list[Marker]]] = []
    cur_start, cur_end, cur_markers = segments[0][0], segments[0][1], [segments[0][2]]

    for start, end, marker in segments[1:]:
        gap = start - cur_end
        if gap < merge_gap:
            # Merge: extend the current group
            cur_end = max(cur_end, end)
            cur_markers.append(marker)
        else:
            merged.append((cur_start, cur_end, cur_markers))
            cur_start, cur_end, cur_markers = start, end, [marker]

    merged.append((cur_start, cur_end, cur_markers))
    return merged


def _build_asset_map(assets: list[MediaAsset]) -> dict[str, MediaAsset]:
    by_path: dict[str, MediaAsset] = {}
    for asset in assets:
        by_path[asset.path] = asset
        by_path[str(asset.id)] = asset
    return by_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_replay(
    workspace_root: Path,
    target_duration: float = 60.0,
) -> Path:
    """Generate a replay highlight-reel .kdenlive project.

    Steps
    -----
    1. Read markers from ``markers/`` in *workspace_root*.
    2. Read media assets (best-effort).
    3. Rank markers by score (confidence * category_weight).
    4. Greedily select non-overlapping segments until *target_duration* is met.
    5. Apply 2 s padding to each selected segment.
    6. Merge adjacent segments (gap < 3 s) into one.
    7. Build a KdenliveProject with segments in chronological order.
    8. Add medium crossfade (24 frames) between segments.
    9. Add guide markers labelled "Highlight: {reason}".
    10. Serialize to ``projects/working_copies/{title}_replay_v{N}.kdenlive``.

    Returns
    -------
    Path to the generated .kdenlive file.

    Raises
    ------
    ValueError
        If no markers are found.
    """
    workspace_root = Path(workspace_root)

    # 1. Load markers
    markers = _load_markers(workspace_root)
    if not markers:
        raise ValueError("No markers found. Run markers_auto_generate first.")

    # 2. Load assets (best-effort)
    assets = _load_assets(workspace_root)
    asset_map = _build_asset_map(assets)

    # 3. Rank markers
    config = default_config()
    ranked = rank_markers(markers, config)

    # 4. Greedy segment selection
    selected = _select_segments(ranked, target_duration, padding=_PADDING_SECONDS)

    # 5. Apply padding and sort chronologically
    padded = _apply_padding(selected, _PADDING_SECONDS)

    # 6. Merge adjacent segments (gap < 3 s)
    merged = _merge_adjacent(padded, _MERGE_GAP_SECONDS)

    # 7. Build KdenliveProject
    fps = 25.0
    project = KdenliveProject(
        version="7",
        title="Replay",
        profile=ProjectProfile(width=1920, height=1080, fps=fps, colorspace="709"),
    )

    video_track = Track(id="playlist_video", track_type="video", name="Video")
    audio_track = Track(id="playlist_audio", track_type="audio", name="Audio")
    project.tracks = [video_track, audio_track]

    video_playlist = Playlist(id="playlist_video")
    audio_playlist = Playlist(id="playlist_audio")

    seen_producers: dict[str, Producer] = {}
    timeline_frame = 0  # running frame counter for guide positions

    for seg_idx, (seg_start, seg_end, seg_markers) in enumerate(merged):
        # Use the first marker's clip_ref as the representative source
        primary_marker = seg_markers[0]
        clip_ref = primary_marker.clip_ref
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

        in_point = int(seg_start * fps)
        out_point = int(seg_end * fps)
        if out_point <= in_point:
            out_point = in_point + 1

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

        # 9. Add guide marker labelled "Highlight: {reason}"
        reason = primary_marker.reason or str(primary_marker.category)
        guide_label = f"Highlight: {reason}"
        project.guides.append(
            Guide(
                position=timeline_frame,
                label=guide_label,
                category="highlight",
            )
        )

        seg_duration_frames = out_point - in_point
        timeline_frame += seg_duration_frames

        # 8. Add crossfade transition between segments (not after the last one)
        if seg_idx < len(merged) - 1:
            from workshop_video_brain.core.models.kdenlive import OpaqueElement
            xml = (
                f'<transition id="transition_{seg_idx}" '
                f'type="luma" '
                f'track="playlist_video" '
                f'left="producer_{seg_idx}" '
                f'right="producer_{seg_idx + 1 if seg_idx + 1 < len(seen_producers) else seg_idx}" '
                f'duration="{_CROSSFADE_FRAMES}" />'
            )
            project.opaque_elements.append(
                OpaqueElement(
                    tag="transition",
                    xml_string=xml,
                    position_hint="after_tractor",
                )
            )

    project.playlists = [video_playlist, audio_playlist]
    project.tractor = {"id": "tractor0", "in": "0", "out": str(max(timeline_frame - 1, 0))}

    # Serialize to versioned path
    title_slug = slugify("replay") or "replay"
    output_path = serialize_versioned(project, workspace_root, title_slug)
    logger.info("Replay generated: %s", output_path)
    return output_path
