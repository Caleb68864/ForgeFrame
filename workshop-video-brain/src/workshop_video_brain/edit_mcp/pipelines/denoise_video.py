"""One-call video denoise built on FFmpeg's ``hqdn3d`` / ``atadenoise``.

Cleans high-ISO / low-light grain. Mirrors ``pipelines/stabilize.py``: pure
command-construction helpers plus an orchestrating function that runs FFmpeg
via ``adapters/ffmpeg/runner.run_ffmpeg`` and returns a plain result ``dict``.

Two methods:

* ``hqdn3d`` -- high-quality spatial + temporal 3-D denoise. Takes four knobs:
  ``luma_spatial:chroma_spatial:luma_tmp:chroma_tmp``. Larger = more smoothing.
  FFmpeg's own default is ``4:3:6:4.5``, used here for the ``medium`` preset.
* ``atadenoise`` -- adaptive temporal denoise; per-frame (``0a``) and
  accumulated (``0b``) thresholds scale with strength.

Writes a new file to ``media/processed/`` (never touches ``media/raw``) and
stream-copies the audio track so only the video is re-encoded.
"""
from __future__ import annotations

import logging
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegResult,
    run_ffmpeg,
)

logger = logging.getLogger(__name__)

# Suffix appended to the source stem for the denoised output.
_OUTPUT_SUFFIX = "_denoised"

# Video encode settings for the render pass -- match stabilize.py / proxy.py
# conventions (libx264, sane CRF) and copy the audio stream through untouched.
_ENCODE_ARGS: list[str] = ["-c:v", "libx264", "-crf", "18", "-c:a", "copy"]

_DEFAULT_STRENGTH = "medium"
_DEFAULT_METHOD = "hqdn3d"

# hqdn3d presets: luma_spatial : chroma_spatial : luma_tmp : chroma_tmp.
# "medium" == FFmpeg's built-in default (4:3:6:4.5).
_HQDN3D_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "light": (2.0, 1.5, 3.0, 2.25),
    "medium": (4.0, 3.0, 6.0, 4.5),
    "strong": (8.0, 6.0, 12.0, 9.0),
}

# atadenoise presets: per-frame threshold (0a) and accumulated threshold (0b).
# Larger thresholds allow more averaging => stronger denoise.
_ATADENOISE_PRESETS: dict[str, tuple[float, float]] = {
    "light": (0.01, 0.02),
    "medium": (0.02, 0.04),
    "strong": (0.04, 0.08),
}

_METHODS = ("hqdn3d", "atadenoise")


def _norm_strength(strength: str) -> str:
    """Normalize/validate a strength preset name, defaulting to ``medium``."""
    s = (strength or "").strip().lower()
    return s if s in _HQDN3D_PRESETS else _DEFAULT_STRENGTH


def _norm_method(method: str) -> str:
    """Normalize/validate a method name, defaulting to ``hqdn3d``."""
    m = (method or "").strip().lower()
    return m if m in _METHODS else _DEFAULT_METHOD


# ---------------------------------------------------------------------------
# Filter-string construction (pure)
# ---------------------------------------------------------------------------

def build_hqdn3d_filter(strength: str = _DEFAULT_STRENGTH) -> str:
    """Build an ``hqdn3d`` filter string for the given strength preset."""
    ls, cs, lt, ct = _HQDN3D_PRESETS[_norm_strength(strength)]
    return f"hqdn3d={ls}:{cs}:{lt}:{ct}"


def build_atadenoise_filter(strength: str = _DEFAULT_STRENGTH) -> str:
    """Build an ``atadenoise`` filter string for the given strength preset."""
    a, b = _ATADENOISE_PRESETS[_norm_strength(strength)]
    return f"atadenoise=0a={a}:0b={b}"


def build_denoise_filter(
    strength: str = _DEFAULT_STRENGTH,
    method: str = _DEFAULT_METHOD,
) -> str:
    """Build the denoise ``-vf`` string, dispatching on *method*."""
    if _norm_method(method) == "atadenoise":
        return build_atadenoise_filter(strength)
    return build_hqdn3d_filter(strength)


def denoise_params(
    strength: str = _DEFAULT_STRENGTH,
    method: str = _DEFAULT_METHOD,
) -> dict:
    """Return the resolved {strength, method, filter, values} for reporting."""
    s = _norm_strength(strength)
    m = _norm_method(method)
    if m == "atadenoise":
        values = list(_ATADENOISE_PRESETS[s])
    else:
        values = list(_HQDN3D_PRESETS[s])
    return {
        "strength": s,
        "method": m,
        "filter": build_denoise_filter(s, m),
        "values": values,
    }


def denoised_output_path(
    source: Path,
    output_dir: Path,
    output_name: str | None = None,
) -> Path:
    """Compute the destination path for a denoised render.

    Defaults to ``{stem}_denoised{suffix}`` inside *output_dir*. A custom
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
# Orchestrating chain
# ---------------------------------------------------------------------------

def denoise_video_file(
    input_path: Path,
    output_path: Path,
    strength: str = _DEFAULT_STRENGTH,
    method: str = _DEFAULT_METHOD,
    dry_run: bool = False,
) -> dict:
    """Denoise a video file, writing a new file to *output_path*.

    Applies ``hqdn3d`` (spatial+temporal) or ``atadenoise`` (temporal) and
    re-encodes video with libx264/CRF 18, copying the audio stream through
    untouched. The source is never modified.

    Args:
        input_path: Source video file (never modified).
        output_path: Destination file in ``media/processed/``.
        strength: ``light`` | ``medium`` | ``strong`` (default ``medium``).
        method: ``hqdn3d`` | ``atadenoise`` (default ``hqdn3d``).
        dry_run: Return the constructed command without executing.

    Returns:
        Dict with: ``success``, ``method``, ``strength``, ``filter``,
        ``params``, ``steps`` (FFmpegResult dicts), ``final_output``, and on
        failure ``error``.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    params = denoise_params(strength, method)
    vf = params["filter"]

    result = run_ffmpeg(
        ["-vf", vf, *_ENCODE_ARGS],
        input_path=input_path,
        output_path=output_path,
        overwrite=True,
        dry_run=dry_run,
    )
    steps: list[FFmpegResult] = [result]

    if not result.success and not dry_run:
        return {
            "success": False,
            "method": params["method"],
            "strength": params["strength"],
            "filter": vf,
            "params": params,
            "steps": [s.model_dump() for s in steps],
            "final_output": None,
            "error": f"Denoise failed: {result.stderr[-300:]}",
        }

    return {
        "success": True,
        "method": params["method"],
        "strength": params["strength"],
        "filter": vf,
        "params": params,
        "steps": [s.model_dump() for s in steps],
        "final_output": str(output_path),
    }
