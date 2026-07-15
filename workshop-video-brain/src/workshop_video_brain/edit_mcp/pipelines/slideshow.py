"""Timelapse / slideshow assembly from a folder of still images.

Pure command-construction + timing helpers for the ``media_slideshow`` MCP
bundle tool (``edit_mcp/server/bundles/slideshow.py``).  This is the **additive
route**: assemble a folder of images into a normal H.264 video in
``media/processed/`` with FFmpeg, after which the result is an ordinary
ingestable clip (unlike a native MLT image-sequence producer, which is
documented but not built -- see the module-level notes below and
``docs/research/2026-07-03-tutorial-effect-analysis/timelapse-slideshow.md``).

Design derives from the *"Timelapse / Slideshow from images"* tutorial
(`dxHC_BzryuA`), which builds a slideshow clip from a photo folder with a
per-image frame-duration (seconds + a "ffs"/frames field), optional *dissolve*
(crossfade) and optional *pan / pan-and-zoom* (Ken Burns) animation.

Two assembly backends, chosen by the caller:

* **pattern input** (`-framerate F/N -i prefix%0Nd.ext`) -- used when the folder
  is a uniform, contiguous, single-extension numbered sequence and no crossfade
  / Ken Burns is requested.  Scales to thousands of frames (the timelapse case).
* **filter_complex** (one ``-loop 1 -t`` / single-frame input per image) --
  handles mixed filenames/extensions/sizes, per-image ``xfade`` crossfades and
  per-image ``zoompan`` Ken Burns.  Bounded by input count
  (``MAX_FILTERGRAPH_IMAGES``); very large *mixed-name* sets should be renamed
  into a uniform sequence to take the pattern path.

Every backend scales+pads (or scales+crops, for Ken Burns) each image to the
project profile and emits CFR ``yuv420p`` H.264 so the output ffprobes to a
predictable duration and resolution.

Native MLT image-sequence producer (future work, analysis only): SYNTHESIS gap
#9.  A native producer would attach ``mlt_service="qimage"`` (or ``pixbuf``) to
a ``<producer>`` whose ``resource`` is a ``.all.<ext>``/``%0Nd`` glob, carry a
``ttl`` (frames-per-image) property and optional ``loop``, and require
``adapters/ffmpeg/probe.py`` ``DEFAULT_EXTENSIONS`` (line 16) to recognise image
extensions so the sequence is scannable/ingestable.  That path is *editor-native*
(no intermediate video, per-image ``ttl`` editable in Kdenlive) but blocked on
the image-producer builder + extension scan; this module is the unblocked
additive alternative.
"""
from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Image extensions recognised when scanning a folder (lower-case, with dot).
#: NB: ``adapters/ffmpeg/probe.py::DEFAULT_EXTENSIONS`` (line 16) deliberately
#: excludes these, so images are invisible to ``media_ingest`` -- this module
#: turns them into an ``.mp4`` that *is* ingestable.
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
)

#: Upper bound on images fed to the filter_complex backend (per-image inputs).
#: Above this, callers should use a uniform numbered sequence (pattern backend)
#: or drop crossfade/Ken Burns.
MAX_FILTERGRAPH_IMAGES: int = 300

_DIGITS_RE = re.compile(r"(\d+)")


# ---------------------------------------------------------------------------
# Image discovery
# ---------------------------------------------------------------------------

def _natural_key(name: str) -> list:
    """Sort key that orders embedded numbers naturally (img2 < img10)."""
    parts = _DIGITS_RE.split(name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def list_images(
    folder: Path, extensions: frozenset[str] | set[str] | None = None
) -> list[Path]:
    """Return image files in *folder*, naturally sorted by filename.

    Args:
        folder: Directory to scan (non-recursive).
        extensions: Lower-case extensions (with dot) to accept; defaults to
            :data:`IMAGE_EXTENSIONS`.

    Returns:
        Sorted list of image ``Path`` objects (may be empty).
    """
    exts = extensions or IMAGE_EXTENSIONS
    if not folder.exists() or not folder.is_dir():
        return []
    imgs = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in exts
    ]
    return sorted(imgs, key=lambda p: _natural_key(p.name))


# ---------------------------------------------------------------------------
# Timing math
# ---------------------------------------------------------------------------

