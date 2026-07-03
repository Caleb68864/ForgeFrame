"""Local AI mask generation: produce a black/white **matte video** for a clip.

This is the *producing* half of the SAM2 story. Kdenlive 25.04's Object Mask
runs SAM2 as an application plugin (own venv, not scriptable) and leaves behind
a mask video + a Shape Alpha effect. Our file-based tools already *consume* any
matte via ``pipelines/shape_alpha.py`` + ``server/bundles/shape_alpha_mask.py``
(``mask_set_from_file`` → MLT ``shape`` filter). This module generates that
matte **headlessly** with a local segmenter so an agent can mask a subject
without the GUI. See ``docs/plans/2026-07-03-kdenlive-mcp-improvements.md`` §5
and ``vault/Research/Local AI Mask Generation.md``.

Design (mirrors ``pipelines/stabilize.py``): pure command-construction /
planning helpers + an engine adapter, then an orchestrating ``generate_matte``
that runs ffmpeg via ``subprocess``.

Pipeline
--------
1. ``ffmpeg`` extracts source frames to PNGs (matching native resolution/fps).
2. The segmenter turns each frame into a single-channel matte (white = keep).
3. ``ffmpeg`` encodes the matte PNGs back into a video matching the source
   fps/resolution/duration, applying box-restriction / invert / feather in the
   encode filter chain. Output lands in ``media/derived_masks/`` — the source in
   ``media/raw`` is never touched.

Engines
-------
* ``rembg`` (default, lightest) — onnxruntime, **no torch**. Salient-object /
  background removal, per-frame. ``subject="person"`` biases to the
  ``u2net_human_seg`` model; otherwise a light default model is used.
* ``sam2`` / ``yolo`` — documented **second tier** (pull the multi-GB torch
  stack, GPU recommended). Not implemented here; requesting them yields a clear
  ``pip install …`` error rather than a crash.

If the chosen engine's package is missing, ``generate_matte`` raises
``EngineUnavailable`` carrying the exact ``pip install`` line to run.
"""
from __future__ import annotations

