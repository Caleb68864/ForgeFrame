"""Video stabilization pipeline built on FFmpeg's vidstab (two-pass).

Mirrors the file-level audio processing tools in
``adapters/ffmpeg/audio.py``: pure command-construction helpers plus an
orchestrating chain function that runs FFmpeg via
``adapters/ffmpeg/runner.run_ffmpeg`` and returns a plain result ``dict``.

Two routes exist for stabilization in this project:

* **Kdenlive clip-job route** -- the editor runs ``vidstabdetect`` /
  ``vidstabtransform`` as a *clip job* on a bin clip and stores a
  ``.trf`` beside the media. That path lives inside Kdenlive and is not
  automated here.
* **File-level ffmpeg route (this module)** -- a standalone two-pass
  ``vidstabdetect`` -> ``vidstabtransform`` render that writes a new,
  already-stabilized file to ``media/processed/``. This is the route the
  ``media_stabilize`` MCP tool exposes.

If ``libvidstab`` is missing from the local FFmpeg build we fall back to
the always-available single-pass ``deshake`` filter and report which
method was used.
"""
from __future__ import annotations

import functools
import logging
import subprocess
import tempfile
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegResult,
    run_ffmpeg,
)

logger = logging.getLogger(__name__)

# Suffix appended to the source stem for the stabilized output (mirrors the
# ``_proxy`` / ``_cfr`` conventions used elsewhere in the ffmpeg adapters).
_OUTPUT_SUFFIX = "_stabilized"

# Video encode settings for the render pass -- match proxy.py conventions
# (libx264, sane CRF) and copy the audio stream through untouched.
_ENCODE_ARGS: list[str] = ["-c:v", "libx264", "-crf", "18", "-c:a", "copy"]


