"""Shared bits for the plain-file media tool shells (skipped by discovery)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import cleanup_partial_output
from workshop_video_brain.edit_mcp.server.errors import invalid_input, missing_file, operation_failed


def source_path(source: str, param: str = "source") -> Path | dict:
    if not source or not str(source).strip():
        return invalid_input(f"{param} must be a file path", f"Pass the media file as {param}.", param=param)
    path = Path(source).expanduser()
    if not path.is_file():
        return missing_file(str(path), param)
    return path.resolve()


def ffmpeg_ok_or_error(result, output: Path, what: str) -> dict | None:
    if result.success:
        return None
    cleanup_partial_output(output)
    return operation_failed(
        f"{what} failed", cause=result.stderr_tail or "ffmpeg exited non-zero",
        suggestion="ffmpeg's own message is in 'cause'; check the input file plays and the options are valid.",
    )


def run_file_tool(source: str, *, suffix: str, ext: str | None, output_path: str, output_dir: str,
                  overwrite: bool, run, what: str, extra: dict | None = None) -> dict:
    """The common shell: validate source -> resolve output -> run -> map errors -> summary.

    ``run(src, out)`` returns an ``FFmpegResult``. A ``ValueError`` from it is the
    user's input (``invalid_input``); one starting "source has no" is a file
    without the needed stream (``media_unreadable``).
    """
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary, resolve_output
    from workshop_video_brain.edit_mcp.server.errors import media_unreadable
    from workshop_video_brain.edit_mcp.server.tools_helpers import _ok

    src = source_path(source)
    if isinstance(src, dict):
        return src
    try:
        out = resolve_output(src, output_path, output_dir, suffix=suffix, ext=ext, overwrite=overwrite)
        result = run(src, out)
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return media_unreadable(str(src), exc)
        return invalid_input(str(exc), f"Check the {what.lower()} options against the tool's description.")
    problem = ffmpeg_ok_or_error(result, out, what)
    if problem:
        return problem
    return _ok({**output_summary(out), "source": str(src), **(extra or {})})
