"""Motion tracking & subject auto-zoom -- pure geometry + tracker engines.

Implements plan §5 (``docs/plans/2026-07-03-kdenlive-mcp-improvements.md``):
turn a subject rectangle into a smooth, tracked punch-in that follows it.

Two halves live here:

1. **Pure functions** (no I/O) that convert tracked subject rects into
   ``affine``/``transform`` source-region keyframes -- padding to a target
   composition, clamping to frame bounds, moving-average smoothing, and
   ease-in/out at the punch-in boundaries. These reuse the shared keyframe
   machinery in ``pipelines/keyframes.py`` (``build_keyframe_string``), exactly
   like ``pipelines/pan_zoom.py`` (this module is its *tracked* cousin).

2. **Tracker engines** (mirrors ``pipelines/ai_mask.py``'s engine registry):
   * ``melt`` (default) -- the MLT ``opencv.tracker`` filter run **headless**.
     The §5 feasibility spike confirmed melt persists analysis in a ``results``
     property via ``melt <clip> -filter opencv.tracker rect=... algo=... \
     -consumer xml:out.mlt all=1 real_time=-1`` (deterministic; **do not** set
     ``shape_width=0`` -- that empirically suppresses persistence). No new deps.
   * ``opencv`` -- pure-Python CSRT/KCF via ``opencv-contrib-python-headless``
     (optional ``motion-track`` extra). A missing package raises
     ``TrackerUnavailable`` carrying the exact ``pip install`` line.

Coordinates: a subject rect and a transform *source-region* rect are both
``(x, y, w, h)`` in **source-frame pixels**. The transform scales its region up
to fill the output frame, so a smaller region zooms in; translating it pans/
follows. All emitted regions live inside ``[0, 0, W, H]``.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines.keyframes import (
    Keyframe,
    VALID_EASE_FAMILIES,
    build_keyframe_string,
)

Rect = tuple[float, float, float, float]

# Where tracked-keyframe JSON + extracted locator frames are written, relative
# to the workspace root (never ``media/raw``). Mirrors ai_mask's dedicated dir.
TRACKS_DIR = ("reports", "tracks")


# ---------------------------------------------------------------------------
# Tracker-engine registry / selection (mirrors pipelines/ai_mask.py)
# ---------------------------------------------------------------------------

# Every supported engine -> what must be present for it to run + how to get it.
# ``melt`` is a binary on PATH (checked with shutil.which); ``opencv`` is an
# importable module. Both are "implemented" here.
ENGINES: dict[str, dict[str, str]] = {
    "melt": {
        "kind": "binary",
        "probe": "melt",
        "pip": "install the MLT toolkit providing the 'melt' binary "
               "(e.g. `sudo pacman -S mlt` / `apt install melt`)",
    },
    "opencv": {
        "kind": "module",
        "probe": "cv2",
        "pip": "uv pip install opencv-contrib-python-headless  "
               "(CSRT/KCF trackers; ~66 MB, no GUI/torch)",
    },
}

# Preference order for ``engine="auto"``: melt first (zero new deps, native
# CSRT), OpenCV fallback second.
_AUTO_ORDER: tuple[str, ...] = ("melt", "opencv")

# Accepted algorithm names (case-insensitive) -> canonical upper form passed to
# both melt's ``algo`` and OpenCV's ``Tracker<NAME>`` constructor. CSRT is the
# accurate default per plan §5; the rest are faster/older.
_ALGORITHMS: dict[str, str] = {
    "csrt": "CSRT",
    "kcf": "KCF",
    "mosse": "MOSSE",
    "mil": "MIL",
    "boosting": "BOOSTING",
    "tld": "TLD",
    "medianflow": "MEDIANFLOW",
}
DEFAULT_ALGORITHM = "csrt"


class TrackerUnavailable(RuntimeError):
    """Raised when the requested tracker engine cannot be used.

    The message always includes an actionable install hint.
    """


class FfmpegUnavailable(RuntimeError):
    """Raised when the ``ffmpeg`` binary needed for frame extraction is missing.

    Distinct from a *decode* failure (:class:`FrameExtractionError`): this is an
    environment problem the user fixes by installing FFmpeg. The message carries
    an install hint so the tool layer maps it to ``missing_binary``.
    """


class FrameExtractionError(RuntimeError):
    """Raised when ffmpeg ran but produced no frame (unreadable/undecodable input).

    Distinct from :class:`FfmpegUnavailable` (binary missing): here ffmpeg is
    present but could not decode the requested timestamp -- a truncated, corrupt,
    or wrong-format source -- so the tool layer maps it to ``media_unreadable``.
    """


def engine_available(name: str) -> bool:
    """Return True if *name*'s backing binary/module is present."""
    spec = ENGINES.get(name)
    if spec is None:
        return False
    if spec["kind"] == "binary":
        return shutil.which(spec["probe"]) is not None
    return importlib.util.find_spec(spec["probe"]) is not None


