"""Integration tests for local AI mask generation.

Three layers, each independent of the heavy segmentation engines:

1. **Mock-engine pipeline (always, needs only ffmpeg/ffprobe)** -- drive the
   real ffmpeg extract→encode path with a stub segmenter (identity matte) and
   ffprobe the result: resolution/fps match the source and the matte is not a
   uniform frame.
2. **Bundle wiring (always, no ffmpeg)** -- monkeypatch the pipeline's
   ``generate_matte`` so ``mask_generate`` / ``mask_generate_and_apply``
   exercise workspace validation, the derived-masks path, snapshotting, and the
   Shape Alpha insertion without a real engine. Plus the missing-engine error.
3. **Real rembg run (gated)** -- if ``rembg`` + ffmpeg are present, generate a
   genuine matte with the tiny ``u2netp`` model and ffprobe it.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.pipelines import ai_mask
from workshop_video_brain.edit_mcp.server.bundles import ai_mask as ai_mask_bundle
from workshop_video_brain.edit_mcp.server import tools as _tools

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"
TRACK = 2
CLIP = 0

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_FFPROBE = shutil.which("ffprobe") is not None


def _callable(obj):
    """Underlying function whether ``obj`` is plain or a FastMCP tool wrapper."""
    if callable(obj) and not obj.__class__.__name__.endswith("Tool"):
        return obj
    for attr in ("fn", "func", "__wrapped__", "callable", "handler"):
        candidate = getattr(obj, attr, None)
        if callable(candidate):
            return candidate
    if callable(obj):
        return obj
    raise TypeError(f"cannot resolve callable from {obj!r}")


mask_generate = _callable(ai_mask_bundle.mask_generate)
mask_generate_and_apply = _callable(ai_mask_bundle.mask_generate_and_apply)
workspace_create = _callable(_tools.workspace_create)


class _IdentityEngine(ai_mask.MaskEngine):
    """Stub segmenter: the matte is the source frame itself (non-uniform)."""

    name = "mock"

    def mask_png_bytes(self, png_bytes: bytes) -> bytes:
        return png_bytes


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="AI Mask Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    shutil.copy(FIXTURE, ws_root / project_name)
    return ws_root, project_name


def _make_source(path: Path, w: int = 320, h: int = 240, fps: int = 25, frames: int = 5):
    """ffmpeg testsrc clip -- deterministic, non-uniform luma."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc=size={w}x{h}:rate={fps}",
         "-frames:v", str(frames), str(path)],
        capture_output=True, check=True,
    )


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames",
         "-count_frames", "-of", "default=nk=1:nw=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return {"width": int(out[0]), "height": int(out[1]),
            "fps": out[2], "frames": int(out[3])}


