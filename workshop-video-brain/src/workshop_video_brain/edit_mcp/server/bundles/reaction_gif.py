"""Reaction-GIF MCP tools: ``gif_find_line``, ``gif_fetch_scene``, ``gif_render``.

Auto-imported by ``server/bundles/__init__.py``. Thin shells over
``edit_mcp.pipelines.reaction_gif`` (the vault ``make_gif.py`` find -> scene
-> gif flow). Work from evidence: subtitle cues, contact sheets and shot-cut
times, never guessed timestamps. Nothing here writes a Kdenlive project.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.server.errors import (
    invalid_input,
    missing_binary,
    missing_file,
    operation_failed,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.server import mcp


def _ytdlp_errors(exc: Exception) -> dict | None:
    from workshop_video_brain.edit_mcp.adapters.youtube.ytdlp_cli import (
        YtDlpError,
        YtDlpNotFound,
    )

    if isinstance(exc, YtDlpNotFound):
        return missing_binary("yt-dlp", "sudo pacman -S yt-dlp, or pipx install yt-dlp")
    if isinstance(exc, YtDlpError):
        return operation_failed(
            "yt-dlp could not fetch the video.",
            exc,
            "Check the URL plays in a browser, then run `yt-dlp -F <url>` to list formats.",
        )
    return None


@mcp.tool()
@tool_guard
def gif_find_line(
    source: str,
    text: str,
    context: int = 4,
    picture_offset: float = 3.0,
    work_dir: str = "",
) -> dict:
    """Step 1 of a reaction GIF: find a spoken line in a video's subtitles.

    Searches case-insensitively and returns EVERY match (lines repeat), each
    with the ``context`` cues before it and a ~30 s ``suggested_window`` for
    ``gif_fetch_scene``, centred on the cue start plus ``picture_offset``
    (subtitles run ~3 s ahead of the picture). Downloads subtitles only, no
    video. If there are several matches, compare their contact sheets or ask
    the user which scene; never pick one by guessing.

    Args:
        source: Video URL (Tubi first, YouTube fallback) or a local ``.srt``.
        text: The line to find, e.g. ``"I've got it"``.
        context: Preceding cues to include per match.
        picture_offset: Seconds the picture lags the subtitle.
        work_dir: Where subtitles are saved; default ``<gallery>/_work/subs``.

    Returns:
        ``query``, ``subtitle_files``, ``match_count`` and ``matches`` (each:
        ``cue``, ``context``, ``picture_time``, ``suggested_window``).
    """
    from workshop_video_brain.edit_mcp.pipelines.reaction_gif import find_line

    if not text.strip():
        return invalid_input("text is empty.", "Pass the line to search for.", param="text")
    try:
        result = find_line(
            source, text, work_dir=Path(work_dir) if work_dir else None,
            context=context, picture_offset=picture_offset,
        )
    except Exception as exc:  # yt-dlp errors are classified; others re-raise
        mapped = _ytdlp_errors(exc)
        if mapped is None:
            raise
        return mapped
    return _ok(result)


@mcp.tool()
@tool_guard
def gif_fetch_scene(
    source: str,
    start: str = "",
    end: str = "",
    out_dir: str = "",
    contact_sheet: bool = True,
    fine_sheet_at: str = "",
    waveform_at: str = "",
) -> dict:
    """Step 2: download just the scene and pin exact frames.

    With a URL, downloads only ``start``-``end`` (MM:SS, a ~30 s window from
    ``gif_find_line``) to ``out_dir/clip.mp4``. With a local clip, nothing is
    downloaded. Returns the shot-cut times (``scene_cuts``) and
    ``end_before_cuts`` (each cut minus 0.04 s, to stop on the frame before a
    cutaway), plus a 2 fps contact sheet labelled with clip time. Optional:
    a fine 6 fps sheet over 3 s from ``fine_sheet_at`` and a waveform from
    ``waveform_at`` (clip seconds; speech shows as short bursts). Look at the
    sheets before choosing GIF times.

    Args:
        source: Video URL, or a local clip already downloaded.
        start: Window start in the source video (URL only), e.g. ``"20:15"``.
        end: Window end (URL only), e.g. ``"20:45"``.
        out_dir: Folder for clip.mp4; default ``<gallery>/_work/scene-<s>-<e>``.
        contact_sheet: Write the 2 fps contact sheet.
        fine_sheet_at: Clip time for a 6 fps / 3 s sheet, e.g. ``"15"``.
        waveform_at: Clip time for a 6 s waveform picture.

    Returns:
        ``clip``, ``scene_cuts``, ``end_before_cuts``, ``contact_sheet`` and,
        when asked, ``fine_sheet`` and ``waveform`` (PNG paths).
    """
    from workshop_video_brain.edit_mcp.pipelines.reaction_gif import fetch_scene

    try:
        result = fetch_scene(
            source,
            start or None,
            end or None,
            out_dir=Path(out_dir) if out_dir else None,
            contact_sheet=contact_sheet,
            fine_sheet_at=fine_sheet_at or None,
            waveform_at=waveform_at or None,
        )
    except ValueError as exc:
        return invalid_input(
            str(exc),
            "Times are seconds or MM:SS; a URL needs both start and end, end after start.",
        )
    except Exception as exc:
        mapped = _ytdlp_errors(exc)
        if mapped is None:
            raise
        return mapped
    return _ok(result)


@mcp.tool()
@tool_guard
def gif_render(
    clip_path: str,
    start: str,
    end: str,
    caption: str = "",
    output_path: str = "",
    gallery_dir: str = "",
    width: int = 480,
    fps: int = 15,
) -> dict:
    """Step 3: render the captioned GIF and its check strip.

    15 fps, 480 px wide, lanczos; white Liberation Sans Bold caption with a
    black outline, bottom-centre, sized from the width; two-pass palette with
    bayer dither. The caption goes through a text file, so apostrophes are
    safe. Aim for a 2-3 s loop starting just before the action; to stop
    before a cutaway use an ``end_before_cuts`` time from ``gif_fetch_scene``.
    Then LOOK at ``check_strip`` (10 frames): caption fits, no frames from
    the next shot.

    Args:
        clip_path: The scene clip (``clip.mp4`` from ``gif_fetch_scene``).
        start: Seconds (or MM:SS) within the clip, e.g. ``"15.5"``.
        end: Seconds within the clip, e.g. ``"17.52"``.
        caption: Caption text; empty for none.
        output_path: GIF path; default ``<gallery>/<caption-slug>.gif``.
        gallery_dir: GIF gallery; default ``$WVB_GIF_GALLERY`` or
            ``~/Pictures/Reaction GIFs``.
        width: Output width in px.
        fps: Output frame rate.

    Returns:
        ``path``, ``size_bytes``, ``size_mb``, ``duration``, ``fps``,
        ``width``, ``height``, ``frames``, ``check_strip`` and ``warnings``.
    """
    from workshop_video_brain.edit_mcp.pipelines.reaction_gif import render_gif

    if not Path(clip_path).expanduser().is_file():
        return missing_file(clip_path, "clip")
    if width < 16 or fps < 1 or fps > 50:
        return invalid_input(
            f"width={width}, fps={fps} is out of range.",
            "Use width >= 16 (480 is the default) and fps 1-50 (15 is the default).",
        )
    try:
        result = render_gif(
            Path(clip_path).expanduser(), start, end, caption or None,
            output=Path(output_path).expanduser() if output_path else None,
            gallery_dir=Path(gallery_dir).expanduser() if gallery_dir else None,
            width=width, fps=fps,
        )
    except ValueError as exc:
        return invalid_input(
            str(exc), "start and end are seconds or MM:SS within the clip, end after start."
        )
    return _ok(result)
