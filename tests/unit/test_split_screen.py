"""Unit tests for the split/quad-screen pipeline (tutorial #15).

Covers cell geometry math across 1080p / 4K / vertical profiles, gap and
border handling, crop modes (fit vs stretch), and the ``apply_split_screen``
composite wiring (via a mocked ``apply_composite``).
"""
from unittest.mock import patch

import pytest

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.pipelines.split_screen import (
    LAYOUTS,
    CROP_MODES,
    Cell,
    compute_cells,
    apply_split_screen,
)


# ---------------------------------------------------------------------------
# Cell.geometry
# ---------------------------------------------------------------------------

def test_cell_geometry_string():
    assert Cell(0, 0, 960, 1080).geometry() == "0/0:960x1080:100"
    assert Cell(960, 0, 960, 1080).geometry(75) == "960/0:960x1080:75"


# ---------------------------------------------------------------------------
# 2h side-by-side (stretch) -- 1080p
# ---------------------------------------------------------------------------

class TestTwoHStretch:
    def test_full_frame_split(self):
        cells = compute_cells("2h", 1920, 1080, crop="stretch")
        assert len(cells) == 2
        assert cells[0] == Cell(0, 0, 960, 1080)      # left
        assert cells[1] == Cell(960, 0, 960, 1080)    # right

    def test_cells_plus_gap_sum_to_width(self):
        cells = compute_cells("2h", 1920, 1080, gap_px=20, crop="stretch")
        # left=950, gap=20, right=950 -> 1920
        assert cells[0] == Cell(0, 0, 950, 1080)
        assert cells[1] == Cell(970, 0, 950, 1080)
        assert cells[0].width + 20 + cells[1].width == 1920

    def test_odd_width_remainder_on_trailing_cell(self):
        # 1921 wide, gap 0: left=960, right=961
        cells = compute_cells("2h", 1921, 1080, crop="stretch")
        assert cells[0].width == 960
        assert cells[1].width == 961
        assert cells[1].x == 960


# ---------------------------------------------------------------------------
# 2v top-bottom (stretch)
# ---------------------------------------------------------------------------

class TestTwoVStretch:
    def test_full_frame_split(self):
        cells = compute_cells("2v", 1920, 1080, crop="stretch")
        assert cells[0] == Cell(0, 0, 1920, 540)      # top
        assert cells[1] == Cell(0, 540, 1920, 540)    # bottom

    def test_gap(self):
        cells = compute_cells("2v", 1920, 1080, gap_px=40, crop="stretch")
        assert cells[0] == Cell(0, 0, 1920, 520)
        assert cells[1] == Cell(0, 560, 1920, 520)


# ---------------------------------------------------------------------------
# Quad (stretch)
# ---------------------------------------------------------------------------

class TestQuadStretch:
    def test_row_major_order(self):
        cells = compute_cells("4", 1920, 1080, crop="stretch")
        assert len(cells) == 4
        assert cells[0] == Cell(0, 0, 960, 540)       # TL
        assert cells[1] == Cell(960, 0, 960, 540)     # TR
        assert cells[2] == Cell(0, 540, 960, 540)     # BL
        assert cells[3] == Cell(960, 540, 960, 540)   # BR

    def test_matches_tutorial_values(self):
        # Tutorial sets each quad cell height=540, width=960, y-axis=540.
        cells = compute_cells("4", 1920, 1080, crop="stretch")
        for c in cells:
            assert (c.width, c.height) == (960, 540)
        assert cells[2].y == 540 and cells[3].y == 540


# ---------------------------------------------------------------------------
# 4K + vertical profiles
# ---------------------------------------------------------------------------

class TestOtherProfiles:
    def test_4k_2h(self):
        cells = compute_cells("2h", 3840, 2160, crop="stretch")
        assert cells[0] == Cell(0, 0, 1920, 2160)
        assert cells[1] == Cell(1920, 0, 1920, 2160)

    def test_4k_quad(self):
        cells = compute_cells("4", 3840, 2160, crop="stretch")
        assert cells[0] == Cell(0, 0, 1920, 1080)
        assert cells[3] == Cell(1920, 1080, 1920, 1080)

    def test_vertical_2v(self):
        # 1080x1920 portrait, top/bottom split
        cells = compute_cells("2v", 1080, 1920, crop="stretch")
        assert cells[0] == Cell(0, 0, 1080, 960)
        assert cells[1] == Cell(0, 960, 1080, 960)

    def test_vertical_quad(self):
        cells = compute_cells("4", 1080, 1920, crop="stretch")
        assert cells[0] == Cell(0, 0, 540, 960)
        assert cells[3] == Cell(540, 960, 540, 960)


# ---------------------------------------------------------------------------
# Crop = fit (aspect-preserving letterbox)
# ---------------------------------------------------------------------------