def resolve_per_image_seconds(
    fps_per_image: float,
    duration_per_image_seconds: float | None,
    project_fps: float,
) -> float:
    """Resolve how long (seconds) each image is on screen.

    Mirrors the tutorial's dual control: an explicit seconds value, or a
    frames-per-image ("ffs") value that depends on the project frame rate.

    Args:
        fps_per_image: Number of project frames each image is held for
            (the tutorial's frame-duration "ffs" field).  Used only when
            *duration_per_image_seconds* is ``None``.
        duration_per_image_seconds: Explicit seconds-per-image override.
        project_fps: Project/output frame rate.

    Returns:
        Positive seconds-per-image.

    Raises:
        ValueError: if the resolved duration is non-positive or fps invalid.
    """
    if duration_per_image_seconds is not None:
        seconds = float(duration_per_image_seconds)
    else:
        if project_fps <= 0:
            raise ValueError("project_fps must be positive")
        seconds = float(fps_per_image) / float(project_fps)
    if seconds <= 0:
        raise ValueError("per-image duration must be positive")
    return seconds


def compute_total_duration(
    n_images: int, per_image_seconds: float, crossfade_seconds: float = 0.0
) -> float:
    """Expected output duration (seconds).

    Each crossfade overlaps two images, so *n-1* crossfades subtract from the
    naive sum.

    Args:
        n_images: Number of images in the slideshow.
        per_image_seconds: Seconds each image is shown.
        crossfade_seconds: Crossfade/dissolve length between images.

    Returns:
        Total duration in seconds (never negative).
    """
    if n_images <= 0:
        return 0.0
    total = n_images * per_image_seconds
    if crossfade_seconds > 0 and n_images > 1:
        total -= (n_images - 1) * crossfade_seconds
    return max(0.0, total)


def frames_per_image(per_image_seconds: float, fps: float) -> int:
    """Output frames a single image occupies (>= 1)."""
    return max(1, seconds_to_frames(per_image_seconds, fps))


# ---------------------------------------------------------------------------
# Numbered-sequence detection (pattern backend eligibility)
# ---------------------------------------------------------------------------

def detect_numbered_sequence(paths: list[Path]) -> tuple[str, int, int] | None:
    """Detect a uniform, contiguous, single-extension numbered sequence.

    Args:
        paths: Naturally-sorted image paths from one folder.

    Returns:
        ``(printf_pattern, start_number, count)`` -- e.g.
        ``("frame%03d.png", 1, 329)`` -- when every file shares one extension,
        one alphabetic prefix and one zero-pad width, and the trailing numbers
        are contiguous.  ``None`` otherwise (mixed names/extensions ⇒ caller
        uses the filter_complex backend).
    """
    if len(paths) < 1:
        return None

    ext = paths[0].suffix.lower()
    if any(p.suffix.lower() != ext for p in paths):
        return None

    prefix: str | None = None
    width: int | None = None
    numbers: list[int] = []
    for p in paths:
        stem = p.stem
        m = re.fullmatch(r"(.*?)(\d+)", stem)
        if not m:
            return None
        pre, digits = m.group(1), m.group(2)
        if prefix is None:
            prefix = pre
            width = len(digits)
        elif pre != prefix or len(digits) != width:
            return None
        numbers.append(int(digits))

    start = numbers[0]
    if numbers != list(range(start, start + len(numbers))):
        return None

    return f"{prefix}%0{width}d{ext}", start, len(numbers)


# ---------------------------------------------------------------------------
# Filter fragments
# ---------------------------------------------------------------------------

def _fps_fraction(fps: float) -> Fraction:
    return Fraction(fps).limit_denominator(100000)


def scale_pad_filter(width: int, height: int) -> str:
    """Letterbox each image into WxH without distortion (slideshow default)."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )


def scale_crop_filter(width: int, height: int) -> str:
    """Fill WxH (crop overflow) -- used under Ken Burns so zoompan has cover."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )


def zoompan_filter(width: int, height: int, fps: float, d_frames: int) -> str:
    """Simple centred slow-zoom Ken Burns for a single image (``d_frames``)."""
    return (
        "zoompan=z='min(zoom+0.0015,1.5)':"
        f"d={d_frames}:"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={width}x{height}:fps={_fps_fraction(fps)}"
    )


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------