import importlib.util
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Suffix appended to the source stem for the generated matte (mirrors the
# ``_stabilized`` / ``_proxy`` / ``_cfr`` conventions in the ffmpeg adapters).
_OUTPUT_SUFFIX = "_matte"
_MATTE_EXT = ".mp4"

# Where generated mattes live, relative to the workspace root. A dedicated
# folder (not ``media/processed``) keeps derived mask videos self-describing and
# easy to prune. Never ``media/raw``.
DERIVED_MASKS_DIR = ("media", "derived_masks")


# ---------------------------------------------------------------------------
# Engine registry / selection
# ---------------------------------------------------------------------------

# Every supported engine name → the module that must import for it to run, plus
# the exact command to install it. ``rembg`` is the only one with an adapter
# implemented in this module; ``sam2``/``yolo`` are the documented heavy tier.
ENGINES: dict[str, dict[str, str]] = {
    "rembg": {
        "module": "rembg",
        "pip": "uv pip install rembg onnxruntime  (lightweight, no torch)",
        "implemented": "yes",
    },
    "sam2": {
        "module": "sam2",
        "pip": "uv pip install ultralytics  (SAM2; pulls torch ~2GB, GPU recommended)",
        "implemented": "no",
    },
    "yolo": {
        "module": "ultralytics",
        "pip": "uv pip install ultralytics  (YOLO-seg; pulls torch ~2GB)",
        "implemented": "no",
    },
}

# Preference order used to resolve ``engine="auto"`` — lightest first.
_AUTO_ORDER: tuple[str, ...] = ("rembg",)

# rembg model resolution: which onnx model to use for a given subject.
_HUMAN_SUBJECTS = {"person", "people", "human", "man", "woman", "portrait", "self"}
_DEFAULT_MODEL = "u2netp"  # tiny (~4 MB), CPU-friendly, zero-friction default.
_HUMAN_MODEL = "u2net_human_seg"  # biased to people (~170 MB, downloaded on use).


class EngineUnavailable(RuntimeError):
    """Raised when the requested segmentation engine cannot be used.

    The message always includes an actionable ``pip install`` hint.
    """


def engine_available(name: str) -> bool:
    """Return True if *name*'s backing package is importable."""
    spec = ENGINES.get(name)
    if spec is None:
        return False
    return importlib.util.find_spec(spec["module"]) is not None


def _pip_hint(name: str) -> str:
    spec = ENGINES.get(name)
    return spec["pip"] if spec else f"install the '{name}' package"


def resolve_engine(requested: str = "auto") -> str:
    """Resolve an engine name, validating it is known, implemented, installed.

    ``"auto"`` picks the lightest available engine (rembg). Raises
    ``ValueError`` for an unknown name and ``EngineUnavailable`` (with a
    ``pip install`` hint) for a known-but-missing/unimplemented engine.
    """
    requested = (requested or "auto").strip().lower()

    if requested == "auto":
        for name in _AUTO_ORDER:
            if engine_available(name):
                return name
        raise EngineUnavailable(
            "No local mask engine is installed. Install the default engine: "
            f"{_pip_hint('rembg')}"
        )

    if requested not in ENGINES:
        raise ValueError(
            f"Unknown engine '{requested}'. Known: {', '.join(sorted(ENGINES))}, auto."
        )

    spec = ENGINES[requested]
    if spec["implemented"] != "yes":
        raise EngineUnavailable(
            f"Engine '{requested}' is a documented second-tier engine not yet "
            f"wired up here. Use engine='rembg' (default), or see: {spec['pip']}"
        )
    if not engine_available(requested):
        raise EngineUnavailable(
            f"Engine '{requested}' is selected but not installed. "
            f"Install it: {spec['pip']}"
        )
    return requested


def resolve_model(subject: str, model: str = "") -> str:
    """Pick the rembg model for *subject* (explicit *model* wins).

    ``subject`` in the people set → ``u2net_human_seg``; otherwise the tiny
    default. An explicit non-empty *model* overrides the heuristic.
    """
    if model and model.strip():
        return model.strip()
    if subject and subject.strip().lower() in _HUMAN_SUBJECTS:
        return _HUMAN_MODEL
    return _DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Planning / param helpers (pure)
# ---------------------------------------------------------------------------

def parse_box(box: str) -> tuple[int, int, int, int] | None:
    """Parse a ``"x,y,w,h"`` box string into a validated int tuple.

    Empty / whitespace → ``None`` (no restriction). Raises ``ValueError`` for a
    malformed string or non-positive width/height.
    """
    if not box or not box.strip():
        return None
    parts = [p.strip() for p in box.split(",")]
    if len(parts) != 4:
        raise ValueError(f"box must be 'x,y,w,h' (4 comma-separated ints), got {box!r}")
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"box components must be integers: {box!r}") from exc
    if x < 0 or y < 0:
        raise ValueError(f"box x,y must be >= 0: {box!r}")
    if w <= 0 or h <= 0:
        raise ValueError(f"box w,h must be > 0: {box!r}")
    return (x, y, w, h)


def derived_mask_path(
    source: Path,
    output_dir: Path,
    output_name: str | None = None,
) -> Path:
    """Compute the matte destination path.

    Defaults to ``{stem}_matte.mp4`` inside *output_dir*. A custom
    *output_name* is used as-is (``.mp4`` appended if it has no suffix).
    """
    source = Path(source)
    if output_name and output_name.strip():
        name = output_name.strip()
        if not Path(name).suffix:
            name = f"{name}{_MATTE_EXT}"
        return Path(output_dir) / name
    return Path(output_dir) / f"{source.stem}{_OUTPUT_SUFFIX}{_MATTE_EXT}"