def _pip_hint(name: str) -> str:
    spec = ENGINES.get(name)
    return spec["pip"] if spec else f"install the '{name}' engine"


def resolve_engine(requested: str = "auto") -> str:
    """Resolve a tracker engine name, validating it is known and installed.

    ``"auto"`` picks the first available engine (melt, then opencv). Raises
    ``ValueError`` for an unknown name and ``TrackerUnavailable`` (with an
    install hint) for a known-but-missing engine.
    """
    requested = (requested or "auto").strip().lower()

    if requested == "auto":
        for name in _AUTO_ORDER:
            if engine_available(name):
                return name
        raise TrackerUnavailable(
            "No motion-tracking engine available. Install melt (MLT) or the "
            f"OpenCV fallback: {_pip_hint('opencv')}"
        )

    if requested not in ENGINES:
        raise ValueError(
            f"Unknown engine '{requested}'. Known: {', '.join(sorted(ENGINES))}, auto."
        )
    if not engine_available(requested):
        raise TrackerUnavailable(
            f"Engine '{requested}' is selected but not available. "
            f"{_pip_hint(requested)}"
        )
    return requested


def resolve_algorithm(algorithm: str = DEFAULT_ALGORITHM) -> str:
    """Validate + canonicalise a tracker algorithm name (upper form)."""
    key = (algorithm or DEFAULT_ALGORITHM).strip().lower()
    if key not in _ALGORITHMS:
        raise ValueError(
            f"Unknown algorithm {algorithm!r}. Valid: "
            f"{', '.join(sorted(_ALGORITHMS))}."
        )
    return _ALGORITHMS[key]


# ---------------------------------------------------------------------------
# Pure geometry: pad / clamp / smooth / boundary-easing
# ---------------------------------------------------------------------------

def _as_four(rect: object) -> Rect:
    """Coerce a 4- or 5-element rect ``(x y w h [op])`` to ``(x, y, w, h)``."""
    if not isinstance(rect, (list, tuple)) or len(rect) not in (4, 5):
        raise ValueError(
            f"rect must be a list/tuple of 4 or 5 numbers; got {rect!r}"
        )
    try:
        return tuple(float(v) for v in rect[:4])  # type: ignore[return-value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"rect values must be numeric; got {rect!r}") from exc