class TestCropFit:
    def test_2h_fit_letterboxes_within_cell(self):
        # 1080p source (16:9) into a 960x1080 cell -> width-constrained.
        # fit rect: fw=960, fh=round(960*1080/1920)=540, centred vertically.
        cells = compute_cells("2h", 1920, 1080, crop="fit")
        left = cells[0]
        assert left.width == 960
        assert left.height == 540
        assert left.x == 0
        assert left.y == (1080 - 540) // 2  # 270

    def test_quad_fit_matches_cell_aspect(self):
        # Quad cell is 960x540 which is already 16:9 == source aspect;
        # fit should equal the full cell (no letterbox).
        cells = compute_cells("4", 1920, 1080, crop="fit")
        assert cells[0] == Cell(0, 0, 960, 540)

    def test_default_crop_is_fit(self):
        assert compute_cells("2h", 1920, 1080) == compute_cells(
            "2h", 1920, 1080, crop="fit"
        )


# ---------------------------------------------------------------------------
# Border inset
# ---------------------------------------------------------------------------

class TestBorder:
    def test_border_insets_every_edge(self):
        cells = compute_cells("2h", 1920, 1080, border_px=10, crop="stretch")
        # left base 0,0,960,1080 -> inset 10 each side
        assert cells[0] == Cell(10, 10, 940, 1060)
        # right base 960,0,960,1080 -> inset
        assert cells[1] == Cell(970, 10, 940, 1060)

    def test_border_and_gap_combine(self):
        cells = compute_cells(
            "2h", 1920, 1080, gap_px=20, border_px=10, crop="stretch"
        )
        # base left 0,0,950,1080 -> inset -> 10,10,930,1060
        assert cells[0] == Cell(10, 10, 930, 1060)


# ---------------------------------------------------------------------------
# Validation / errors
# ---------------------------------------------------------------------------

class TestComputeCellsErrors:
    def test_unknown_layout(self):
        with pytest.raises(ValueError, match="Unknown layout"):
            compute_cells("3h", 1920, 1080)

    def test_unknown_crop(self):
        with pytest.raises(ValueError, match="Unknown crop"):
            compute_cells("2h", 1920, 1080, crop="cover")

    def test_non_positive_dims(self):
        with pytest.raises(ValueError, match="positive"):
            compute_cells("2h", 0, 1080)

    def test_negative_gap(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            compute_cells("2h", 1920, 1080, gap_px=-1)

    def test_collapsing_border_raises(self):
        with pytest.raises(ValueError, match="collapsed"):
            compute_cells("2h", 1920, 1080, border_px=600, crop="stretch")


# ---------------------------------------------------------------------------
# apply_split_screen wiring
# ---------------------------------------------------------------------------

def _project(width=1920, height=1080):
    return KdenliveProject.model_validate({
        "profile": {"width": width, "height": height, "colorspace": "709"},
    })


class TestApplySplitScreen:
    @patch("workshop_video_brain.edit_mcp.pipelines.split_screen.apply_composite")
    def test_2h_composites_each_track_over_base(self, mock_comp):
        project = _project()
        mock_comp.side_effect = lambda proj, **kw: proj  # pass-through

        updated, cells = apply_split_screen(
            project, "2h", [1, 2], start_frame=0, end_frame=120,
            base_track=0, crop="stretch",
        )
        assert len(cells) == 2
        assert mock_comp.call_count == 2
        # Track 1 -> left cell geometry, track 2 -> right cell geometry.
        call1 = mock_comp.call_args_list[0].kwargs
        assert call1["track_a"] == 0 and call1["track_b"] == 1
        assert call1["blend_mode"] == "cairoblend"
        assert call1["geometry"] == "0/0:960x1080:100"
        call2 = mock_comp.call_args_list[1].kwargs
        assert call2["track_b"] == 2
        assert call2["geometry"] == "960/0:960x1080:100"

    @patch("workshop_video_brain.edit_mcp.pipelines.split_screen.apply_composite")
    def test_quad_four_composites(self, mock_comp):
        mock_comp.side_effect = lambda proj, **kw: proj
        _updated, cells = apply_split_screen(
            _project(), "4", [1, 2, 3, 4], start_frame=0, end_frame=90,
            crop="stretch",
        )
        assert mock_comp.call_count == 4
        assert len(cells) == 4

    def test_track_count_mismatch(self):
        with pytest.raises(ValueError, match="needs exactly 2 tracks"):
            apply_split_screen(_project(), "2h", [1, 2, 3], 0, 120)

    def test_quad_track_count_mismatch(self):
        with pytest.raises(ValueError, match="needs exactly 4 tracks"):
            apply_split_screen(_project(), "4", [1, 2], 0, 120)

    def test_duplicate_tracks(self):
        with pytest.raises(ValueError, match="distinct"):
            apply_split_screen(_project(), "2h", [1, 1], 0, 120)

    def test_base_collision(self):
        with pytest.raises(ValueError, match="base_track"):
            apply_split_screen(_project(), "2h", [0, 1], 0, 120, base_track=0)

    def test_bad_frame_range(self):
        with pytest.raises(ValueError, match="greater than"):
            apply_split_screen(_project(), "2h", [1, 2], 120, 120)

    @patch("workshop_video_brain.edit_mcp.pipelines.split_screen.apply_composite")
    def test_unknown_layout(self, mock_comp):
        with pytest.raises(ValueError, match="Unknown layout"):
            apply_split_screen(_project(), "9x9", [1, 2], 0, 120)


def test_layouts_and_crop_constants():
    assert LAYOUTS == {"2h": 2, "2v": 2, "4": 4}
    assert CROP_MODES == frozenset({"fit", "stretch"})
