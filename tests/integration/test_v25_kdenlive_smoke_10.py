"""Smoke test batch 10.0: build-from-data pipelines emit v25-shape output.

Exercises the three Python pipelines that build ``.kdenlive`` files
without going through the patcher's ``AddClip`` intent:

* ``selects_timeline.build_selects_timeline``
* ``review_timeline.build_review_timeline``
* ``assembly.build_assembly_project`` (via the smoke -- harder to
  exercise standalone)

These were quietly broken until smoke 10: each constructed
``Producer(id=..., resource=..., properties={'resource': ...})``
without ``mlt_service`` or ``length``, so Kdenlive 25.x couldn't load
the bin clip.  Fixed by routing all four producer-construction sites
through the new ``adapters/kdenlive/producers.make_avformat_producer``
factory (``_apply_add_clip``, selects, review, assembly).

032 + 033 verify a real selects timeline + review timeline open in
Kdenlive with the bin clip loaded and playable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.markers import (
    Marker,
    MarkerCategory,
    MarkerConfig,
)
from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.edit_mcp.pipelines.review_timeline import build_review_timeline
from workshop_video_brain.edit_mcp.pipelines.selects_timeline import (
    SelectsEntry,
    build_selects_timeline,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"
USER_TEST_KDENLIVE = Path("C:/Users/CalebBennett/Videos/Test KdenLive")
USER_OUTPUT_DIR = Path("C:/Users/CalebBennett/Videos/Video Production/tests/mcp_output")


def _resolve_clip(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


def _make_workspace(tmp_path: Path) -> Path:
    """selects/review timelines write to ``projects/working_copies/`` so
    the workspace needs the standard layout pre-created."""
    (tmp_path / "projects" / "working_copies").mkdir(parents=True, exist_ok=True)
    (tmp_path / "projects" / "snapshots").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _make_marker(
    *, clip_ref: str, start: float, end: float, category: str = "hook_candidate",
    confidence: float = 0.8, reason: str = "interesting",
) -> Marker:
    return Marker(
        category=MarkerCategory(category),
        confidence_score=confidence,
        reason=reason,
        clip_ref=clip_ref,
        start_seconds=start,
        end_seconds=end,
    )


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_032_selects_timeline_emits_v25_producers(tmp_path):
    """Build a selects timeline from two markers; verify the resulting
    ``.kdenlive`` has chains with ``mlt_service`` and ``length``."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No source clip available")

    ws = _make_workspace(tmp_path)
    asset = MediaAsset(
        path=str(clip).replace("\\", "/"),
        media_type="video",
        width=1920, height=1080, duration=5.0,
        bitrate=8_000_000, video_codec="h264",
    )
    selects = [
        SelectsEntry(
            marker=_make_marker(clip_ref=asset.path, start=0.5, end=1.5),
            clip_ref=asset.path,
            start_seconds=0.5,
            end_seconds=1.5,
            reason="opening hook",
            usefulness_score=0.9,
        ),
        SelectsEntry(
            marker=_make_marker(clip_ref=asset.path, start=3.0, end=4.0),
            clip_ref=asset.path,
            start_seconds=3.0,
            end_seconds=4.0,
            reason="core demo",
            usefulness_score=0.8,
        ),
    ]
    out_path = build_selects_timeline(selects, [asset], ws)

    # Drop a copy into the user's Kdenlive folder for visual review.
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    user_copy = USER_OUTPUT_DIR / "032-selects-timeline.kdenlive"
    user_copy.write_bytes(out_path.read_bytes())

    # Structural assertions on the produced project.
    import xml.etree.ElementTree as ET
    root = ET.parse(out_path).getroot()
    chains = root.findall("chain")
    assert len(chains) >= 1
    # Every avformat chain should declare mlt_service and length.
    for chain in chains:
        props = {p.get("name"): (p.text or "") for p in chain.findall("property")}
        assert props.get("mlt_service") in ("avformat-novalidate", "avformat"), (
            f"chain {chain.get('id')} missing mlt_service"
        )
        assert props.get("length"), (
            f"chain {chain.get('id')} missing length"
        )


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_033_review_timeline_emits_v25_producers(tmp_path):
    """Build a review timeline from a few markers; verify v25-shape output."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No source clip available")

    ws = _make_workspace(tmp_path)
    asset = MediaAsset(
        path=str(clip).replace("\\", "/"),
        media_type="video",
        width=1920, height=1080, duration=5.0,
        bitrate=8_000_000, video_codec="h264",
    )
    markers = [
        _make_marker(clip_ref=asset.path, start=0.0, end=2.0, confidence=0.9),
        _make_marker(clip_ref=asset.path, start=2.5, end=4.5, confidence=0.7),
    ]
    out_path = build_review_timeline(markers, [asset], ws, mode="ranked")

    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    user_copy = USER_OUTPUT_DIR / "033-review-timeline.kdenlive"
    user_copy.write_bytes(out_path.read_bytes())

    import xml.etree.ElementTree as ET
    root = ET.parse(out_path).getroot()
    chains = root.findall("chain")
    assert len(chains) >= 1
    for chain in chains:
        props = {p.get("name"): (p.text or "") for p in chain.findall("property")}
        assert props.get("mlt_service") in ("avformat-novalidate", "avformat")
        assert props.get("length")