# ---------------------------------------------------------------------------
# 1. Mock-engine pipeline (ffmpeg required)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (_HAS_FFMPEG and _HAS_FFPROBE), reason="ffmpeg/ffprobe absent")
def test_mock_engine_pipeline_matches_source(tmp_path):
    src = tmp_path / "src.mp4"
    _make_source(src)
    out_dir = tmp_path / "masks"

    res = ai_mask.generate_matte(
        src, out_dir, engine="rembg", engine_impl=_IdentityEngine(),
    )
    assert res["success"], res
    matte = Path(res["output"])
    assert matte.exists()
    assert res["frames"] == 5

    probe = _probe(matte)
    assert probe["width"] == 320
    assert probe["height"] == 240
    assert probe["fps"] == "25/1"
    assert probe["frames"] == 5

    # Matte must not be a single uniform value (testsrc has varied luma).
    stats = subprocess.run(
        ["ffmpeg", "-i", str(matte), "-vf", "signalstats,metadata=print",
         "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    ymins = [int(l.split("=")[1]) for l in stats.splitlines() if "YMIN=" in l]
    ymaxs = [int(l.split("=")[1]) for l in stats.splitlines() if "YMAX=" in l]
    assert ymins and ymaxs
    assert max(ymaxs) > min(ymins), "matte appears uniform"


@pytest.mark.skipif(not (_HAS_FFMPEG and _HAS_FFPROBE), reason="ffmpeg/ffprobe absent")
def test_mock_engine_pipeline_invert_and_feather(tmp_path):
    src = tmp_path / "src.mp4"
    _make_source(src)
    res = ai_mask.generate_matte(
        src, tmp_path / "masks", engine="rembg", engine_impl=_IdentityEngine(),
        invert=True, feather_px=3, output_name="inv",
    )
    assert res["success"], res
    assert Path(res["output"]).name == "inv.mp4"
    assert res["invert"] is True
    assert res["feather_px"] == 3


def test_generate_matte_missing_source_returns_error(tmp_path):
    res = ai_mask.generate_matte(tmp_path / "nope.mp4", tmp_path / "m",
                                 engine_impl=_IdentityEngine())
    assert res["success"] is False
    assert "not found" in res["error"].lower()


# ---------------------------------------------------------------------------
# 2. Bundle wiring (no ffmpeg / no engine -- monkeypatched pipeline)
# ---------------------------------------------------------------------------

def test_mask_generate_missing_engine_error(tmp_path):
    """A second-tier engine returns an actionable error, never a crash."""
    ws, _ = _make_ws(tmp_path)
    # Put a dummy source in media/raw so we reach engine resolution.
    raw = ws / "media" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "clip.mp4").write_bytes(b"not really a video")
    out = mask_generate(workspace_path=str(ws), source="media/raw/clip.mp4",
                        engine="sam2")
    assert out["status"] == "error"
    assert "ultralytics" in out["message"]


def test_mask_generate_wiring(tmp_path, monkeypatch):
    ws, _ = _make_ws(tmp_path)
    src = ws / "media" / "raw" / "clip.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"x")

    def fake_generate(source, output_dir, **kw):
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        return {"success": True, "output": str(Path(output_dir) / "clip_matte.mp4"),
                "engine": "rembg", "model": "u2netp", "frames": 3,
                "width": 320, "height": 240, "fps": 25.0, "duration": 0.12}

    monkeypatch.setattr(ai_mask, "generate_matte", fake_generate)
    out = mask_generate(workspace_path=str(ws), source="media/raw/clip.mp4")
    assert out["status"] == "success", out
    assert out["data"]["engine"] == "rembg"
    assert out["data"]["output"].endswith("media/derived_masks/clip_matte.mp4")
    assert out["data"]["input"].endswith("media/raw/clip.mp4")


def test_mask_generate_no_source_error(tmp_path):
    ws, _ = _make_ws(tmp_path)  # empty media/raw
    out = mask_generate(workspace_path=str(ws))
    assert out["status"] == "error"
    assert "no video file" in out["message"].lower()


def test_mask_generate_and_apply_wiring(tmp_path, monkeypatch):
    ws, pf = _make_ws(tmp_path)
    src = ws / "media" / "raw" / "clip.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"x")

    matte_rel = "media/derived_masks/clip_matte.mp4"

    def fake_generate(source, output_dir, **kw):
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        return {"success": True, "output": str(ws / matte_rel),
                "engine": "rembg", "model": "u2net_human_seg", "frames": 3,
                "width": 1920, "height": 1080, "fps": 25.0, "duration": 0.12}

    monkeypatch.setattr(ai_mask, "generate_matte", fake_generate)

    out = mask_generate_and_apply(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        source="media/raw/clip.mp4", subject="person",
    )
    assert out["status"] == "success", out
    assert out["data"]["mlt_service"] == "shape"
    assert out["data"]["type"] == "image_alpha"
    assert "snapshot_id" in out["data"]
    assert out["data"]["mask_file"].endswith(matte_rel)

    # A Shape Alpha effect referencing the matte was inserted at index 0.
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    stack = patcher.list_effects(parse_project(ws / pf), (TRACK, CLIP))
    assert stack[0]["mlt_service"] == "shape"
    assert stack[0]["properties"]["resource"].endswith(matte_rel)
    assert stack[0]["properties"]["use_luminance"] == "1"


def test_mask_generate_and_apply_missing_project(tmp_path):
    ws, _ = _make_ws(tmp_path)
    out = mask_generate_and_apply(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track=TRACK, clip=CLIP, source="x.mp4",
    )
    assert out["status"] == "error"


def test_tool_symbols_registered():
    assert hasattr(ai_mask_bundle, "mask_generate")
    assert hasattr(ai_mask_bundle, "mask_generate_and_apply")


# ---------------------------------------------------------------------------
# 3. Real rembg run (gated on availability)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_FFPROBE and ai_mask.engine_available("rembg")),
    reason="rembg or ffmpeg not installed -- real-engine test skipped",
)
def test_real_rembg_generates_matte(tmp_path):
    src = tmp_path / "src.mp4"
    _make_source(src, w=160, h=120, frames=3)
    res = ai_mask.generate_matte(
        src, tmp_path / "masks", engine="rembg", model="u2netp", max_frames=3,
    )
    assert res["success"], res
    matte = Path(res["output"])
    assert matte.exists()
    probe = _probe(matte)
    assert probe["width"] == 160 and probe["height"] == 120
    assert probe["fps"] == "25/1"
