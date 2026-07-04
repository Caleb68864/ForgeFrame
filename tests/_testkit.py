"""Shared test helpers ("testkit") for the ForgeFrame suite.

Consolidates patterns that were copy-pasted across dozens of integration and
unit modules:

* ``unwrap`` / ``call_tool`` / ``tool_fn`` -- the ``@mcp.tool()`` ``.fn``-unwrap
  dance (a ``FunctionTool`` in newer fastmcp, the bare function in older).
* ``registered_tool_names`` / ``assert_registered`` -- the FastMCP
  ``list_tools`` / ``get_tools`` (sync-or-coroutine, list-or-dict) probe.
* ``make_test_clip`` and friends -- deterministic synthetic media via ffmpeg
  (``testsrc`` / ``sine`` / solid ``color`` sources).
* ``solid_color_project`` / ``sequence_project`` / ``two_track_project`` -- tiny
  in-memory :class:`KdenliveProject` builders backed by MLT ``color:`` producers
  (no media files needed). These are the *non-external twin* of
  ``tests/integration/external/builders.py`` -- kept here so non-external tests
  never import from the external oracle package.

Gating markers/fixtures live in ``tests/conftest.py``.

Growth policy (consolidation pass 4)
------------------------------------
This module mirrors ``pipelines/_common`` on the test side: a shared kernel of
small, reusable primitives. It spans five domains -- MCP unwrap/invoke, tool
registration probing, synthetic media generation, in-memory ``KdenliveProject``
builders, and tool-availability gates. Split trigger (same as ``_common``):
when it clearly exceeds its cohesion, promote to a ``tests/_testkit/`` package
split by domain (``_mcp`` / ``_media`` / ``_projects`` / ``_gates``) behind a
``__init__.py`` shim that re-exports every current name so the ~19 importing
test modules stay byte-identical. As of pass 4 it is ~309 LOC / 5 domains --
**at the threshold**, but a package split is deferred (the opinion's "do not
pre-split" guidance) so this pass's diff stays contained; execute the shim-backed
split as its own mechanical change when it next grows.
"""
from __future__ import annotations

import asyncio
import inspect
import shutil
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Tool-availability gates (canonical). Marks assign to a module ``pytestmark``;
# the ffmpeg/ffprobe/melt *fixtures* live in tests/conftest.py.
# ---------------------------------------------------------------------------
HAVE_FFMPEG = shutil.which("ffmpeg") is not None
HAVE_FFPROBE = shutil.which("ffprobe") is not None
HAVE_MELT = shutil.which("melt") is not None

requires_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not available on PATH")
requires_ffprobe = pytest.mark.skipif(not HAVE_FFPROBE, reason="ffprobe not available on PATH")
requires_ffmpeg_ffprobe = pytest.mark.skipif(
    not (HAVE_FFMPEG and HAVE_FFPROBE), reason="ffmpeg/ffprobe not available on PATH"
)
requires_melt = pytest.mark.skipif(not HAVE_MELT, reason="melt not available on PATH")
requires_melt_ffmpeg = pytest.mark.skipif(
    not (HAVE_MELT and HAVE_FFMPEG), reason="melt/ffmpeg not available on PATH"
)

# ---------------------------------------------------------------------------
# MCP tool unwrap + invocation
# ---------------------------------------------------------------------------


def unwrap(tool):
    """Return the underlying callable for an ``@mcp.tool()`` object.

    Newer fastmcp wraps the function in a ``FunctionTool`` exposing ``.fn``;
    older versions return the bare function. Works on either.
    """
    return getattr(tool, "fn", tool)


def tool_fn(module, name: str):
    """``unwrap(getattr(module, name))`` -- fetch a bundle tool by name."""
    return unwrap(getattr(module, name))


def call_tool(tool, *args, **kwargs):
    """Unwrap *tool* and call it with the given args."""
    return unwrap(tool)(*args, **kwargs)


# ---------------------------------------------------------------------------
# FastMCP registration probing
# ---------------------------------------------------------------------------


def registered_tool_names(mcp=None) -> set[str]:
    """Return the set of tool names registered on the FastMCP instance.

    Tolerates the fastmcp API surface variants: ``get_tools`` vs ``list_tools``,
    sync return vs coroutine/awaitable, and dict vs list-of-tool results.
    ``mcp`` defaults to the project singleton ``workshop_video_brain.server.mcp``.
    """
    if mcp is None:
        from workshop_video_brain.server import mcp as mcp  # noqa: PLW0127
    getter = getattr(mcp, "get_tools", None) or getattr(mcp, "list_tools", None)
    if getter is None:  # pragma: no cover - defensive
        raise AttributeError("FastMCP instance exposes neither get_tools nor list_tools")
    res = getter()
    if inspect.isawaitable(res):
        res = asyncio.run(res)
    if isinstance(res, dict):
        return set(res.keys())
    return {getattr(t, "name", getattr(t, "key", str(t))) for t in res}


def assert_registered(*names: str, mcp=None) -> None:
    """Assert every name in *names* is a registered FastMCP tool."""
    registered = registered_tool_names(mcp)
    missing = [n for n in names if n not in registered]
    assert not missing, f"tools not registered: {missing}"


# ---------------------------------------------------------------------------
# Synthetic media (ffmpeg testsrc / sine / color)
# ---------------------------------------------------------------------------

_FFMPEG_QUIET = ["-v", "error", "-y"]


def _run_ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", *_FFMPEG_QUIET, *args], check=True, capture_output=True)


