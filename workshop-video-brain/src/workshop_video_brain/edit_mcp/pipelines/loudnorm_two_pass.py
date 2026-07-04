"""Two-pass EBU R128 loudness normalization built on FFmpeg's ``loudnorm``.

Upgrades the single-pass ``adapters/ffmpeg/audio.normalize_audio`` to the
accurate *measured* two-pass form: measure the source first, then feed the
measured values back into a second ``loudnorm`` pass with ``linear=true``.

Mirrors the file-level style of ``pipelines/stabilize.py``: pure
command-construction helpers plus an orchestrating function that runs FFmpeg
via ``adapters/ffmpeg/runner.run_ffmpeg`` and returns a plain result ``dict``.

The pass-1 integrated / true-peak / loudness-range measurement is delegated to
the existing ``adapters/ffmpeg/probe.measure_loudness`` (never modified here).
``loudnorm``'s second pass additionally wants the measured *threshold*, which
``measure_loudness`` does not expose, so a tiny supplementary ``_measure_thresh``
reads it from the same ``print_format=json`` output.

Works on both audio-only files and video files: when the source carries a video
stream the video is stream-copied (``-c:v copy``) and only the audio is
re-encoded through the normalized filter, so nothing but the audio is touched.

``linear=true`` is always requested; ``loudnorm`` itself decides whether a purely
linear gain is possible (it is not when the required gain would push the true
peak past the target, or for material with no measurable loudness range) and
silently falls back to dynamic normalization. This module reads the pass-2
``normalization_type`` back out and surfaces a warning when the applied mode was
dynamic rather than the requested linear.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import (
    LoudnessResult,
    has_video_stream,
    measure_loudness,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegResult,
    run_ffmpeg,
)

logger = logging.getLogger(__name__)

# Suffix appended to the source stem for the normalized output (mirrors the
# ``_stabilized`` / ``_proxy`` / ``_cfr`` conventions used elsewhere).
_OUTPUT_SUFFIX = "_normalized"

# Regex matching a loudnorm JSON block (no nested braces in loudnorm output).
_JSON_RE = re.compile(r'\{[^{}]*"input_i"[^{}]*\}', re.DOTALL)


# ---------------------------------------------------------------------------
# Filter-string construction (pure)
# ---------------------------------------------------------------------------

def build_loudnorm_pass2_filter(
    target_i: float,
    target_tp: float,
    target_lra: float,
    measured_i: float,
    measured_tp: float,
    measured_lra: float,
    measured_thresh: float,
    linear: bool = True,
    print_format: str = "json",
) -> str:
    """Build the pass-2 ``loudnorm`` filter string in the measured two-pass form.

    Produces exactly::

        loudnorm=I=<ti>:TP=<ttp>:LRA=<tlra>:measured_I=<mi>:measured_TP=<mtp>
                 :measured_LRA=<mlra>:measured_thresh=<mth>:linear=true
                 :print_format=json

    ``linear`` is emitted as a lowercase ``true``/``false`` literal. Requesting
    ``linear=true`` is advisory -- ``loudnorm`` downgrades to dynamic on its own
    when a linear gain is not achievable.
    """
    return (
        f"loudnorm=I={target_i}"
        f":TP={target_tp}"
        f":LRA={target_lra}"
        f":measured_I={measured_i}"
        f":measured_TP={measured_tp}"
        f":measured_LRA={measured_lra}"
        f":measured_thresh={measured_thresh}"
        f":linear={'true' if linear else 'false'}"
        f":print_format={print_format}"
    )


def normalized_output_path(
    source: Path,
    output_dir: Path,
    output_name: str | None = None,
) -> Path:
    """Compute the destination path for a normalized render.

    Defaults to ``{stem}_normalized{suffix}`` inside *output_dir*. A custom
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
# Probing helpers
# ---------------------------------------------------------------------------