_ENCODE_ARGS = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-fps_mode", "cfr"]


def build_pattern_command(
    folder: Path,
    pattern: str,
    start_number: int,
    output_path: Path,
    width: int,
    height: int,
    fps: float,
    per_image_seconds: float,
    overwrite: bool = True,
) -> list[str]:
    """FFmpeg command for the pattern (numbered-sequence) backend.

    Holds each image for ``round(per_image_seconds * fps)`` output frames by
    setting the input ``-framerate`` to ``fps / frames_per_image``.
    """
    fpi = frames_per_image(per_image_seconds, fps)
    fps_frac = _fps_fraction(fps)
    # input images-per-second = fps / frames_per_image (exact fraction)
    in_rate = f"{fps_frac.numerator}/{fps_frac.denominator * fpi}"
    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += [
        "-framerate", in_rate,
        "-start_number", str(start_number),
        "-i", str(folder / pattern),
        "-vf", f"{scale_pad_filter(width, height)},format=yuv420p",
        "-r", str(fps_frac),
        *_ENCODE_ARGS,
        str(output_path),
    ]
    return cmd


def build_filtergraph_command(
    paths: list[Path],
    output_path: Path,
    width: int,
    height: int,
    fps: float,
    per_image_seconds: float,
    crossfade_seconds: float = 0.0,
    kenburns: bool = False,
    overwrite: bool = True,
) -> list[str]:
    """FFmpeg command for the per-image filter_complex backend.

    Handles mixed filenames/extensions, ``xfade`` crossfades (dissolve) and
    ``zoompan`` Ken Burns (pan/zoom).  One input per image.
    """
    n = len(paths)
    if n == 0:
        raise ValueError("no images to assemble")
    fpi = frames_per_image(per_image_seconds, fps)
    fps_frac = _fps_fraction(fps)

    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")

    # Inputs: Ken Burns consumes one input frame per image (single still),
    # otherwise loop the still for its on-screen duration.
    for p in paths:
        if kenburns:
            cmd += ["-i", str(p)]
        else:
            cmd += ["-loop", "1", "-t", f"{per_image_seconds:.6f}", "-i", str(p)]

    # Per-image normalisation chain.
    segments: list[str] = []
    labels: list[str] = []
    for i in range(n):
        label = f"v{i}"
        if kenburns:
            chain = (
                f"[{i}:v]{scale_crop_filter(width, height)},"
                f"{zoompan_filter(width, height, fps, fpi)},"
                f"format=yuv420p[{label}]"
            )
        else:
            chain = (
                f"[{i}:v]{scale_pad_filter(width, height)},"
                f"fps={fps_frac},format=yuv420p[{label}]"
            )
        segments.append(chain)
        labels.append(label)

    if crossfade_seconds > 0 and n > 1:
        # Chain xfade transitions, accumulating the offset.
        prev = labels[0]
        offset = per_image_seconds - crossfade_seconds
        for i in range(1, n):
            out = "xfout" if i == n - 1 else f"x{i}"
            segments.append(
                f"[{prev}][{labels[i]}]"
                f"xfade=transition=fade:duration={crossfade_seconds:.6f}:"
                f"offset={offset:.6f}[{out}]"
            )
            prev = out
            offset += per_image_seconds - crossfade_seconds
        final_label = prev
    elif n > 1:
        segments.append(
            "".join(f"[{lbl}]" for lbl in labels) + f"concat=n={n}:v=1:a=0[xfout]"
        )
        final_label = "xfout"
    else:
        final_label = labels[0]

    filter_complex = ";".join(segments)
    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{final_label}]",
        "-r", str(fps_frac),
        *_ENCODE_ARGS,
        str(output_path),
    ]
    return cmd


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

def choose_backend(
    paths: list[Path], crossfade_frames: int, kenburns: bool
) -> str:
    """Return ``"pattern"`` or ``"filtergraph"`` for the given inputs.

    Pattern backend requires a uniform numbered sequence and no
    crossfade / Ken Burns; everything else uses filter_complex.
    """
    if crossfade_frames > 0 or kenburns:
        return "filtergraph"
    return "pattern" if detect_numbered_sequence(paths) is not None else "filtergraph"
