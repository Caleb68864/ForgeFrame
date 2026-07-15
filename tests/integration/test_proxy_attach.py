"""Integration tests for the proxy-wiring MCP tools.

Exercises ``proxy_attach`` / ``proxy_detach`` / ``proxy_status`` end-to-end inside
a real workspace (snapshot + parser/serializer round-trip) plus registration
asserts.  When ffmpeg/melt are present it also generates a REAL proxy for a
``testsrc`` clip via the existing proxy machinery, proves ``proxy_status`` reports
it and ``proxy_attach`` wires it, and melt-accepts the wired project.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

import workshop_video_brain.server as _server  # noqa: F401
from workshop_video_brain.edit_mcp.server.bundles import proxy_wiring as _bundle
import workshop_video_brain.edit_mcp.server.tools as _tools
from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


from tests._testkit import unwrap as _fn  # noqa: E402


proxy_attach = _fn(_bundle.proxy_attach)
proxy_detach = _fn(_bundle.proxy_detach)
proxy_status = _fn(_bundle.proxy_status)
workspace_create = _fn(_tools.workspace_create)

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_MELT = shutil.which("melt") is not None


def _make_ws(tmp_path: Path) -> Path:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Proxy Test", media_root=str(media_root))
    assert result["status"] == "success", result
    return Path(result["data"]["workspace_root"])


def _write_project(ws: Path, sources: list[str]) -> Path:
    producers = [
        Producer(id=f"producer{i}", resource=s, properties={"resource": s})
        for i, s in enumerate(sources)
    ]
    entries = [PlaylistEntry(producer_id=p.id, in_point=0, out_point=99) for p in producers]
    project = KdenliveProject(
        title="Proxy Test",
        producers=producers,
        playlists=[Playlist(id="playlist0", entries=entries)],
        tracks=[Track(id="playlist0", track_type="video")],
    )
    dest = ws / "projects" / "working_copies" / "proxy_test_v1.kdenlive"
    dest.parent.mkdir(parents=True, exist_ok=True)
    serialize_project(project, dest)
    return dest


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_tools_registered():
    lister = getattr(_server.mcp, "list_tools", None) or _server.mcp.get_tools
    result = asyncio.run(lister())
    names = set(result.keys()) if isinstance(result, dict) else {
        getattr(t, "name", t) for t in result
    }
    for name in ("proxy_attach", "proxy_detach", "proxy_status"):
        assert name in names, f"{name} not registered"


# ---------------------------------------------------------------------------
# attach / status / detach against a fake (touched) proxy file
# ---------------------------------------------------------------------------

def test_attach_wires_touched_proxy(tmp_path):
    ws = _make_ws(tmp_path)
    proj = _write_project(ws, ["/raw/clip.mp4"])
    proxy = ws / "media" / "proxies" / "clip_proxy.mp4"
    proxy.parent.mkdir(parents=True, exist_ok=True)
    proxy.write_bytes(b"\x00")

    out = proxy_attach(workspace_path=str(ws), project_file=str(proj))
    assert out["status"] == "success", out
    assert out["data"]["attached"] == ["producer0"]
    assert out["data"]["enableproxy"] == "1"
    assert out["data"]["snapshot_id"]

    reparsed = parse_project(proj)
    prod = reparsed.producers[0]
    assert prod.resource == str(proxy)
    assert prod.properties["kdenlive:proxy"] == str(proxy)
    assert prod.properties["kdenlive:originalurl"] == "/raw/clip.mp4"
    assert reparsed.docproperties["enableproxy"] == "1"


def test_status_then_detach(tmp_path):
    ws = _make_ws(tmp_path)
    proj = _write_project(ws, ["/raw/clip.mp4"])
    proxy = ws / "media" / "proxies" / "clip_proxy.mp4"
    proxy.parent.mkdir(parents=True, exist_ok=True)
    proxy.write_bytes(b"\x00")

    # status before: not proxied
    st0 = proxy_status(workspace_path=str(ws), project_file=str(proj))
    assert st0["data"]["proxied_count"] == 0
    assert st0["data"]["total_video_producers"] == 1

    proxy_attach(workspace_path=str(ws), project_file=str(proj))

    st1 = proxy_status(workspace_path=str(ws), project_file=str(proj))
    assert st1["data"]["proxied_count"] == 1
    assert st1["data"]["producers"][0]["proxy_file_exists"] is True

    det = proxy_detach(workspace_path=str(ws), project_file=str(proj))
    assert det["status"] == "success", det
    assert det["data"]["detached"] == ["producer0"]

    reparsed = parse_project(proj)
    assert reparsed.producers[0].resource == "/raw/clip.mp4"
    assert reparsed.docproperties["enableproxy"] == "0"


def test_attach_errors_when_no_proxy_files(tmp_path):
    ws = _make_ws(tmp_path)
    proj = _write_project(ws, ["/raw/clip.mp4"])  # no proxy generated
    out = proxy_attach(workspace_path=str(ws), project_file=str(proj))
    assert out["status"] == "error"
    assert "producer0" in out["message"]


def test_bad_workspace_errors():
    assert proxy_attach(workspace_path="", project_file="x")["status"] == "error"
    assert proxy_status(workspace_path="", project_file="x")["status"] == "error"


def test_resolve_project_picks_highest_version_not_lexicographic(tmp_path):
    """Regression: empty project_file must fall back to the numerically-latest
    working copy (``_v10`` > ``_v2``), not the lexicographic ``files[-1]`` which
    wrongly selected ``_v2``."""
    ws = _make_ws(tmp_path)
    working = ws / "projects" / "working_copies"
    working.mkdir(parents=True, exist_ok=True)
    # Distinguishable content per version so we can prove which was chosen.
    for ver in (2, 10):
        _write_project(ws, [f"/raw/clip_v{ver}.mp4"])
        (working / "proxy_test_v1.kdenlive").rename(working / f"proxy_test_v{ver}.kdenlive")
    resolved = _bundle._resolve_project(str(ws), "")
    assert resolved.name == "proxy_test_v10.kdenlive", resolved


# ---------------------------------------------------------------------------
# Real proxy via the existing machinery (ffmpeg) + melt-accept
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not available")
def test_real_proxy_generate_status_attach(tmp_path):
    ws = _make_ws(tmp_path)
    raw = ws / "media" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    original = raw / "testsrc.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=size=1280x720:rate=25:duration=1",
            "-pix_fmt", "yuv420p", str(original),
        ],
        check=True, capture_output=True,
    )

    # Generate a REAL proxy via the existing proxy machinery.
    from workshop_video_brain.core.models import MediaAsset
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import (
        generate_proxy,
        proxy_path_for,
    )

    asset = MediaAsset(path=str(original), media_type="video", width=1280, height=720)
    proxy_dir = ws / "media" / "proxies"
    generate_proxy(asset, proxy_dir)
    assert proxy_path_for(asset, proxy_dir).exists()

    proj = _write_project(ws, [str(original)])

    # proxy_status sees the not-yet-wired clip.
    st = proxy_status(workspace_path=str(ws), project_file=str(proj))
    assert st["data"]["total_video_producers"] == 1
    assert st["data"]["proxied_count"] == 0

    # proxy_attach wires the real proxy by default naming.
    out = proxy_attach(workspace_path=str(ws), project_file=str(proj))
    assert out["status"] == "success", out
    assert out["data"]["attached"] == ["producer0"]

    reparsed = parse_project(proj)
    assert reparsed.producers[0].resource == str(proxy_path_for(asset, proxy_dir))

    # After attach the status reports the proxy present.
    st2 = proxy_status(workspace_path=str(ws), project_file=str(proj))
    assert st2["data"]["proxied_count"] == 1
    assert st2["data"]["missing_proxy_count"] == 0

    if _HAS_MELT:
        proc = subprocess.run(
            ["melt", str(proj), "-consumer", "null", "out=5"],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr[-500:]


@pytest.mark.skipif(
    not (_HAS_FFMPEG and _HAS_MELT), reason="ffmpeg+melt required"
)
def test_render_uses_originals_not_proxy(tmp_path):
    """run_render (non-proxy mode) must swap resource back to the original."""
    ws = _make_ws(tmp_path)
    raw = ws / "media" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    original = raw / "testsrc.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=size=1280x720:rate=25:duration=1",
            "-pix_fmt", "yuv420p", str(original),
        ],
        check=True, capture_output=True,
    )
    from workshop_video_brain.core.models import MediaAsset
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import generate_proxy

    asset = MediaAsset(path=str(original), media_type="video", width=1280, height=720)
    generate_proxy(asset, ws / "media" / "proxies")
    proj = _write_project(ws, [str(original)])
    proxy_attach(workspace_path=str(ws), project_file=str(proj))

    from workshop_video_brain.edit_mcp.pipelines.proxy_wiring import originals_render_copy

    swapped = originals_render_copy(proj, ws / "renders" / ".proxy_originals")
    assert swapped != proj
    reparsed = parse_project(swapped)
    assert reparsed.producers[0].resource == str(original)
