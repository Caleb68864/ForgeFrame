"""Split / quad-screen compositing -- pure geometry + composite application.

Derived from the tutorial "Two Ways To Create Split / Quad Screen Videos"
(https://www.youtube.com/watch?v=7C2oP2z0m3Y). The tutorial shows two hand
workflows -- a *Position and Zoom* effect and a *Composite and Transform*
(qtblend) transition -- to scale each source into a grid cell (height 540,
optionally width 960, plus X/Y placement and the "distort" checkbox).

This module packages that into deterministic geometry: given a layout and the
project profile it computes one rectangle per cell, then places each source
track into its cell by reusing :func:`compositing.apply_composite` -- the exact
same machinery ``apply_pip`` uses (frei0r.cairoblend + ``geometry`` string).

Layouts
-------
- ``"2h"`` -- two cells side-by-side (left, right).
- ``"2v"`` -- two cells stacked (top, bottom).
- ``"4"``  -- quad, 2x2 grid in row-major order (TL, TR, BL, BR).

``tracks`` maps 1:1 (in order) onto the cells above and each is composited over
``base_track`` (a background/color track), just as a PiP overlay composites over
its base.

Crop modes
----------
- ``"stretch"`` -- scale the source to exactly fill its cell (the tutorial's
  "distort" checkbox: fills the cell but changes aspect ratio).
- ``"fit"`` -- preserve the source's aspect ratio (assumed equal to the project
  profile's) inside the cell, centred, letterboxed against the background. No
  distortion.

True center-crop-to-fill ("cover": crop the source so it fills the cell with
neither distortion nor letterbox) is **not** expressible through a single
composite/qtblend geometry -- it needs a per-clip crop effect. That is a noted
omission, not implemented here.

Placement caveat (kdenlive-mcp-improvements plan §1.1 / §1.2)
------------------------------------------------------------
Like every composite in this codebase, the transition is appended at the MLT
root via the shared patcher. Whether Kdenlive renders it in place is subject to
the §1.1/§1.2 filter/composition-placement work; this is noted, not blocking.
The reference workflow uses the *qtblend* "Composite and Transform" service;
here we reuse the cairoblend + ``geometry`` PiP path for consistency with
``apply_pip`` (the closest existing machinery).
"""
from __future__ import annotations

from dataclasses import dataclass

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.pipelines.compositing import apply_composite

# layout name -> number of cells / tracks it requires
LAYOUTS: dict[str, int] = {"2h": 2, "2v": 2, "4": 4}

CROP_MODES: frozenset[str] = frozenset({"fit", "stretch"})


@dataclass(frozen=True)
class Cell:
    """A rectangular sub-region of the frame that one source is placed into."""

    x: int
    y: int
    width: int
    height: int

    def geometry(self, opacity: int = 100) -> str:
        """Render the MLT composite geometry string ``x/y:WxH:opacity``."""
        return f"{self.x}/{self.y}:{self.width}x{self.height}:{opacity}"


def _aspect_fit(
    cell_x: int, cell_y: int, cw: int, ch: int, src_w: int, src_h: int
) -> Cell:
    """Largest rect of source aspect that fits inside the cell, centred."""
    # Compare cell aspect (cw/ch) with source aspect (src_w/src_h) without float.
    if cw * src_h >= ch * src_w:
        # Cell is wider (or equal) than source aspect -> height-constrained.
        fh = ch
        fw = max(1, round(ch * src_w / src_h))
    else:
        # Cell is taller -> width-constrained.
        fw = cw
        fh = max(1, round(cw * src_h / src_w))
    fx = cell_x + (cw - fw) // 2
    fy = cell_y + (ch - fh) // 2
    return Cell(fx, fy, fw, fh)


def _base_cells(layout: str, width: int, height: int, gap_px: int) -> list[Cell]:
    """Full-cell (stretch) rectangles for a layout, honouring the gutter gap.

    Widths/heights consume any odd remainder on the trailing cell so the cells
    plus gaps always sum exactly to the frame dimension.
    """
    if layout == "2h":
        lw = (width - gap_px) // 2
        rw = width - gap_px - lw
        return [
            Cell(0, 0, lw, height),
            Cell(lw + gap_px, 0, rw, height),
        ]
    if layout == "2v":
        th = (height - gap_px) // 2
        bh = height - gap_px - th
        return [
            Cell(0, 0, width, th),
            Cell(0, th + gap_px, width, bh),
        ]
    # layout == "4"
    lw = (width - gap_px) // 2
    rw = width - gap_px - lw
    th = (height - gap_px) // 2
    bh = height - gap_px - th
    x2 = lw + gap_px
    y2 = th + gap_px
    return [
        Cell(0, 0, lw, th),    # top-left
        Cell(x2, 0, rw, th),   # top-right
        Cell(0, y2, lw, bh),   # bottom-left
        Cell(x2, y2, rw, bh),  # bottom-right
    ]


