"""Real subtitle-track MCP tools -- §3 High "Real subtitle track".

``subtitles_attach`` turns an SRT (default: the latest ``reports/*.srt`` from
``subtitles_generate``) into a real project subtitle track: it converts the SRT
to a styled ``.ass`` sidecar next to the project, adds an ``avfilter.subtitles``
filter on the timeline tractor (render-provable headless in melt) and the
``subtitlesList`` / ``activeSubtitleIndex`` doc/sequence properties the Kdenlive
24/25/26 GUI reads for its Subtitles panel.

``subtitles_burn_in`` bakes the subtitles into a delivered file via ffmpeg's
``ass``/``subtitles`` filter (media/processed/), rendering the project through
melt first when a ``.kdenlive`` is passed.  This is the render-path guarantee
that works today regardless of project-format support.

Format verified against KDE source + live melt -- see
``docs/research/2026-07-03-tutorial-effect-analysis/subtitle-track.md``.

Auto-imported by ``server/bundles/__init__``; registers via ``@mcp.tool()``.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    invalid_input,
    bad_json_param,
    corrupt_project,
    operation_failed,
    from_exception,
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, find_workspace_root
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg
from workshop_video_brain.edit_mcp.pipelines import subtitle_track as st
from workshop_video_brain.workspace import create_snapshot


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _find_workspace_root(start: Path) -> Path | None:
    return find_workspace_root(start)


def _resolve_project(workspace_path: str, project_file: str) -> Path:
    """Resolve *project_file* to an existing .kdenlive path.

    Accepts absolute paths, cwd-relative paths, bare filenames under the
    workspace ``projects/working_copies/``, and falls back to the latest working
    copy when *project_file* is empty.
    """
    ws = Path(workspace_path)
    if project_file:
        p = _resolve(project_file)
        if p.exists():
            return p
        candidate = ws / "projects" / "working_copies" / project_file
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Project file not found: {project_file}")
    working = ws / "projects" / "working_copies"
    files = sorted(working.glob("*.kdenlive")) if working.exists() else []
    if not files:
        raise FileNotFoundError(
            "No project_file given and no .kdenlive in projects/working_copies/"
        )
    return files[-1]


def _resolve_srt(workspace_path: str, srt_path: str) -> Path:
    if srt_path:
        p = _resolve(srt_path)
        if not p.exists():
            raise FileNotFoundError(f"SRT file not found: {srt_path}")
        return p
    latest = st.latest_srt(Path(workspace_path) / "reports")
    if latest is None:
        raise FileNotFoundError(
            "No srt_path given and no *.srt in reports/ "
            "(run subtitles_generate first)"
        )
    return latest


def _escape_ff(path: Path) -> str:
    """Escape a path for use inside an ffmpeg filtergraph option value."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


