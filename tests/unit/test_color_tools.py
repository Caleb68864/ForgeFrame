"""TDD tests for color analysis and LUT application."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.color import ColorAnalysis


# --- fixtures ---------------------------------------------------------------

def _make_asset(**kwargs):
    """Create a mock MediaAsset with color fields."""
    asset = MagicMock()
    asset.color_space = kwargs.get("color_space", None)
    asset.color_primaries = kwargs.get("color_primaries", None)
    asset.color_transfer = kwargs.get("color_transfer", None)
    asset.bit_depth = kwargs.get("bit_depth", None)
    return asset


# --- analyze_color ----------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_bt709_source(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset(
        color_space="bt709",
        color_primaries="bt709",
        color_transfer="bt709",
        bit_depth=8,
    )
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.color_space == "bt709"
    assert result.color_primaries == "bt709"
    assert result.is_hdr is False
    assert any("BT.709 SDR" in r for r in result.recommendations)


@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_bt2020_source(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset(
        color_space="bt2020nc",
        color_primaries="bt2020",
        color_transfer="bt709",
        bit_depth=10,
    )
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.color_primaries == "bt2020"
    assert result.is_hdr is False
    assert any("BT.2020" in r for r in result.recommendations)


@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_missing_metadata(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset()  # all None
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.color_space is None
    assert result.is_hdr is False
    assert any("No color metadata found" in r for r in result.recommendations)


@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_hdr_pq_detection(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset(
        color_space="bt2020nc",
        color_primaries="bt2020",
        color_transfer="smpte2084",
        bit_depth=10,
    )
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.is_hdr is True
    assert any("HDR" in r for r in result.recommendations)
    assert any("PQ" in r for r in result.recommendations)


@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_hdr_hlg_detection(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset(
        color_space="bt2020nc",
        color_primaries="bt2020",
        color_transfer="arib-std-b67",
        bit_depth=10,
    )
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.is_hdr is True
    assert any("HLG" in r for r in result.recommendations)


# --- apply_lut_to_project ---------------------------------------------------

@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_lut_application_creates_add_effect(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import apply_lut_to_project
    from workshop_video_brain.core.models.timeline import AddEffect

    mock_project = MagicMock()
    mock_patch.return_value = MagicMock()

    result = apply_lut_to_project(
        mock_project, track_index=0, clip_index=1, lut_path="/luts/film_look.cube"
    )

    mock_patch.assert_called_once()
    call_args = mock_patch.call_args
    intents = call_args[0][1]  # second positional arg
    assert len(intents) == 1
    assert isinstance(intents[0], AddEffect)
    assert intents[0].effect_name == "avfilter.lut3d"
    assert intents[0].params == {"av.file": "/luts/film_look.cube"}
    assert intents[0].track_index == 0
    assert intents[0].clip_index == 1


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_lut_round_trip(mock_patch):
    """Verify that applying a LUT returns the patched project, not the original."""
    from workshop_video_brain.edit_mcp.pipelines.color_tools import apply_lut_to_project

    original = MagicMock(name="original")
    patched = MagicMock(name="patched")
    mock_patch.return_value = patched

    result = apply_lut_to_project(original, 0, 0, "/luts/rec709.cube")

    assert result is patched
    assert result is not original


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_lut_invalid_track_propagates(mock_patch):
    """If patcher raises IndexError for bad track, it should propagate."""
    from workshop_video_brain.edit_mcp.pipelines.color_tools import apply_lut_to_project

    mock_patch.side_effect = IndexError("Track index 99 out of range")

    with pytest.raises(IndexError, match="Track index 99"):
        apply_lut_to_project(MagicMock(), 99, 0, "/luts/test.cube")