def compute_cells(
    layout: str,
    width: int,
    height: int,
    *,
    gap_px: int = 0,
    border_px: int = 0,
    crop: str = "fit",
) -> list[Cell]:
    """Compute one placement :class:`Cell` per track for ``layout``.

    Args:
        layout: one of :data:`LAYOUTS`.
        width, height: project profile dimensions in pixels.
        gap_px: gutter between adjacent cells (background shows through).
        border_px: uniform inset applied to *every* cell edge (outer frame and
            inner gutters), revealing the background as a border/frame.
        crop: ``"fit"`` (aspect-preserving, letterboxed) or ``"stretch"``
            (fill cell exactly, distorting aspect).

    Returns:
        Cells in layout order (2h: left,right / 2v: top,bottom / 4: TL,TR,BL,BR).

    Raises:
        ValueError: unknown layout/crop, non-positive dims, negative
            gap/border, or a gap/border so large a cell would collapse.
    """
    if layout not in LAYOUTS:
        raise ValueError(
            f"Unknown layout '{layout}'; valid layouts: {sorted(LAYOUTS)}"
        )
    if crop not in CROP_MODES:
        raise ValueError(
            f"Unknown crop '{crop}'; valid modes: {sorted(CROP_MODES)}"
        )
    if width <= 0 or height <= 0:
        raise ValueError(f"width/height must be positive (got {width}x{height})")
    if gap_px < 0 or border_px < 0:
        raise ValueError(
            f"gap_px/border_px must be >= 0 (got gap={gap_px}, border={border_px})"
        )

    cells = _base_cells(layout, width, height, gap_px)

    # Apply the uniform border inset on every edge of every cell.
    if border_px:
        cells = [
            Cell(
                c.x + border_px,
                c.y + border_px,
                c.width - 2 * border_px,
                c.height - 2 * border_px,
            )
            for c in cells
        ]

    for c in cells:
        if c.width <= 0 or c.height <= 0:
            raise ValueError(
                "gap_px/border_px too large for this profile -- a cell "
                f"collapsed to {c.width}x{c.height}"
            )

    if crop == "fit":
        # Preserve source aspect (assumed == profile aspect) inside each cell.
        cells = [
            _aspect_fit(c.x, c.y, c.width, c.height, width, height)
            for c in cells
        ]

    return cells


def apply_split_screen(
    project: KdenliveProject,
    layout: str,
    tracks: list[int],
    start_frame: int,
    end_frame: int,
    *,
    base_track: int = 0,
    crop: str = "fit",
    gap_px: int = 0,
    border_px: int = 0,
    opacity: int = 100,
) -> tuple[KdenliveProject, list[Cell]]:
    """Composite each track in ``tracks`` into its split/quad-screen cell.

    Geometry is computed from the project profile; each cell is placed over
    ``base_track`` by reusing :func:`compositing.apply_composite` (the same
    cairoblend + ``geometry`` path as ``apply_pip``).

    Returns the updated project and the list of cells (in track order).

    Raises:
        ValueError: track-count mismatch, duplicate/base-collision tracks,
            bad frame range, or any error from :func:`compute_cells`.
    """
    needed = LAYOUTS.get(layout)
    if needed is None:
        raise ValueError(
            f"Unknown layout '{layout}'; valid layouts: {sorted(LAYOUTS)}"
        )
    if len(tracks) != needed:
        raise ValueError(
            f"layout '{layout}' needs exactly {needed} tracks, got {len(tracks)}"
        )
    if len(set(tracks)) != len(tracks):
        raise ValueError(f"tracks must be distinct, got {tracks}")
    if base_track in tracks:
        raise ValueError(
            f"base_track ({base_track}) must not be one of the cell tracks {tracks}"
        )
    if end_frame <= start_frame:
        raise ValueError(
            f"end_frame ({end_frame}) must be greater than start_frame ({start_frame})"
        )

    cells = compute_cells(
        layout,
        project.profile.width,
        project.profile.height,
        gap_px=gap_px,
        border_px=border_px,
        crop=crop,
    )

    updated = project
    for track, cell in zip(tracks, cells):
        updated = apply_composite(
            updated,
            track_a=base_track,
            track_b=track,
            start_frame=start_frame,
            end_frame=end_frame,
            blend_mode="cairoblend",
            geometry=cell.geometry(opacity),
        )
    return updated, cells
