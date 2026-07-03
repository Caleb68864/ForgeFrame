"""External-truth helpers for the melt-oracle harness.

This module is the load-bearing layer: it shells out to real ``melt`` and
``ffprobe`` and extracts truth that cannot be produced by our own parser and
serializer agreeing with each other.

It imports **nothing** from the effect stack / models -- it only knows about
files on disk, subprocess exit codes, decoded pixels, and container metadata.
That keeps its functions liftable into a future runtime ``validate_project()``
service without rework.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------------------
# melt acceptance
# ---------------------------------------------------------------------------

# Substrings of stderr lines that are non-fatal noise on this / typical MLT
# builds (optional module dlopen failures, ffmpeg deprecation chatter). Lines
# containing any of these are dropped before scanning for real errors.
_IGNORE_LINE_SUBSTR = (
    "dlopen",
    "shared object",
    "mlt_repository_init",
    "deprecated",
    "swscaler",
    "[image2",
    "current frame",
    "libmovit",
    "librtaudio",
    "libsox",
)

# Substrings that indicate a genuine load / parse failure. melt frequently
# exits 0 even when it fails to load a producer, so stderr scanning -- not the
# exit code alone -- is what classifies acceptance. Keep this list small and
# curated; widen only with evidence (see design "Risks").
_FATAL_SUBSTR = (
    "failed to load",
    "could not load",
    "cannot load",
    "parse error",
    "invalid producer",
    "syntax error",
    "no such producer",
)

# Every project our serializer writes contains a black_track producer with
# out=2147483646, so an unbounded ``-consumer null:`` would try to process ~2
# billion frames and hang. We always bound the run with ``out=<frames-1>``.
DEFAULT_ACCEPT_FRAMES = 25


@dataclass
class OracleResult:
    """Outcome of a melt acceptance check."""

    ok: bool
    returncode: int
    stderr: str = ""
    stdout: str = ""

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.ok


def _classify_stderr(stderr: str) -> str | None:
    """Return the first fatal error line found in *stderr*, else None."""
    for raw in stderr.splitlines():
        line = raw.strip().lower()
        if not line:
            continue
        if any(sub in line for sub in _IGNORE_LINE_SUBSTR):
            continue
        if any(sub in line for sub in _FATAL_SUBSTR):
            return raw.strip()
    return None


def melt_accepts(
    project_path: str | Path,
    melt_bin: str = "melt",
    frames: int = DEFAULT_ACCEPT_FRAMES,
    timeout: int = 60,
) -> OracleResult:
    """Validate that *project_path* loads and processes in real melt.

    Runs ``melt {path} out={frames-1} -consumer null:`` -- the null consumer
    processes frames but writes nothing, so it is fast. Acceptance fails on a
    non-zero exit code OR a fatal error substring in stderr (melt can exit 0
    while emitting a load failure).
    """
    project_path = Path(project_path)
    out = max(0, frames - 1)
    cmd = [melt_bin, str(project_path), f"out={out}", "-consumer", "null:"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        return OracleResult(
            ok=False, returncode=-1, stderr=f"melt timed out after {timeout}s: {exc}"
        )

    fatal = _classify_stderr(proc.stderr)
    ok = proc.returncode == 0 and fatal is None
    stderr = proc.stderr if fatal is None else f"FATAL LINE: {fatal}\n---\n{proc.stderr}"
    return OracleResult(
        ok=ok, returncode=proc.returncode, stderr=stderr, stdout=proc.stdout
    )


# ---------------------------------------------------------------------------
# single-frame render
# ---------------------------------------------------------------------------


def render_frame(
    project_path: str | Path,
    frame: int,
    out_dir: str | Path,
    melt_bin: str = "melt",
    timeout: int = 120,
    name: str | None = None,
) -> Path:
    """Render exactly one frame of *project_path* to a PNG and return its path.

    Uses ``melt {path} in={N} out={N} -consumer avformat:{png} -update 1``,
    which reuses the profile embedded in the project file.
    """
    project_path = Path(project_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / (name or f"{project_path.stem}_f{frame}.png")
    png.unlink(missing_ok=True)

    cmd = [
        melt_bin,
        str(project_path),
        f"in={frame}",
        f"out={frame}",
        "-consumer",
        f"avformat:{png}",
        "-update",
        "1",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if not png.exists():
        raise RuntimeError(
            f"render_frame produced no output for {project_path} frame {frame}.\n"
            f"returncode={proc.returncode}\nstderr tail:\n{proc.stderr[-1500:]}"
        )
    return png


def render_video(
    project_path: str | Path,
    out_path: str | Path,
    frames: int,
    melt_bin: str = "melt",
    vcodec: str = "libx264",
    acodec: str = "aac",
    timeout: int = 180,
) -> Path:
    """Render the first *frames* frames of *project_path* to a media file."""
    project_path = Path(project_path)
    out_path = Path(out_path)
    out_path.unlink(missing_ok=True)
    cmd = [
        melt_bin,
        str(project_path),
        f"out={max(0, frames - 1)}",
        "-consumer",
        f"avformat:{out_path}",
        f"vcodec={vcodec}",
        f"acodec={acodec}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if not out_path.exists():
        raise RuntimeError(
            f"render_video produced no output for {project_path}.\n"
            f"returncode={proc.returncode}\nstderr tail:\n{proc.stderr[-1500:]}"
        )
    return out_path


# ---------------------------------------------------------------------------
# perceptual / differential frame comparison
# ---------------------------------------------------------------------------

# Downscaled grid edge used for both the average hash and the colour
# fingerprint. Differential (not golden) comparison keeps the tests robust
# across melt/codec/distro versions.
_HASH_EDGE = 8
_FINGERPRINT_EDGE = 16

# Mean per-channel absolute difference (0-255 scale) thresholds.
DIFFER_MIN_DELTA = 10.0   # frames are "different" above this
SIMILAR_MAX_DELTA = 4.0   # frames are "similar" at/below this


def _open_rgb(png_path: str | Path) -> Image.Image:
    return Image.open(png_path).convert("RGB")


def frame_hash(png_path: str | Path) -> int:
    """Average hash (aHash) of a frame as a 64-bit int.

    Grayscale, downscaled to 8x8; each bit is pixel > mean. Useful for
    structural comparison via :func:`hamming_distance`. Note: solid-colour
    frames all hash to 0, so colour-sensitive tests should use
    :func:`frames_differ` / :func:`frames_similar`, which fold in colour.
    """
    im = _open_rgb(png_path).resize((_HASH_EDGE, _HASH_EDGE)).convert("L")
    pixels = im.tobytes()
    mean = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p > mean:
            bits |= 1 << i
    return bits


def hamming_distance(a: int, b: int) -> int:
    """Bit-difference between two average hashes."""
    return bin(a ^ b).count("1")


def mean_color(png_path: str | Path) -> tuple[float, float, float]:
    """Mean (R, G, B) of the whole frame on a 0-255 scale."""
    data = _open_rgb(png_path).tobytes()
    n = len(data) // 3
    return (
        sum(data[0::3]) / n,
        sum(data[1::3]) / n,
        sum(data[2::3]) / n,
    )


def _fingerprint(png_path: str | Path) -> list[int]:
    """Flattened RGB values of a 16x16 downscale (768 ints)."""
    im = _open_rgb(png_path).resize((_FINGERPRINT_EDGE, _FINGERPRINT_EDGE))
    return list(im.tobytes())


def frame_delta(a: str | Path, b: str | Path) -> float:
    """Mean per-channel absolute difference between two frames (0-255)."""
    fa = _fingerprint(a)
    fb = _fingerprint(b)
    return sum(abs(x - y) for x, y in zip(fa, fb)) / len(fa)


def frames_differ(a: str | Path, b: str | Path, min_delta: float = DIFFER_MIN_DELTA) -> bool:
    """True when frames *a* and *b* differ beyond *min_delta*.

    Combines colour (a downscaled RGB fingerprint) and structure so it works
    for both solid-colour and textured frames.
    """
    return frame_delta(a, b) > min_delta


def frames_similar(a: str | Path, b: str | Path, max_delta: float = SIMILAR_MAX_DELTA) -> bool:
    """True when frames *a* and *b* are within *max_delta* of each other."""
    return frame_delta(a, b) <= max_delta


# ---------------------------------------------------------------------------
# ffprobe
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    raw: dict = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        val = self.raw.get("format", {}).get("duration")
        return float(val) if val is not None else None

    @property
    def streams(self) -> list[dict]:
        return self.raw.get("streams", [])

    @property
    def video_streams(self) -> list[dict]:
        return [s for s in self.streams if s.get("codec_type") == "video"]

    @property
    def audio_streams(self) -> list[dict]:
        return [s for s in self.streams if s.get("codec_type") == "audio"]

    @property
    def width(self) -> int | None:
        vs = self.video_streams
        return int(vs[0]["width"]) if vs and "width" in vs[0] else None

    @property
    def height(self) -> int | None:
        vs = self.video_streams
        return int(vs[0]["height"]) if vs and "height" in vs[0] else None

    @property
    def fps(self) -> float | None:
        vs = self.video_streams
        if not vs:
            return None
        rate = vs[0].get("avg_frame_rate") or vs[0].get("r_frame_rate")
        if not rate or rate == "0/0":
            return None
        num, _, den = rate.partition("/")
        try:
            return float(num) / float(den) if den else float(num)
        except (ValueError, ZeroDivisionError):
            return None


def probe(media_path: str | Path, ffprobe_bin: str = "ffprobe", timeout: int = 30) -> ProbeResult:
    """Return container/stream metadata for *media_path* via ffprobe."""
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {media_path}: {proc.stderr[-1000:]}")
    return ProbeResult(raw=json.loads(proc.stdout or "{}"))


def audio_stats(media_path: str | Path, ffmpeg_bin: str = "ffmpeg", timeout: int = 60) -> dict:
    """Return overall astats measurements (RMS/peak levels) for *media_path*."""
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-i",
        str(media_path),
        "-af",
        "astats=metadata=1:reset=0",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    stats: dict[str, float] = {}
    for line in proc.stderr.splitlines():
        line = line.strip()
        for key in ("RMS level dB", "Peak level dB", "RMS peak dB"):
            marker = key + ":"
            if marker in line:
                val = line.split(marker, 1)[1].strip()
                try:
                    stats[key] = float(val)
                except ValueError:
                    pass
    return stats