def pad_rect_to_fill(
    subject: object, frame_w: int, frame_h: int, fill: float = 0.6
) -> Rect:
    """Grow *subject* into a **source-region** rect so the subject fills *fill*.

    The transform scales its source region up to fill the whole output frame,
    so for the subject to occupy ``fill`` of the output the region must be
    ``subject_size / fill`` -- and sized to the frame's aspect ratio so the
    scale-up doesn't distort. The region is centred on the subject's centre;
    ``fill`` is met in the tighter dimension (the subject fits within it in the
    other). The result is *not* yet clamped to frame bounds -- compose with
    :func:`clamp_rect_to_bounds`.
    """
    if frame_w <= 0 or frame_h <= 0:
        raise ValueError(
            f"frame size must be positive; got {frame_w}x{frame_h}"
        )
    if not 0.0 < fill <= 1.0:
        raise ValueError(f"fill must be in (0, 1]; got {fill}")
    sx, sy, sw, sh = _as_four(subject)
    if sw <= 0 or sh <= 0:
        raise ValueError(f"subject w,h must be > 0; got {subject!r}")

    frame_ar = frame_w / frame_h
    # Region width needed to satisfy `fill` in each dimension, projected to the
    # frame aspect ratio; take the larger so the subject fits within `fill` on
    # both axes.
    region_w = max(sw / fill, (sh / fill) * frame_ar)
    region_h = region_w / frame_ar

    cx = sx + sw / 2.0
    cy = sy + sh / 2.0
    return (cx - region_w / 2.0, cy - region_h / 2.0, region_w, region_h)


def clamp_rect_to_bounds(rect: object, frame_w: int, frame_h: int) -> Rect:
    """Clamp a region into ``[0, 0, W, H]``, preserving aspect on oversize.

    If the region is larger than the frame it is shrunk **uniformly** about its
    centre (so a zoom never distorts), then the origin is constrained so the
    region lies fully inside the frame.
    """
    if frame_w <= 0 or frame_h <= 0:
        raise ValueError(
            f"frame size must be positive; got {frame_w}x{frame_h}"
        )
    x, y, w, h = _as_four(rect)
    w = max(w, 1.0)
    h = max(h, 1.0)
    # Uniform shrink-to-fit about the centre (preserves aspect ratio).
    scale = min(1.0, float(frame_w) / w, float(frame_h) / h)
    if scale < 1.0:
        cx = x + w / 2.0
        cy = y + h / 2.0
        w *= scale
        h *= scale
        x = cx - w / 2.0
        y = cy - h / 2.0
    x = min(max(x, 0.0), float(frame_w) - w)
    y = min(max(y, 0.0), float(frame_h) - h)
    return (x, y, w, h)


def moving_average_smooth(rects: list[Rect], window: int) -> list[Rect]:
    """Centred moving-average smooth of a rect sequence (per component).

    ``window`` is the total window size (odd recommended). ``window <= 1``
    returns the input unchanged. Edges use a shrinking clamped window so the
    sequence length is preserved and the first/last rects stay anchored.
    """
    if not isinstance(window, int) or isinstance(window, bool):
        raise ValueError(f"window must be int; got {window!r}")
    if window <= 1 or len(rects) <= 2:
        return [tuple(_as_four(r)) for r in rects]  # type: ignore[misc]
    coerced = [_as_four(r) for r in rects]
    k = window // 2
    n = len(coerced)
    out: list[Rect] = []
    for i in range(n):
        lo = max(0, i - k)
        hi = min(n, i + k + 1)
        seg = coerced[lo:hi]
        m = len(seg)
        out.append((
            sum(r[0] for r in seg) / m,
            sum(r[1] for r in seg) / m,
            sum(r[2] for r in seg) / m,
            sum(r[3] for r in seg) / m,
        ))
    return out


def boundary_easings(
    n: int, ease: str = "cubic", interior: str = "smooth"
) -> list[str]:
    """Per-keyframe easing names: ease **into** and **out of** the punch-in.

    The MLT operator on a keyframe governs the segment *leaving* it. The first
    keyframe therefore gets ``ease_in_<ease>`` (ramp into the move) and the
    penultimate keyframe ``ease_out_<ease>`` (settle onto the final framing);
    interior keyframes use *interior* (``smooth`` -> natural follow). Returns a
    list of length *n*.
    """
    if ease not in VALID_EASE_FAMILIES:
        raise ValueError(
            f"ease family {ease!r} invalid; valid: {VALID_EASE_FAMILIES}"
        )
    if n <= 0:
        return []
    if n == 1:
        return ["linear"]
    out = [interior] * n
    out[0] = f"ease_in_{ease}"
    if n >= 3:
        out[-2] = f"ease_out_{ease}"
    return out


