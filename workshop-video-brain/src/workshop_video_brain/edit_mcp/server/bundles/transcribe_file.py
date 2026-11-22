"""``transcribe_file``: speech to SRT / VTT / TXT and word-level JSON for any media file (no workspace)."""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import source_path
from workshop_video_brain.edit_mcp.server.errors import (
    invalid_input,
    media_unreadable,
    missing_dependency,
    operation_failed,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok

_MODELS = {"tiny", "base", "small", "medium", "large-v3", "turbo"}
_MODELS |= {f"{m}.en" for m in ("tiny", "base", "small", "medium")}


@mcp.tool()
@tool_guard
def transcribe_file(source: str, formats: str = "srt,vtt,json", model: str = "small", language: str = "",
                    max_line_length: int = 42, max_cue_seconds: float = 5.0, output_dir: str = "",
                    overwrite: bool = False) -> dict:
    """Transcribe a media file with faster-whisper into subtitle files.

    ``formats``: comma list of srt, vtt, txt, json (``<name>_transcript.json``
    keeps word timings, which text-based editing uses). ``model``: tiny,
    base, small (default), medium, large-v3, turbo, or a ``.en`` variant;
    models download on first use. Output goes beside the source (or
    ``media/processed/`` for a ``media/raw/`` source) unless ``output_dir``.
    Transcription runs in-process and is not time-bounded: send long files
    through ``job_submit``.
    """
    from pathlib import Path

    from workshop_video_brain.edit_mcp.adapters.stt import whisper_engine
    from workshop_video_brain.edit_mcp.pipelines.media_files import default_output_dir
    from workshop_video_brain.edit_mcp.pipelines.transcribe_file import FORMATS, transcribe_to_files

    src = source_path(source)
    if isinstance(src, dict):
        return src
    wanted = [f.strip().lower() for f in formats.split(",") if f.strip()]
    unknown = [f for f in wanted if f not in FORMATS]
    if not wanted or unknown:
        return invalid_input(f"Unknown format(s): {', '.join(unknown) or '(none given)'}",
                             f"Use a comma list of {', '.join(FORMATS)}.", param="formats")
    if model not in _MODELS:
        return invalid_input(f"Unknown model {model!r}", f"Use one of {', '.join(sorted(_MODELS))}.", param="model")
    if not whisper_engine.is_available():
        return missing_dependency("faster-whisper", "uv pip install faster-whisper")
    out_dir = Path(output_dir) if output_dir else default_output_dir(src)
    try:
        done = transcribe_to_files(src, out_dir, src.stem, wanted, model, language or None, max_line_length,
                                   max_cue_seconds, overwrite)
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return media_unreadable(str(src), exc)
        return invalid_input(str(exc), "Choose another output_dir or pass overwrite=true.")
    except (OSError, RuntimeError) as exc:
        return operation_failed(f"Transcription failed: {exc}", cause=exc,
                                suggestion="If the model could not be loaded, run once with network access so it "
                                           "downloads, or use a model that is already cached (e.g. tiny).")
    return _ok({"source": str(src), **done})