def _measure_thresh(path: Path) -> float | None:
    """Read the measured loudness *threshold* (``input_thresh``) from loudnorm.

    ``measure_loudness`` in ``probe.py`` intentionally exposes only I/TP/LRA;
    the two-pass second stage additionally needs ``measured_thresh``. This runs
    the same ``loudnorm=print_format=json`` analysis pass and extracts it.
    Returns ``None`` on any failure.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(path),
                "-af", "loudnorm=print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        match = _JSON_RE.search(result.stderr)
        if match:
            data = json.loads(match.group())
            return float(data.get("input_thresh", 0.0))
        return None
    except Exception:  # noqa: BLE001
        logger.warning("Threshold measurement failed for %s", path)
        return None


def _has_video_stream(path: Path) -> bool:
    """Return True if *path* contains at least one video stream (ffprobe).

    Thin delegate to the shared ``adapters/ffmpeg/probe.has_video_stream``; the
    adapter returns ``None`` when it cannot tell (ffprobe missing/errored), which
    this collapses to ``False`` to preserve the original bool contract (treat
    "unknown" as audio-only). Kept as a module-local name because the loudnorm
    tests monkeypatch ``_has_video_stream`` directly.
    """
    return has_video_stream(path) is True


def parse_pass2_result(stderr: str) -> dict:
    """Parse the pass-2 loudnorm JSON block out of FFmpeg stderr.

    Returns a dict with ``output_i`` (float | None), ``output_tp``,
    ``normalization_type`` ("linear" | "dynamic" | None), and ``raw`` (the
    parsed JSON, or ``{}``). Missing/failed parse yields Nones.
    """
    match = _JSON_RE.search(stderr)
    if not match:
        return {
            "output_i": None,
            "output_tp": None,
            "normalization_type": None,
            "raw": {},
        }
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return {
            "output_i": None,
            "output_tp": None,
            "normalization_type": None,
            "raw": {},
        }

    def _f(key: str) -> float | None:
        val = data.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "output_i": _f("output_i"),
        "output_tp": _f("output_tp"),
        "normalization_type": data.get("normalization_type"),
        "raw": data,
    }


# ---------------------------------------------------------------------------
# Orchestrating chain
# ---------------------------------------------------------------------------

def normalize_two_pass_file(
    input_path: Path,
    output_path: Path,
    target_i: float = -16.0,
    target_tp: float = -1.5,
    target_lra: float = 11.0,
    linear: bool = True,
    dry_run: bool = False,
) -> dict:
    """Two-pass loudnorm a file, writing a normalized copy to *output_path*.

    Pass 1 measures loudness (via ``probe.measure_loudness`` + a threshold read);
    pass 2 applies ``loudnorm`` with the measured values fed back and
    ``linear=true``. Video streams are copied through untouched; only audio is
    re-encoded.

    Args:
        input_path: Source audio/video file (never modified).
        output_path: Destination file in ``media/processed/``.
        target_i: Target integrated loudness in LUFS (default -16.0).
        target_tp: Target maximum true peak in dBTP (default -1.5).
        target_lra: Target loudness range in LU (default 11.0).
        linear: Request linear normalization (default True). loudnorm may still
            fall back to dynamic; the applied mode is reported.
        dry_run: Construct the command without executing (skips measurement).

    Returns:
        Dict with: ``success``, ``measured`` (i/tp/lra/thresh), ``target``
        (i/tp/lra), ``normalization_type``, ``linear_requested``,
        ``linear_applied``, ``achieved_i`` (re-measured output integrated LUFS),
        ``has_video``, ``warning`` (or None), ``steps`` (FFmpegResult dicts),
        ``final_output``, and on failure ``error``.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    has_video = _has_video_stream(input_path)

    target = {"i": target_i, "tp": target_tp, "lra": target_lra}

    if dry_run:
        af = build_loudnorm_pass2_filter(
            target_i, target_tp, target_lra,
            measured_i=0.0, measured_tp=0.0, measured_lra=0.0,
            measured_thresh=0.0, linear=linear,
        )
        args = (["-c:v", "copy"] if has_video else []) + ["-af", af]
        step = run_ffmpeg(
            args, input_path=input_path, output_path=output_path,
            overwrite=True, dry_run=True,
        )
        return {
            "success": True,
            "measured": None,
            "target": target,
            "normalization_type": None,
            "linear_requested": linear,
            "linear_applied": None,
            "achieved_i": None,
            "has_video": has_video,
            "warning": None,
            "steps": [step.model_dump()],
            "final_output": str(output_path),
        }

    # Pass 1 -- measurement (reuse the existing probe adapter).
    measurement: LoudnessResult | None = measure_loudness(input_path)
    if measurement is None:
        return _fail(
            [], target, has_video, linear,
            "Pass-1 loudness measurement failed (measure_loudness returned None)",
            error_type="media_unreadable",
        )
    thresh = _measure_thresh(input_path)
    if thresh is None:
        return _fail(
            [], target, has_video, linear,
            "Pass-1 threshold measurement failed",
            error_type="media_unreadable",
        )

    measured = {
        "i": measurement.input_i,
        "tp": measurement.input_tp,
        "lra": measurement.input_lra,
        "thresh": thresh,
    }

    # Pass 2 -- apply loudnorm with the measured values fed back.
    af = build_loudnorm_pass2_filter(
        target_i, target_tp, target_lra,
        measured_i=measurement.input_i,
        measured_tp=measurement.input_tp,
        measured_lra=measurement.input_lra,
        measured_thresh=thresh,
        linear=linear,
    )
    args = (["-c:v", "copy"] if has_video else []) + ["-af", af]
    apply_result = run_ffmpeg(
        args, input_path=input_path, output_path=output_path,
        overwrite=True, dry_run=False,
    )
    steps: list[FFmpegResult] = [apply_result]
    if not apply_result.success:
        return _fail(
            steps, target, has_video, linear,
            f"Pass-2 loudnorm apply failed: {apply_result.stderr[-300:]}",
            measured=measured,
            error_type="operation_failed",
        )

    parsed = parse_pass2_result(apply_result.stderr)
    norm_type = parsed["normalization_type"]
    linear_applied = norm_type == "linear"

    warning = None
    if linear and not linear_applied:
        warning = (
            "Linear normalization was requested but loudnorm applied "
            f"'{norm_type or 'unknown'}' normalization instead (linear gain not "
            "achievable for this material -- e.g. it would exceed the target "
            "true peak, or the material has no measurable loudness range)."
        )

    return {
        "success": True,
        "measured": measured,
        "target": target,
        "normalization_type": norm_type,
        "linear_requested": linear,
        "linear_applied": linear_applied,
        "achieved_i": parsed["output_i"],
        "has_video": has_video,
        "warning": warning,
        "steps": [s.model_dump() for s in steps],
        "final_output": str(output_path),
    }


def _fail(
    steps: list[FFmpegResult],
    target: dict,
    has_video: bool,
    linear: bool,
    error: str,
    measured: dict | None = None,
    error_type: str = "operation_failed",
) -> dict:
    # ``error_type``: stable machine key (server/errors.py taxonomy) the bundle
    # passes through -- measurement failures are media_unreadable, an apply-pass
    # nonzero exit is operation_failed.
    return {
        "success": False,
        "measured": measured,
        "target": target,
        "normalization_type": None,
        "linear_requested": linear,
        "linear_applied": None,
        "achieved_i": None,
        "has_video": has_video,
        "warning": None,
        "steps": [s.model_dump() for s in steps],
        "final_output": None,
        "error": error,
        "error_type": error_type,
    }