# ---------------------------------------------------------------------------
# Keyframe assembly (tracked follow + static punch-in)
# ---------------------------------------------------------------------------

def region_to_transform_rect(
    region: object, frame_w: int, frame_h: int
) -> Rect:
    """Convert a **source-region** rect to the MLT ``affine`` *destination* rect.

    The ``affine`` filter's ``transition.rect`` names where the *whole* source
    frame is placed/scaled, not a crop -- so to make source region
    ``R=(rx,ry,rw,rh)`` fill the ``W x H`` output we place the full frame scaled
    by ``s`` and offset so ``R`` maps onto ``(0,0,W,H)``::

        s = W / rw            (== H / rh for aspect-preserved regions)
        dest = (-rx*s, -ry*s, W*s, H*s)

    Verified against a real ``melt`` render in the §5 render-proof test. Keeping
    geometry (pad/clamp/smooth) in intuitive source-region space and converting
    only at emit time is why those pure functions stay simple + unit-testable.
    """
    rx, ry, rw, rh = _as_four(region)
    if rw <= 0 or rh <= 0:
        raise ValueError(f"region w,h must be > 0; got {region!r}")
    sx = float(frame_w) / rw
    sy = float(frame_h) / rh
    return (-rx * sx, -ry * sy, float(frame_w) * sx, float(frame_h) * sy)


def build_zoom_keyframes(
    tracked: list[tuple[int, Rect]],
    frame_w: int,
    frame_h: int,
    fps: float,
    *,
    fill: float = 0.6,
    smoothing: int = 5,
    ease: str = "cubic",
) -> str:
    """Tracked subject rects -> a smoothed, eased transform-rect keyframe string.

    Pipeline (all pure): pad each subject rect to the target composition
    (:func:`pad_rect_to_fill`) -> clamp to frame bounds -> moving-average smooth
    -> re-clamp -> attach boundary easing -> emit via ``build_keyframe_string``.
    Frame numbers are **rebased** so the earliest tracked frame becomes keyframe
    0 (clip-local), which is what the ``transform`` filter on the clip expects.
    """
    if not tracked:
        raise ValueError("tracked keyframe list cannot be empty")
    tracked = sorted(tracked, key=lambda t: t[0])
    base = tracked[0][0]
    frames = [f - base for f, _ in tracked]

    regions = [
        clamp_rect_to_bounds(
            pad_rect_to_fill(r, frame_w, frame_h, fill), frame_w, frame_h
        )
        for _, r in tracked
    ]
    regions = moving_average_smooth(regions, smoothing)
    regions = [clamp_rect_to_bounds(r, frame_w, frame_h) for r in regions]

    # Convert source regions -> affine destination rects at emit time.
    dests = [region_to_transform_rect(r, frame_w, frame_h) for r in regions]
    easings = boundary_easings(len(dests), ease)
    kfs = [
        Keyframe(fr, list(dst), es)
        for fr, dst, es in zip(frames, dests, easings)
    ]
    return build_keyframe_string("rect", kfs, fps, ease_family_default=ease)


def build_static_zoom_keyframes(
    subject: object,
    frame_w: int,
    frame_h: int,
    fps: float,
    *,
    fill: float = 0.6,
) -> str:
    """A single subject rect -> a **static punch-in** (constant framing).

    Pads + clamps the subject to a fixed source region and emits a one-keyframe
    (constant) rect animation. No camera motion -- a fixed zoomed framing that
    works even before any tracking data exists.
    """
    region = clamp_rect_to_bounds(
        pad_rect_to_fill(subject, frame_w, frame_h, fill), frame_w, frame_h
    )
    dest = region_to_transform_rect(region, frame_w, frame_h)
    return build_keyframe_string(
        "rect", [Keyframe(0, list(dest), "linear")], fps
    )


# ---------------------------------------------------------------------------
# melt results parsing
# ---------------------------------------------------------------------------

