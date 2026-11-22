"""``audio_loudness``: measure (and optionally normalize) a file's loudness, no workspace needed."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    invalid_input,
    media_unreadable,
    missing_file,
    not_found,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def audio_loudness(source: str, target_lufs: float = 0.0, true_peak: float = -1.5, lra: float = 11.0,
                   output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """Integrated loudness (LUFS), true peak and loudness range of a file, or of every media file in a folder.

    ``target_lufs`` 0 measures only. A negative target (e.g. -14 for YouTube,
    -16 for podcasts) also writes a normalized copy of a single file with the
    two-pass loudnorm (lands within ~0.1 LU; video is copied). Default output
    ``<name>_normalized<ext>``.
    """
    from workshop_video_brain.edit_mcp.pipelines.analysis_common import iter_media_files
    from workshop_video_brain.edit_mcp.pipelines.loudness_scan import scan_loudness
    from workshop_video_brain.edit_mcp.pipelines.loudnorm_two_pass import normalize_two_pass_file
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary, resolve_output
    from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
        cleanup_partial_output,
        error_from_pipeline_result,
    )

    if not source or not source.strip():
        return invalid_input("source must be a file or folder", "Pass the media file or a folder of them.")
    target = Path(source).expanduser()
    if not target.exists():
        return missing_file(str(target), "source")
    if target_lufs > 0:
        return invalid_input(f"target_lufs must be negative (LUFS), got {target_lufs}",
                             "Use e.g. -14 for YouTube or -16 for podcasts; 0 measures only.")
    files = iter_media_files(target.resolve())
    if not files:
        return not_found("Media files", str(target), hint="The folder has no audio or video files.")
    if target_lufs == 0:
        report = scan_loudness(files)
        if report["results"] and not any(r.get("ok") for r in report["results"]):
            return media_unreadable(str(files[0]), report["results"][0].get("error"))
        return _ok(report)
    if target.is_dir():
        return invalid_input("Normalize one file at a time",
                             "Pass a single file as source (with output_dir if you like), or target_lufs=0 to measure.")
    try:
        out = resolve_output(target.resolve(), output_path, output_dir, suffix="_normalized", overwrite=overwrite)
    except ValueError as exc:
        return invalid_input(str(exc), "Choose another output_path or pass overwrite=true.")
    result = normalize_two_pass_file(target.resolve(), out, target_i=target_lufs, target_tp=true_peak,
                                     target_lra=lra)
    if not result.get("success"):
        cleanup_partial_output(out)
        return error_from_pipeline_result(result, "Loudness normalization failed", path=str(target))
    return _ok({**output_summary(out), "source": str(target), "target_lufs": target_lufs,
                "measured": result.get("measured"), "achieved_i": result.get("achieved_i"),
                "normalization_type": result.get("normalization_type"), "warning": result.get("warning")})