def make_test_clip(
    path: str | Path,
    *,
    duration: float = 2.0,
    fps: int = 25,
    kind: str = "video",
    size: tuple[int, int] = (320, 240),
    color: str = "red",
    freq: float = 440.0,
    with_audio: bool = False,
    pix_fmt: str | None = None,
) -> Path:
    """Generate a deterministic synthetic clip with ffmpeg.

    ``kind``:
      * ``"video"``  -- ``testsrc`` colour-bar pattern (optionally +sine audio
        when ``with_audio`` is set).
      * ``"color"``  -- a solid ``color=`` source (uses ``color``).
      * ``"tone"`` / ``"audio"`` -- a ``sine`` tone (uses ``freq``); container
        chosen from ``path`` suffix.

    Returns the written ``Path``. ffmpeg must be present (gate with the
    ``ffmpeg``/``ffprobe`` fixtures or ``requires_ffmpeg`` marker).
    """
    path = Path(path)
    w, h = size
    if kind in ("tone", "audio"):
        _run_ffmpeg(["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}", str(path)])
        return path
    if kind == "color":
        src = f"color=c={color}:size={w}x{h}:rate={fps}:duration={duration}"
    elif kind == "video":
        src = f"testsrc=size={w}x{h}:rate={fps}:duration={duration}"
    else:  # pragma: no cover - defensive
        raise ValueError(f"unknown clip kind: {kind!r}")
    args = ["-f", "lavfi", "-i", src]
    if with_audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}", "-shortest"]
    if pix_fmt:
        args += ["-pix_fmt", pix_fmt]
    args.append(str(path))
    _run_ffmpeg(args)
    return path


# ---------------------------------------------------------------------------
# In-memory KdenliveProject builders (color-producer backed, hermetic)
# ---------------------------------------------------------------------------

# 0xRRGGBBAA
RED = "0xff0000ff"
BLUE = "0x0000ffff"
GREEN = "0x00ff00ff"
WHITE = "0xffffffff"
BLACK = "0x000000ff"

DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 180
DEFAULT_FPS = 25.0

VIDEO_TRACK = "playlist_video"
AUDIO_TRACK = "playlist_audio"


def color_producer(producer_id: str, resource: str, length: int):
    """A solid-colour MLT ``color`` producer (bare 0xRRGGBBAA resource)."""
    from workshop_video_brain.core.models.kdenlive import Producer

    return Producer(
        id=producer_id,
        resource=resource,
        properties={"resource": resource, "mlt_service": "color", "length": str(length)},
    )


def solid_color_project(
    color: str = RED,
    frames: int = 50,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: float = DEFAULT_FPS,
    title: str = "solid",
):
    """One video + one audio track, a single solid-colour clip on each."""
    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject,
        Playlist,
        PlaylistEntry,
        ProjectProfile,
        Track,
    )

    length = frames + 10
    p = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=width, height=height, fps=fps, colorspace="709"),
    )
    p.producers = [color_producer("producer_0", color, length)]
    p.tracks = [
        Track(id=VIDEO_TRACK, track_type="video", name="Video"),
        Track(id=AUDIO_TRACK, track_type="audio", name="Audio"),
    ]
    entry = PlaylistEntry(producer_id="producer_0", in_point=0, out_point=frames - 1)
    p.playlists = [
        Playlist(id=VIDEO_TRACK, entries=[entry.model_copy(deep=True)]),
        Playlist(id=AUDIO_TRACK, entries=[entry.model_copy(deep=True)]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(frames - 1)}
    return p


def sequence_project(
    colors: list[str] | None = None,
    frames_each: int = 25,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: float = DEFAULT_FPS,
    title: str = "sequence",
):
    """One video (+audio) track with N back-to-back solid-colour clips."""
    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject,
        Playlist,
        PlaylistEntry,
        ProjectProfile,
        Track,
    )

    colors = colors or [RED, BLUE]
    total = frames_each * len(colors)
    p = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=width, height=height, fps=fps, colorspace="709"),
    )
    video_entries: list = []
    audio_entries: list = []
    for i, color in enumerate(colors):
        pid = f"producer_{i}"
        p.producers.append(color_producer(pid, color, frames_each + 10))
        video_entries.append(PlaylistEntry(producer_id=pid, in_point=0, out_point=frames_each - 1))
        audio_entries.append(PlaylistEntry(producer_id=pid, in_point=0, out_point=frames_each - 1))
    p.tracks = [
        Track(id=VIDEO_TRACK, track_type="video", name="Video"),
        Track(id=AUDIO_TRACK, track_type="audio", name="Audio"),
    ]
    p.playlists = [
        Playlist(id=VIDEO_TRACK, entries=video_entries),
        Playlist(id=AUDIO_TRACK, entries=audio_entries),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(total - 1)}
    return p


def two_track_project(
    v1_color: str = RED,
    frames: int = 100,
    fps: float = DEFAULT_FPS,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    title: str = "place",
):
    """v1 (filled), v2 (empty), audio (empty): playlist indices 0, 1, 2.

    The canonical "two video tracks + one clip to move around" fixture used by
    clip-placement and effect-targeting tests.
    """
    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject,
        Playlist,
        PlaylistEntry,
        ProjectProfile,
        Track,
    )

    p = KdenliveProject(title=title, profile=ProjectProfile(width=width, height=height, fps=fps))
    p.producers = [color_producer("red", v1_color, frames * 2)]
    p.tracks = [
        Track(id="v1", track_type="video"),
        Track(id="v2", track_type="video"),
        Track(id="a1", track_type="audio"),
    ]
    p.playlists = [
        Playlist(id="v1", entries=[PlaylistEntry(producer_id="red", in_point=0, out_point=frames - 1)]),
        Playlist(id="v2", entries=[]),
        Playlist(id="a1", entries=[]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(frames - 1)}
    return p


def have_binary(name: str) -> bool:
    """True if *name* resolves on PATH (thin ``shutil.which`` wrapper)."""
    return shutil.which(name) is not None