# One results segment: ``<frame><op>=<x> <y> <w> <h>[ <opacity>]`` where <op> is
# an optional single MLT operator char (e.g. ``~``). Frames are source-absolute.
_RESULT_SEG_RE = re.compile(
    r"^(?P<frame>\d+)(?P<op>[^\d=\-]?)=(?P<rect>[-\d.\s]+)$"
)


def parse_mlt_results(results: str) -> list[tuple[int, Rect]]:
    """Parse an MLT ``opencv.tracker`` ``results`` string to ``[(frame, rect)]``.

    Format (verified in the §5 spike)::

        0~=20 96 48 48 0;5~=34 98 43 43 0;10~=46 98 43 43 0;...

    Each segment is ``<frame><op>=<x> <y> <w> <h> [<opacity>]``. Malformed
    segments raise ``ValueError``. Returned rects are ``(x, y, w, h)`` floats.
    """
    if not results or not results.strip():
        return []
    out: list[tuple[int, Rect]] = []
    for raw in results.split(";"):
        seg = raw.strip()
        if not seg:
            continue
        m = _RESULT_SEG_RE.match(seg)
        if not m:
            raise ValueError(f"malformed tracker results segment: {seg!r}")
        frame = int(m.group("frame"))
        nums = m.group("rect").split()
        if len(nums) < 4:
            raise ValueError(
                f"results segment needs >=4 rect numbers: {seg!r}"
            )
        x, y, w, h = (float(v) for v in nums[:4])
        out.append((frame, (x, y, w, h)))
    return out


# ---------------------------------------------------------------------------
# Tracker engines
# ---------------------------------------------------------------------------

def build_melt_track_cmd(
    source: Path,
    seed_rect: Rect,
    algorithm: str,
    out_mlt: Path,
    *,
    start_frame: int = 0,
    end_frame: int = 0,
    steps: int = 5,
    melt: str = "melt",
) -> list[str]:
    """Full ``melt`` command that runs headless opencv.tracker analysis.

    Emits ``melt <source> [in=.. out=..] -filter opencv.tracker rect=.. algo=..
    steps=.. -consumer xml:<out> all=1 real_time=-1`` -- the exact invocation
    the §5 spike proved persists a ``results`` property. ``shape_width`` is left
    at its default: forcing ``shape_width=0`` empirically suppresses
    persistence. ``real_time=-1`` (single-threaded) is required for the
    analysis pass.
    """
    x, y, w, h = seed_rect
    cmd = [melt, str(source)]
    if start_frame > 0:
        cmd.append(f"in={int(start_frame)}")
    if end_frame > 0:
        cmd.append(f"out={int(end_frame)}")
    cmd += [
        "-filter", "opencv.tracker",
        f"rect={int(round(x))} {int(round(y))} {int(round(w))} {int(round(h))}",
        f"algo={algorithm}",
        f"steps={int(steps)}",
        "-consumer", f"xml:{out_mlt}",
        "all=1", "real_time=-1",
    ]
    return cmd