# ---------------------------------------------------------------------------
# subtitles_attach
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def subtitles_attach(
    workspace_path: str,
    project_file: str = "",
    srt_path: str = "",
    style=None,
) -> dict:
    """Attach an SRT to a Kdenlive project as a real subtitle track.

    Converts the SRT to a styled ``.ass`` sidecar next to the project, adds an
    ``avfilter.subtitles`` filter on the timeline tractor and the
    ``subtitlesList`` / ``activeSubtitleIndex`` properties Kdenlive reads.  The
    attach round-trips through our parser/serializer and renders headless in
    melt.

    Args:
        workspace_path: Path to the workspace root directory.
        project_file: .kdenlive path (absolute, cwd-relative, or a bare filename
            under projects/working_copies/).  Empty = latest working copy.
        srt_path: Path to the SRT.  Empty = latest ``reports/*.srt``.
        style: Optional styling as a dict or JSON string -- keys ``font``,
            ``size``, ``primary_color`` (#RRGGBB), ``outline_color``, ``bold``,
            ``italic``, ``outline``, ``alignment`` (1-9) or ``position``
            ("bottom", "top", ...), ``margin_v``.

    Returns a success dict with the sidecar path, cue count and subtitlesList.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).")
        ws = Path(workspace_path)
        if not ws.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).", path=workspace_path)

        project_path = _resolve_project(workspace_path, project_file)
        srt = _resolve_srt(workspace_path, srt_path)
        subtitle_style = st.SubtitleStyle.from_input(style)

        # Parse BEFORE snapshotting so a corrupt project fails cleanly
        # (corrupt_project) instead of the outer generic handler, and without
        # leaving a leaked snapshot behind.
        try:
            project = parse_project(project_path)
        except Exception as exc:  # noqa: BLE001 -- corrupt/unparseable project
            return from_exception(exc)
        width = project.profile.width or 1920
        height = project.profile.height or 1080

        ass_content = st.srt_to_ass(
            srt.read_text(encoding="utf-8-sig"),
            style=subtitle_style,
            width=width,
            height=height,
        )
        cue_count = ass_content.count("\nDialogue:")

        # Sidecar next to the project, matching Kdenlive's {project}.ass pattern.
        sidecar = project_path.with_name(project_path.name + ".ass")
        sidecar.write_text(ass_content, encoding="utf-8")

        ws_root = _find_workspace_root(project_path) or ws
        create_snapshot(ws_root, project_path, description="before_subtitles_attach")

        new_project = st.attach_subtitle(
            project, str(sidecar), name=srt.stem
        )
        serialize_project(new_project, project_path)

        snap = create_snapshot(
            ws_root, project_path, description="after_subtitles_attach"
        )

        return _ok(
            {
                "project_file": str(project_path),
                "sidecar_path": str(sidecar),
                "srt_path": str(srt),
                "cue_count": cue_count,
                "subtitle_track_count": len(new_project.subtitles),
                "styled": subtitle_style is not None,
                "subtitles_list_json": st.subtitles_list_json(new_project),
                "snapshot_id": snap.snapshot_id,
            }
        )
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")


# ---------------------------------------------------------------------------
# subtitles_burn_in
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def subtitles_burn_in(
    workspace_path: str,
    project_file_or_media: str = "",
    srt_path: str = "",
    style=None,
    output_name: str = "",
) -> dict:
    """Burn subtitles into a delivered media file (media/processed/).

    ffmpeg bakes the subtitle pixels via the ``ass`` filter.  If a ``.kdenlive``
    project is passed, it is rendered to a temporary video with melt first; a
    media file is burned directly.  Works today regardless of project subtitle
    support.

    Args:
        workspace_path: Path to the workspace root directory.
        project_file_or_media: A .kdenlive project or a media file. Empty =
            latest working copy.
        srt_path: Path to the SRT.  Empty = latest ``reports/*.srt``.
        style: Optional styling (see ``subtitles_attach``).
        output_name: Output filename under media/processed/ (default
            ``{stem}_subtitled.mp4``).

    Returns a success dict with the burned output path.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).")
        ws = Path(workspace_path)
        if not ws.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).", path=workspace_path)
        if not shutil.which("ffmpeg"):
            return missing_binary("ffmpeg", "apt install ffmpeg (Debian/Ubuntu) or brew install ffmpeg (macOS).")

        srt = _resolve_srt(workspace_path, srt_path)
        subtitle_style = st.SubtitleStyle.from_input(style)

        # Resolve the source: project -> render to mp4; media -> use directly.
        if project_file_or_media and project_file_or_media.endswith(".kdenlive"):
            source_kind = "project"
            source = _resolve_project(workspace_path, project_file_or_media)
        elif not project_file_or_media:
            source_kind = "project"
            source = _resolve_project(workspace_path, "")
        else:
            source = _resolve(project_file_or_media)
            if not source.exists():
                return err(f"Media not found: {project_file_or_media}", suggestion="Pass an existing media file or .kdenlive project; it resolves under the workspace root unless absolute.")
            source_kind = "media"

        processed = ws / "media" / "processed"
        processed.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="ff-burnin-") as tmp:
            tmpdir = Path(tmp)
            # ASS sidecar with styling baked in.
            ass_path = tmpdir / "subs.ass"
            ass_path.write_text(
                st.srt_to_ass(srt.read_text(encoding="utf-8-sig"), style=subtitle_style),
                encoding="utf-8",
            )

            if source_kind == "project":
                if not shutil.which("melt"):
                    return missing_binary("melt", "apt install melt (Debian/Ubuntu) or brew install mlt (macOS).")
                rendered = tmpdir / "render.mp4"
                content_frames = _project_frame_count(source)
                melt_cmd = [
                    "melt", str(source), f"out={max(0, content_frames - 1)}",
                    "-consumer", f"avformat:{rendered}",
                    "vcodec=libx264", "acodec=aac",
                ]
                proc = subprocess.run(
                    melt_cmd, capture_output=True, text=True, timeout=600
                )
                if not rendered.exists():
                    return operation_failed(
                        f"melt failed to render project (rc={proc.returncode})",
                        cause=proc.stderr[-400:], suggestion="The external command exited non-zero; the stderr tail is in 'cause'. Check the input media/codecs and that the tool's filters are supported by your ffmpeg/melt build.",
                    )
                media_input = rendered
            else:
                media_input = source

            stem = (source if source_kind == "media" else source).stem
            out_name = output_name or f"{stem}_subtitled.mp4"
            out_path = processed / out_name

            result = run_ffmpeg(
                args=["-vf", f"ass={_escape_ff(ass_path)}", "-c:a", "copy"],
                input_path=media_input,
                output_path=out_path,
            )
            if not result.success or not out_path.exists():
                return operation_failed(
                    "ffmpeg burn-in failed",
                    cause=result.stderr[-400:], suggestion="The external command exited non-zero; the stderr tail is in 'cause'. Check the input media/codecs and that the tool's filters are supported by your ffmpeg/melt build.",
                )

        return _ok(
            {
                "output_path": str(out_path),
                "source": str(source),
                "source_kind": source_kind,
                "srt_path": str(srt),
                "styled": subtitle_style is not None,
            }
        )
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")


def _project_frame_count(project_path: Path) -> int:
    """Best-effort timeline length in frames for bounding a melt render."""
    try:
        project = parse_project(project_path)
        max_len = 0
        for playlist in project.playlists:
            total = sum(
                max(0, e.out_point - e.in_point + 1)
                for e in playlist.entries
            )
            max_len = max(max_len, total)
        return max_len if max_len > 0 else 250
    except Exception:
        return 250
