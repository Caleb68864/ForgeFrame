"""``clips_qc_scan`` MCP tool -- batch clip QC triage.

Auto-imported by ``server/bundles/__init__.py``. Analysis-only: reads media and
writes a JSON report into ``reports/`` -- no snapshots, no project writes.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines.analysis_common import (
    iter_media_files,
    resolve_under_workspace,
    timestamp_slug,
    write_json_report,
)
from workshop_video_brain.edit_mcp.pipelines.qc_scan import scan_batch
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)
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
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)


@mcp.tool()
@tool_guard
def clips_qc_scan(
    workspace_path: str,
    source_or_dir: str = "",
    black_min: float = 0.5,
    black_pix_th: float = 0.10,
    freeze_min: float = 0.5,
    blur_flag_threshold: float = 15.0,
    yavg_min: float = 40.0,
    yavg_max: float = 235.0,
    silence_db: float = -30.0,
    silence_min: float = 0.6,
    silence_ratio_flag: float = 0.5,
    write_ratings: bool = False,
) -> dict:
    """Batch-scan clips for junk (black / frozen / blurry / mis-exposed / dead-air).

    Runs a single ``-f null -`` pass per clip combining ``blackdetect`` +
    ``freezedetect`` + ``blurdetect`` + ``signalstats`` + ``silencedetect`` and
    returns per-clip ``usable``/``flagged`` verdicts with reasons. Writes a JSON
    report to ``reports/`` and can push an auto-rating into the b-roll index.

    Args:
        workspace_path: Path to workspace root.
        source_or_dir: A clip path or a directory of clips (absolute or
            workspace-relative). Empty uses ``media/raw``.
        black_min: Min black-region seconds to flag (blackdetect ``d=``).
        black_pix_th: Blackdetect pixel threshold.
        freeze_min: Min frozen seconds to flag (freezedetect ``d=``).
        blur_flag_threshold: Avg ``lavfi.blur`` above this flags soft/OOF
            footage (higher = blurrier).
        yavg_min: Avg luma below this flags underexposure.
        yavg_max: Avg luma above this flags overexposure.
        silence_db: Silence noise floor in dBFS.
        silence_min: Min silence-gap seconds.
        silence_ratio_flag: Silence/duration above this flags mostly-dead-air.
        write_ratings: If True, write each verdict's rating into the b-roll
            index (usable=5, flagged=1); requires a configured vault.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)

        if source_or_dir and source_or_dir.strip():
            target = resolve_under_workspace(ws_path, source_or_dir)
        else:
            target = ws_path / "media" / "raw"

        clips = iter_media_files(target)
        if not clips:
            return _err(f"No media files found at: {target}")

        thresholds = {
            "black_min": black_min,
            "black_pix_th": black_pix_th,
            "freeze_min": freeze_min,
            "blur_flag_threshold": blur_flag_threshold,
            "yavg_min": yavg_min,
            "yavg_max": yavg_max,
            "silence_db": silence_db,
            "silence_min": silence_min,
            "silence_ratio_flag": silence_ratio_flag,
        }

        report = scan_batch(clips, thresholds)

        report_path = write_json_report(
            ws_path, f"qc_scan_{timestamp_slug()}.json", report
        )
        report["report_path"] = str(report_path)

        if write_ratings:
            report["ratings_written"] = _write_ratings(report["results"])

        return _ok(report)
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)


def _write_ratings(results: list[dict]) -> dict:
    """Push per-clip ratings into the b-roll index via existing functions."""
    try:
        from workshop_video_brain.edit_mcp.pipelines.broll_library import (
            _resolve_vault_path,
            tag_clip,
        )

        vault = _resolve_vault_path()
        if vault is None:
            return {"written": 0, "reason": "no vault configured"}

        count = 0
        for r in results:
            if not r.get("clip"):
                continue
            tag_clip(vault, r["clip"], rating=int(r.get("rating", 0)))
            count += 1
        return {"written": count}
    except Exception as exc:  # noqa: BLE001
        return {"written": 0, "reason": str(exc)}