def _extract_results_property(mlt_xml: str) -> str:
    """Pull the ``opencv.tracker`` ``results`` property text from a melt XML."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(mlt_xml)
    for prop in root.iter("property"):
        if prop.get("name") == "results" and (prop.text or "").strip():
            return prop.text.strip()
    return ""


def run_melt_tracker(
    source: Path,
    seed_rect: Rect,
    algorithm: str = "CSRT",
    *,
    start_frame: int = 0,
    end_frame: int = 0,
    steps: int = 5,
    melt: str = "melt",
    timeout: int = 300,
) -> list[tuple[int, Rect]]:
    """Run headless MLT ``opencv.tracker`` analysis and return tracked rects.

    Writes a temp analysis MLT, runs melt, then reads back the ``results``
    property. Raises ``TrackerUnavailable`` if ``melt`` is not on PATH and
    ``RuntimeError`` if analysis produced no persisted results.
    """
    if shutil.which(melt) is None:
        raise TrackerUnavailable(
            f"'{melt}' not on PATH. {_pip_hint('melt')}"
        )
    source = Path(source)
    with tempfile.TemporaryDirectory(prefix="motion_track_") as tmp:
        out_mlt = Path(tmp) / "analysis.mlt"
        cmd = build_melt_track_cmd(
            source, seed_rect, algorithm, out_mlt,
            start_frame=start_frame, end_frame=end_frame, steps=steps,
            melt=melt,
        )
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        if not out_mlt.exists():
            raise RuntimeError(
                "melt tracker analysis produced no output MLT.\n"
                f"returncode={proc.returncode}\nstderr tail:\n{proc.stderr[-1200:]}"
            )
        results = _extract_results_property(out_mlt.read_text())
    if not results:
        raise RuntimeError(
            "melt ran but persisted no tracker 'results' -- the opencv module "
            "may be missing, or the content lacks trackable texture. "
            "stderr tail:\n" + proc.stderr[-800:]
        )
    return parse_mlt_results(results)


def _make_cv_tracker(cv2, algorithm: str):
    """Construct an OpenCV tracker for *algorithm* across cv2 API generations."""
    upper = algorithm.upper()
    # cv2 >= 4.5 style: cv2.TrackerCSRT.create(); older: cv2.TrackerCSRT_create;
    # contrib legacy namespace: cv2.legacy.TrackerCSRT_create().
    candidates = (
        getattr(getattr(cv2, f"Tracker{upper}", None), "create", None),
        getattr(cv2, f"Tracker{upper}_create", None),
        getattr(getattr(cv2, "legacy", None), f"Tracker{upper}_create", None),
    )
    for ctor in candidates:
        if callable(ctor):
            return ctor()
    raise TrackerUnavailable(
        f"OpenCV build has no '{upper}' tracker. Install the contrib package: "
        f"{_pip_hint('opencv')}"
    )


def run_opencv_tracker(
    source: Path,
    seed_rect: Rect,
    algorithm: str = "CSRT",
    *,
    start_frame: int = 0,
    end_frame: int = 0,
    step: int = 1,
) -> list[tuple[int, Rect]]:
    """Track *seed_rect* through *source* with OpenCV (fallback engine).

    Requires ``opencv-contrib-python-headless`` (``motion-track`` extra); a
    missing ``cv2`` raises ``TrackerUnavailable`` with the install command.
    Returns source-absolute ``[(frame, rect)]`` sampled every *step* frames.
    """
    if importlib.util.find_spec("cv2") is None:
        raise TrackerUnavailable(
            f"OpenCV not installed. {_pip_hint('opencv')}"
        )
    import cv2  # type: ignore

    source = Path(source)
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open source: {source}")
    tracker = _make_cv_tracker(cv2, algorithm)
    x, y, w, h = seed_rect
    out: list[tuple[int, Rect]] = []
    step = max(1, int(step))
    try:
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_frame))
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("OpenCV could not read the seed frame")
        tracker.init(frame, (int(x), int(y), int(w), int(h)))
        out.append((start_frame, (float(x), float(y), float(w), float(h))))
        idx = start_frame
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            idx += 1
            if end_frame and idx > end_frame:
                break
            tracked_ok, box = tracker.update(frame)
            if not tracked_ok:
                continue
            if (idx - start_frame) % step == 0:
                bx, by, bw, bh = box
                out.append((idx, (float(bx), float(by), float(bw), float(bh))))
    finally:
        cap.release()
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class TrackResult:
    """A completed tracking run (pure, JSON-serialisable via :meth:`to_dict`)."""

    source: str
    engine: str
    algorithm: str
    frame_width: int
    frame_height: int
    fps: float
    start_frame: int
    end_frame: int
    keyframes: list[tuple[int, Rect]] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a plain dict with both pixel and normalised rects."""
        W = float(self.frame_width) or 1.0
        H = float(self.frame_height) or 1.0
        kfs = []
        for frame, (x, y, w, h) in self.keyframes:
            kfs.append({
                "frame": int(frame),
                "seconds": (frame / self.fps) if self.fps else 0.0,
                "rect": [x, y, w, h],
                "rect_normalized": [x / W, y / H, w / W, h / H],
            })
        return {
            "source": self.source,
            "engine": self.engine,
            "algorithm": self.algorithm,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "fps": self.fps,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "keyframe_count": len(self.keyframes),
            "keyframes": kfs,
        }