def build_extract_cmd(
    source: Path,
    out_pattern: str,
    *,
    max_frames: int = 0,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """Full ffmpeg command extracting source frames to a PNG sequence.

    *out_pattern* is a printf pattern (e.g. ``frames/f_%06d.png``). When
    *max_frames* > 0 only the first N frames are extracted (used for fast
    tests / previews). Frames keep the source's native resolution.
    """
    cmd = [ffmpeg, "-y", "-i", str(source)]
    if max_frames and max_frames > 0:
        cmd += ["-frames:v", str(int(max_frames))]
    cmd += ["-start_number", "0", out_pattern]
    return cmd


def build_encode_cmd(
    mask_pattern: str,
    output: Path,
    fps: float,
    width: int,
    height: int,
    *,
    box: tuple[int, int, int, int] | None = None,
    invert: bool = False,
    feather_px: int = 0,
    crf: int = 12,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """Full ffmpeg command encoding matte PNGs into a matte video.

    Builds a filter chain that (in order): forces single-channel ``gray``,
    scales to the exact ``width``x``height``, optionally restricts to *box*
    (everything outside → black), optionally inverts, optionally feathers
    (gaussian blur, sigma≈``feather_px``), then converts to ``yuv420p`` so the
    matte plays as a normal video whose **luma** carries the mask (consume with
    Shape Alpha ``use_luminance=True``).
    """
    if fps <= 0:
        fps = 25.0
    filters = ["format=gray", f"scale={int(width)}:{int(height)}"]
    if box is not None:
        bx, by, bw, bh = box
        # Keep only the box region; pad the rest back to full frame in black.
        filters.append(f"crop={bw}:{bh}:{bx}:{by}")
        filters.append(f"pad={int(width)}:{int(height)}:{bx}:{by}:color=black")
    if invert:
        filters.append("negate")
    if feather_px and feather_px > 0:
        filters.append(f"gblur=sigma={int(feather_px)}")
    filters.append("format=yuv420p")
    vf = ",".join(filters)
    return [
        ffmpeg, "-y",
        "-framerate", _fmt_fps(fps),
        "-start_number", "0",
        "-i", mask_pattern,
        "-vf", vf,
        "-r", _fmt_fps(fps),
        "-c:v", "libx264",
        "-crf", str(int(crf)),
        "-pix_fmt", "yuv420p",
        str(output),
    ]


def _fmt_fps(fps: float) -> str:
    """Format an fps for ffmpeg — integer when whole, else a rational-ish float."""
    if abs(fps - round(fps)) < 1e-6:
        return str(int(round(fps)))
    return f"{fps:.5f}"


# ---------------------------------------------------------------------------
# Engine adapters
# ---------------------------------------------------------------------------

class MaskEngine:
    """Interface: turn one frame's PNG bytes into matte PNG bytes.

    Implementations return single-channel-representable PNG bytes where lighter
    pixels = keep. The encode step forces ``format=gray`` so any channel layout
    is acceptable.
    """

    name: str = "base"

    def mask_png_bytes(self, png_bytes: bytes) -> bytes:  # pragma: no cover
        raise NotImplementedError


class RembgEngine(MaskEngine):
    """rembg (onnxruntime) salient-object matte engine — the default."""

    name = "rembg"

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self.model = model
        self._session = None  # lazily created (triggers model download)

    @staticmethod
    def available() -> bool:
        return engine_available("rembg")

    def _sess(self):
        if self._session is None:
            from rembg import new_session  # type: ignore
            self._session = new_session(self.model)
        return self._session

    def mask_png_bytes(self, png_bytes: bytes) -> bytes:
        from rembg import remove  # type: ignore
        return remove(
            png_bytes,
            session=self._sess(),
            only_mask=True,
            post_process_mask=True,
            force_return_bytes=True,
        )


def make_engine(engine: str, subject: str = "person", model: str = "") -> MaskEngine:
    """Resolve + instantiate a concrete engine (raises like ``resolve_engine``)."""
    name = resolve_engine(engine)
    if name == "rembg":
        return RembgEngine(model=resolve_model(subject, model))
    # resolve_engine only returns implemented engines; defensive guard.
    raise EngineUnavailable(  # pragma: no cover
        f"Engine '{name}' has no adapter. {_pip_hint(name)}"
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class MattePlan:
    """Resolved plan for a matte-generation run (pure, inspectable)."""

    source: Path
    output: Path
    engine: str
    model: str
    subject: str
    box: tuple[int, int, int, int] | None
    invert: bool
    feather_px: int
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration: float = 0.0
    max_frames: int = 0
    extra: dict = field(default_factory=dict)


def _probe_source(source: Path) -> tuple[int, int, float, float]:
    """Return (width, height, fps, duration) for *source* via the ffprobe adapter."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
    asset = probe_media(source)
    return asset.width, asset.height, asset.fps, asset.duration


def plan_matte(
    source: Path,
    output_dir: Path,
    *,
    subject: str = "person",
    engine: str = "auto",
    box: str = "",
    invert: bool = False,
    feather_px: int = 0,
    model: str = "",
    output_name: str = "",
    max_frames: int = 0,
    probe: bool = True,
) -> MattePlan:
    """Build a validated :class:`MattePlan` without running ffmpeg/segmenter.

    Resolves the engine (raising ``EngineUnavailable`` early if missing), the
    rembg model, the box, and the output path; optionally probes the source for
    resolution/fps/duration. Pure enough to unit-test the whole decision layer.
    """
    source = Path(source)
    name = resolve_engine(engine)
    resolved_model = resolve_model(subject, model) if name == "rembg" else ""
    parsed_box = parse_box(box)
    if feather_px < 0:
        raise ValueError(f"feather_px must be >= 0, got {feather_px}")
    out = derived_mask_path(source, output_dir, output_name)

    w = h = 0
    fps = dur = 0.0
    if probe and source.exists():
        w, h, fps, dur = _probe_source(source)

    return MattePlan(
        source=source,
        output=out,
        engine=name,
        model=resolved_model,
        subject=subject,
        box=parsed_box,
        invert=bool(invert),
        feather_px=int(feather_px),
        width=w,
        height=h,
        fps=fps,
        duration=dur,
        max_frames=int(max_frames),
    )


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def generate_matte(
    source: Path,
    output_dir: Path,
    *,
    subject: str = "person",
    engine: str = "auto",
    box: str = "",
    invert: bool = False,
    feather_px: int = 0,
    model: str = "",
    output_name: str = "",
    max_frames: int = 0,
    engine_impl: MaskEngine | None = None,
    ffmpeg: str = "ffmpeg",
) -> dict:
    """Generate a matte video for *source* into *output_dir*.

    Steps: probe → extract frames (ffmpeg) → segment each frame (engine) →
    encode matte video (ffmpeg) matching the source's resolution/fps/duration.
    Box-restriction / invert / feather are applied in the encode filter chain.

    *engine_impl* injects a concrete :class:`MaskEngine` (used by tests to run
    the full ffmpeg pipeline with a mock segmenter); when ``None`` a real engine
    is resolved from *engine* (raising ``EngineUnavailable`` if missing).

    Returns a result ``dict`` with ``success`` and, on success, ``output`` plus
    matte metadata. On ffmpeg failure returns ``success=False`` + ``error``.
    """
    import tempfile

    source = Path(source)
    output_dir = Path(output_dir)
    if not source.exists():
        return {"success": False, "error": f"Source not found: {source}"}

    plan = plan_matte(
        source, output_dir,
        subject=subject, engine=engine, box=box, invert=invert,
        feather_px=feather_px, model=model, output_name=output_name,
        max_frames=max_frames, probe=True,
    )
    eng = engine_impl if engine_impl is not None else make_engine(engine, subject, model)

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ai_mask_") as tmp:
        tmpd = Path(tmp)
        frames_dir = tmpd / "frames"
        masks_dir = tmpd / "masks"
        frames_dir.mkdir()
        masks_dir.mkdir()

        # 1. Extract frames.
        extract = _run(build_extract_cmd(
            source, str(frames_dir / "f_%06d.png"),
            max_frames=plan.max_frames, ffmpeg=ffmpeg,
        ))
        if extract.returncode != 0:
            return {"success": False, "error": f"frame extraction failed: {extract.stderr[-500:]}"}

        frames = sorted(frames_dir.glob("f_*.png"))
        if not frames:
            return {"success": False, "error": "no frames extracted from source"}

        # 2. Segment each frame -> matte PNG.
        for i, fp in enumerate(frames):
            try:
                matte_bytes = eng.mask_png_bytes(fp.read_bytes())
            except Exception as exc:  # noqa: BLE001 -- surface engine errors cleanly
                return {"success": False, "error": f"segmenter failed on frame {i}: {exc}"}
            (masks_dir / f"m_{i:06d}.png").write_bytes(matte_bytes)

        # 3. Encode matte video.
        width = plan.width or _png_dims(frames[0])[0]
        height = plan.height or _png_dims(frames[0])[1]
        encode = _run(build_encode_cmd(
            str(masks_dir / "m_%06d.png"), plan.output,
            fps=plan.fps, width=width, height=height,
            box=plan.box, invert=plan.invert, feather_px=plan.feather_px,
            ffmpeg=ffmpeg,
        ))
        if encode.returncode != 0:
            return {"success": False, "error": f"matte encode failed: {encode.stderr[-500:]}"}

    return {
        "success": True,
        "output": str(plan.output),
        "engine": plan.engine,
        "model": plan.model,
        "subject": plan.subject,
        "frames": len(frames),
        "width": width,
        "height": height,
        "fps": plan.fps,
        "duration": plan.duration,
        "box": list(plan.box) if plan.box else None,
        "invert": plan.invert,
        "feather_px": plan.feather_px,
    }


def _png_dims(path: Path) -> tuple[int, int]:
    """Read a PNG's (width, height) from its IHDR header without a decoder dep."""
    import struct
    with open(path, "rb") as fh:
        head = fh.read(24)
    # PNG signature (8) + IHDR length/type (8) then width, height as big-endian.
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    w, h = struct.unpack(">II", head[16:24])
    return (w, h)