# ---------------------------------------------------------------------------
# Parameter clamping
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* into the inclusive ``[lo, hi]`` range."""
    return max(lo, min(hi, value))


def clamp_params(
    shakiness: int = 5,
    smoothing: int = 15,
    accuracy: int = 15,
    zoom: int = 0,
) -> dict[str, int]:
    """Clamp stabilization parameters to the ranges vidstab accepts.

    * ``shakiness`` -- 1..10 (vidstabdetect)
    * ``smoothing`` -- 0..100 frames (vidstabtransform)
    * ``accuracy``  -- 1..15 (vidstabdetect; must be >= shakiness ideally)
    * ``zoom``      -- -100..100 percent (vidstabtransform)

    Returns a new dict of ints; never mutates its inputs.
    """
    return {
        "shakiness": int(_clamp(shakiness, 1, 10)),
        "smoothing": int(_clamp(smoothing, 0, 100)),
        "accuracy": int(_clamp(accuracy, 1, 15)),
        "zoom": int(_clamp(zoom, -100, 100)),
    }


# ---------------------------------------------------------------------------
# Filter-string construction (pure)
# ---------------------------------------------------------------------------

def build_detect_filter(
    trf_path: Path,
    shakiness: int = 5,
    accuracy: int = 15,
) -> str:
    """Build the pass-1 ``vidstabdetect`` filter string.

    Writes the detected transforms to *trf_path* (the ``result=`` option).
    """
    p = clamp_params(shakiness=shakiness, accuracy=accuracy)
    return (
        f"vidstabdetect=shakiness={p['shakiness']}"
        f":accuracy={p['accuracy']}"
        f":result={trf_path}"
    )


def build_transform_filter(
    trf_path: Path,
    smoothing: int = 15,
    zoom: int = 0,
) -> str:
    """Build the pass-2 ``vidstabtransform`` filter string.

    Reads the transforms from *trf_path* (the ``input=`` option) and adds a
    light ``unsharp`` to recover softness introduced by the warp.
    """
    p = clamp_params(smoothing=smoothing, zoom=zoom)
    return (
        f"vidstabtransform=input={trf_path}"
        f":smoothing={p['smoothing']}"
        f":zoom={p['zoom']}"
        ",unsharp=5:5:0.8"
    )


def build_deshake_filter(zoom: int = 0) -> str:
    """Build the single-pass ``deshake`` filter string (vidstab fallback)."""
    # deshake has no smoothing/shakiness knobs; edge=1 fills borders with a
    # mirrored image, roughly analogous to a small vidstab zoom.
    return "deshake=edge=1"


def stabilized_output_path(
    source: Path,
    output_dir: Path,
    output_name: str | None = None,
) -> Path:
    """Compute the destination path for a stabilized render.

    Defaults to ``{stem}_stabilized{suffix}`` inside *output_dir*. A custom
    *output_name* is used as-is (its suffix defaults to the source's).
    """
    source = Path(source)
    if output_name:
        name = output_name
        if not Path(name).suffix:
            name = f"{name}{source.suffix}"
        return Path(output_dir) / name
    return Path(output_dir) / f"{source.stem}{_OUTPUT_SUFFIX}{source.suffix}"


# ---------------------------------------------------------------------------
# libvidstab availability probe
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def vidstab_available() -> bool:
    """Return True if the local FFmpeg build exposes the vidstab filters.

    Result is cached; both ``vidstabdetect`` and ``vidstabtransform`` must be
    present. Any probe failure (ffmpeg missing, error) returns False so the
    caller falls back to ``deshake``.
    """
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return False
    out = proc.stdout
    return "vidstabdetect" in out and "vidstabtransform" in out


# ---------------------------------------------------------------------------
# Orchestrating chain
# ---------------------------------------------------------------------------

def stabilize_file(
    input_path: Path,
    output_path: Path,
    shakiness: int = 5,
    smoothing: int = 15,
    accuracy: int = 15,
    zoom: int = 0,
    force_deshake: bool = False,
    dry_run: bool = False,
) -> dict:
    """Stabilize a video file, writing a new file to *output_path*.

    Uses two-pass vidstab (``vidstabdetect`` -> ``vidstabtransform``) when
    ``libvidstab`` is available, storing the intermediate ``.trf`` transforms
    file in a temporary directory. Falls back to the single-pass ``deshake``
    filter otherwise (or when *force_deshake* is True).

    Args:
        input_path: Source video file (never modified).
        output_path: Destination file in ``media/processed/``.
        shakiness: Detection shakiness, 1..10 (default 5).
        smoothing: Transform smoothing window in frames, 0..100 (default 15).
        accuracy: Detection accuracy, 1..15 (default 15).
        zoom: Transform zoom percentage, -100..100 (default 0).
        force_deshake: Skip vidstab and use ``deshake`` (used for testing /
            explicit fallback).
        dry_run: Return the constructed commands without executing.

    Returns:
        Dict with: ``success``, ``method`` ("vidstab" | "deshake"),
        ``steps`` (list of ``FFmpegResult`` dicts), ``final_output``,
        ``params`` (the clamped params actually used), and, on failure,
        ``error``.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    params = clamp_params(
        shakiness=shakiness, smoothing=smoothing, accuracy=accuracy, zoom=zoom
    )

    use_vidstab = vidstab_available() and not force_deshake
    method = "vidstab" if use_vidstab else "deshake"

    steps: list[FFmpegResult] = []

    if use_vidstab:
        with tempfile.TemporaryDirectory(prefix="vidstab_") as tmp:
            trf = Path(tmp) / f"{input_path.stem}.trf"

            # Pass 1: detect motion -> write .trf, discard the video output.
            detect = run_ffmpeg(
                ["-vf", build_detect_filter(trf, params["shakiness"], params["accuracy"]),
                 "-f", "null"],
                input_path=input_path,
                output_path=Path("/dev/null"),
                overwrite=True,
                dry_run=dry_run,
            )
            steps.append(detect)
            if not detect.success and not dry_run:
                return _fail(steps, method, params, "vidstabdetect (pass 1) failed")

            # Pass 2: apply the smoothed transform + re-encode.
            transform = run_ffmpeg(
                ["-vf", build_transform_filter(trf, params["smoothing"], params["zoom"]),
                 *_ENCODE_ARGS],
                input_path=input_path,
                output_path=output_path,
                overwrite=True,
                dry_run=dry_run,
            )
            steps.append(transform)
            if not transform.success and not dry_run:
                return _fail(steps, method, params, "vidstabtransform (pass 2) failed")
    else:
        deshake = run_ffmpeg(
            ["-vf", build_deshake_filter(params["zoom"]), *_ENCODE_ARGS],
            input_path=input_path,
            output_path=output_path,
            overwrite=True,
            dry_run=dry_run,
        )
        steps.append(deshake)
        if not deshake.success and not dry_run:
            return _fail(steps, method, params, "deshake failed")

    return {
        "success": True,
        "method": method,
        "steps": [s.model_dump() for s in steps],
        "final_output": str(output_path),
        "params": params,
    }


def _fail(
    steps: list[FFmpegResult],
    method: str,
    params: dict,
    error: str,
    error_type: str = "operation_failed",
) -> dict:
    # ``error_type`` is a stable machine key (matching server/errors.py taxonomy)
    # the bundle layer passes straight through to its error contract, so an
    # ffmpeg command failure here is classified rather than re-wrapped untyped.
    return {
        "success": False,
        "method": method,
        "steps": [s.model_dump() for s in steps],
        "final_output": None,
        "params": params,
        "error": error,
        "error_type": error_type,
    }