def track_subject(
    source: Path,
    seed_rect: Rect,
    frame_width: int,
    frame_height: int,
    fps: float,
    *,
    algorithm: str = DEFAULT_ALGORITHM,
    engine: str = "auto",
    start_frame: int = 0,
    end_frame: int = 0,
    steps: int = 5,
) -> TrackResult:
    """Track *seed_rect* through *source*, engine-resolved (melt|opencv).

    Returns a :class:`TrackResult`; the caller persists it (``reports/tracks``).
    Raises ``TrackerUnavailable`` when no engine is usable, ``ValueError`` for a
    bad algorithm, and ``RuntimeError`` when the engine yields no keyframes.
    """
    resolved = resolve_engine(engine)
    algo = resolve_algorithm(algorithm)
    if resolved == "melt":
        kfs = run_melt_tracker(
            source, seed_rect, algo,
            start_frame=start_frame, end_frame=end_frame, steps=steps,
        )
    else:
        kfs = run_opencv_tracker(
            source, seed_rect, algo,
            start_frame=start_frame, end_frame=end_frame,
        )
    if not kfs:
        raise RuntimeError(
            f"tracker engine '{resolved}' returned no keyframes"
        )
    return TrackResult(
        source=str(source),
        engine=resolved,
        algorithm=algo,
        frame_width=frame_width,
        frame_height=frame_height,
        fps=fps,
        start_frame=start_frame,
        end_frame=end_frame or kfs[-1][0],
        keyframes=kfs,
    )


# ---------------------------------------------------------------------------
# Frame extraction (subject locator, agent-vision mode)
# ---------------------------------------------------------------------------

def build_extract_frame_cmd(
    source: Path,
    at_seconds: float,
    output: Path,
    *,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """ffmpeg command extracting a single frame at *at_seconds* to a PNG."""
    return [
        ffmpeg, "-y",
        "-ss", f"{max(0.0, float(at_seconds)):.5f}",
        "-i", str(source),
        "-frames:v", "1",
        str(output),
    ]


def extract_locator_frames(
    source: Path,
    times: list[float],
    out_dir: Path,
    *,
    stem: str = "locate",
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """Extract one PNG per timestamp in *times*; return written paths.

    Frames land in *out_dir* named ``{stem}_{ms}.png``.

    Raises:
        FfmpegUnavailable: the ``ffmpeg`` binary is not on PATH (environment
            error; carries an install hint) -- maps to ``missing_binary``.
        FrameExtractionError: ffmpeg ran but decoded no frame for a requested
            timestamp (unreadable/corrupt/wrong-format source) -- maps to
            ``media_unreadable``.
    """
    source = Path(source)
    out_dir = Path(out_dir)
    if not source.exists():
        raise FileNotFoundError(f"locator source media not found: {source}")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for t in times:
        ms = int(round(max(0.0, float(t)) * 1000))
        out = out_dir / f"{stem}_{ms:07d}.png"
        cmd = build_extract_frame_cmd(source, t, out, ffmpeg=ffmpeg)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, check=False
            )
        except FileNotFoundError as exc:
            raise FfmpegUnavailable(
                f"'{ffmpeg}' binary not found on PATH; install FFmpeg "
                "(e.g. `sudo pacman -S ffmpeg` / `apt install ffmpeg`)."
            ) from exc
        if not out.exists():
            raise FrameExtractionError(
                f"frame extraction failed at t={t}s (ffmpeg decoded no frame -- "
                f"source may be truncated/corrupt/unsupported).\n"
                f"returncode={proc.returncode}\nstderr tail:\n{proc.stderr[-800:]}"
            )
        written.append(str(out))
    return written
