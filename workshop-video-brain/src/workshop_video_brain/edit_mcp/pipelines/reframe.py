"""Reframe a video to 9:16 / 1:1 / 4:5 / 16:9: crop, smart crop, pad or blur fill (prompt 33).

``smart`` picks a static focus from motion and detail energy, using ffmpeg
for the decode and pure Python for the maths (no numpy/OpenCV at runtime).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import ANALYSIS_TIMEOUT_SECONDS, run_ffmpeg
from workshop_video_brain.edit_mcp.pipelines.media_files import ENCODE_AUDIO_ARGS, ENCODE_VIDEO_ARGS, has_audio, require_streams

ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}
MODES = ("crop", "smart", "pad", "blur")


def _even(value: float) -> int:
    return int(value) // 2 * 2


def target_size(aspect: str, height: int = 0) -> tuple[int, int]:
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of {', '.join(ASPECTS)}, got {aspect!r}")
    w, h = ASPECTS[aspect]
    if height:
        return _even(w * height / h), _even(height)
    return w, h


def crop_box(src_w: int, src_h: int, aspect_w: int, aspect_h: int,
             focus_x: float = 0.5, focus_y: float = 0.5) -> tuple[int, int, int, int]:
    """The largest crop of the target aspect inside the source, centred on the focus, all even."""
    if src_w * aspect_h > src_h * aspect_w:  # source is wider than the target: crop width
        h = _even(src_h)
        w = _even(src_h * aspect_w / aspect_h)
    else:
        w = _even(src_w)
        h = _even(src_w * aspect_h / aspect_w)
    x = min(max(0.0, focus_x * src_w - w / 2), src_w - w)
    y = min(max(0.0, focus_y * src_h - h / 2), src_h - h)
    return _even(x), _even(y), w, h


def _best_window(profile: list[float], window: int) -> float:
    n = len(profile)
    if n == 0 or max(profile) - min(profile) < 1e-6:
        return 0.5
    window = max(1, min(window, n))
    current = sum(profile[:window])
    best, best_start = current, 0
    centre = (n - window) / 2
    for start in range(1, n - window + 1):
        current += profile[start + window - 1] - profile[start - 1]
        if current > best + 1e-9 or (abs(current - best) <= 1e-9 and abs(start - centre) < abs(best_start - centre)):
            best, best_start = current, start
    return (best_start + window / 2) / n


def best_focus_x(columns_energy: list[float], window: int) -> float:
    """Centre (fraction of the width) of the ``window`` columns with the most energy; 0.5 when flat."""
    return _best_window(columns_energy, window)


def best_focus_y(rows_energy: list[float], window: int) -> float:
    return _best_window(rows_energy, window)


def column_energy(frames: list[bytes], w: int, h: int) -> list[float]:
    """Per column: frame-to-frame motion plus 0.25 x horizontal detail, over 8-bit gray frames."""
    energy = [0.0] * w
    previous = None
    for frame in frames:
        for y in range(h):
            row = frame[y * w:(y + 1) * w]
            for x in range(w):
                value = row[x]
                if previous is not None:
                    energy[x] += abs(value - previous[y * w + x])
                if x + 1 < w:
                    energy[x] += 0.25 * abs(row[x + 1] - value)
        previous = frame
    return energy


def row_energy(frames: list[bytes], w: int, h: int) -> list[float]:
    """:func:`column_energy` along the other axis (motion + vertical detail per row)."""
    transposed = [bytes(frame[y * w + x] for x in range(w) for y in range(h)) for frame in frames]
    return column_energy(transposed, h, w)


def filter_for(mode: str, src_w: int, src_h: int, out_w: int, out_h: int,
               focus_x: float = 0.5, focus_y: float = 0.5, pad_color: str = "black") -> str:
    if mode in ("crop", "smart"):
        x, y, w, h = crop_box(src_w, src_h, out_w, out_h, focus_x, focus_y)
        return f"crop={w}:{h}:{x}:{y},scale={out_w}:{out_h},setsar=1"
    if mode == "pad":
        return (f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color={pad_color},setsar=1")
    if mode == "blur":
        return (f"split=2[a][b];[a]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},boxblur=20:5[bg];[b]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    raise ValueError(f"mode must be one of {', '.join(MODES)}, got {mode!r}")


def analyse_focus(source: Path, start: float = 0.0, duration: float | None = None, samples_fps: float = 2.0,
                  analysis_width: int = 160, max_frames: int = 120, out_w: int = 9,
                  out_h: int = 16) -> tuple[float, float, int, int]:
    """(focus_x, focus_y, analysis_w, analysis_h) from motion + detail energy of sampled gray frames."""
    asset = probe_media(source)
    aw = analysis_width
    ah = _even(asset.height * aw / asset.width) if asset.width else aw
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(source), "-vf", f"fps={samples_fps:g},scale={aw}:{ah},format=gray",
            "-frames:v", str(max_frames), "-f", "rawvideo", "pipe:1"]
    raw = subprocess.run(cmd, capture_output=True, timeout=ANALYSIS_TIMEOUT_SECONDS, check=False).stdout
    size = aw * ah
    frames = [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]
    if not frames:
        return 0.5, 0.5, aw, ah
    # The crop window, in analysis pixels, for the target aspect.
    return best_focus_x(column_energy(frames, aw, ah), max(1, round(ah * out_w / out_h))), \
        best_focus_y(row_energy(frames, aw, ah), max(1, round(aw * out_h / out_w))), aw, ah


def reframe_file(source: Path, output: Path, aspect: str = "9:16", mode: str = "smart", focus_x: float = 0.5,
                 focus_y: float = 0.5, height: int = 0, start: float = 0.0, duration: float | None = None,
                 pad_color: str = "black") -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}, got {mode!r}")
    out_w, out_h = target_size(aspect, height)
    asset = probe_media(source)
    require_streams(asset, video=True)
    if asset.duration_seconds and start >= asset.duration_seconds:
        raise ValueError(f"start {start:.3f}s is past the end of the source ({asset.duration_seconds:.3f}s)")
    if mode == "smart":
        focus_x, focus_y, _aw, _ah = analyse_focus(source, start, duration, out_w=out_w, out_h=out_h)
    vf = filter_for(mode, asset.width, asset.height, out_w, out_h, focus_x, focus_y, pad_color)
    args = (["-t", f"{duration:.3f}"] if duration else [])
    if mode == "blur":
        args += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
        if has_audio(asset):
            args += ["-map", "0:a"]
    else:
        args += ["-vf", vf]
    args += ENCODE_VIDEO_ARGS + (ENCODE_AUDIO_ARGS if has_audio(asset) else ["-an"])
    result = run_ffmpeg(args, source, output, overwrite=True, pre_input_args=["-hide_banner", "-ss", f"{start:.3f}"])
    crop = crop_box(asset.width, asset.height, out_w, out_h, focus_x, focus_y) if mode in ("crop", "smart") else None
    return {"result": result, "mode": mode, "focus_x": round(focus_x, 3), "focus_y": round(focus_y, 3),
            "crop": crop, "out_size": (out_w, out_h)}
