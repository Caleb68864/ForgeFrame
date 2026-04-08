"""Ingest pipeline: scan, proxy, transcribe, detect silence."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.app.config import Config
from workshop_video_brain.core.models import (
    MediaAsset,
    ProxyStatus,
    TranscriptStatus,
    Workspace,
)
from workshop_video_brain.core.utils.paths import ensure_dir, safe_filename
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import (
    ProxyPolicy,
    generate_proxy,
    needs_proxy,
    proxy_path_for,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence
from workshop_video_brain.edit_mcp.adapters.stt import whisper_engine
from workshop_video_brain.workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


@dataclass
class IngestReport:
    """Summary of a completed ingest run."""

    scanned_count: int = 0
    proxied_count: int = 0
    transcribed_count: int = 0
    silence_detected_count: int = 0
    errors: list[str] = field(default_factory=list)


def _transcript_json_path(transcripts_dir: Path, asset: MediaAsset) -> Path:
    stem = safe_filename(Path(asset.path).stem)
    return transcripts_dir / f"{stem}_transcript.json"


def _silence_json_path(markers_dir: Path, asset: MediaAsset) -> Path:
    stem = safe_filename(Path(asset.path).stem)
    return markers_dir / f"{stem}_silence.json"


def run_ingest(workspace: Workspace, config: Config) -> IngestReport:
    """Run the full ingest pipeline for *workspace*.

    Steps per asset:
    1. Scan workspace media/raw/ for media files.
    2. Skip asset if transcript JSON already exists (idempotency).
    3. Generate proxy if needed and not already present.
    4. Extract audio, run Whisper transcription.
    5. Run silence detection.
    6. Save artifacts: transcript .json / .txt / .srt in transcripts/,
       silence .json in markers/.
    7. Update workspace manifest after all assets are processed.

    Errors are caught per-asset so one bad file does not stop the pipeline.

    Returns:
        :class:`IngestReport` summarising the run.
    """
    report = IngestReport()

    ws_root = Path(workspace.workspace_root)
    raw_dir = ws_root / "media" / "raw"
    proxy_dir = ws_root / "media" / "proxies"
    audio_dir = ws_root / "media" / "derived_audio"
    transcripts_dir = ws_root / "transcripts"
    markers_dir = ws_root / "markers"

    # Ensure all required directories exist
    for d in (raw_dir, proxy_dir, audio_dir, transcripts_dir, markers_dir):
        ensure_dir(d)

    # 1. Scan for media assets
    if not raw_dir.exists():
        logger.warning("media/raw directory does not exist: %s", raw_dir)
        return report

    assets = scan_directory(raw_dir)
    report.scanned_count = len(assets)
    logger.info("Scanned %d media asset(s) in %s", report.scanned_count, raw_dir)

    proxy_policy = ProxyPolicy()

    for asset in assets:
        asset_name = Path(asset.path).name
        try:
            _process_asset(
                asset=asset,
                proxy_dir=proxy_dir,
                audio_dir=audio_dir,
                transcripts_dir=transcripts_dir,
                markers_dir=markers_dir,
                config=config,
                proxy_policy=proxy_policy,
                report=report,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Error processing {asset_name}: {exc}"
            logger.error(msg)
            report.errors.append(msg)

    # 7. Persist the workspace manifest
    try:
        WorkspaceManager.save_manifest(workspace)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not save workspace manifest: %s", exc)

    logger.info(
        "Ingest complete: scanned=%d proxied=%d transcribed=%d silence=%d errors=%d",
        report.scanned_count,
        report.proxied_count,
        report.transcribed_count,
        report.silence_detected_count,
        len(report.errors),
    )
    return report


def _process_asset(
    asset: MediaAsset,
    proxy_dir: Path,
    audio_dir: Path,
    transcripts_dir: Path,
    markers_dir: Path,
    config: Config,
    proxy_policy: ProxyPolicy,
    report: IngestReport,
) -> None:
    """Process a single asset through the ingest pipeline."""
    asset_path = Path(asset.path)
    stem = safe_filename(asset_path.stem)

    logger.info("Processing asset: %s", asset_path.name)

    # 2. Idempotency: skip if transcript JSON already exists
    transcript_json = _transcript_json_path(transcripts_dir, asset)
    if transcript_json.exists():
        logger.info("Transcript already exists for %s -- skipping", asset_path.name)
        return

    # 3. Proxy generation
    if config.ffmpeg_available and needs_proxy(asset, proxy_policy):
        existing_proxy = proxy_path_for(asset, proxy_dir)
        if not (existing_proxy.exists() and
                existing_proxy.stat().st_mtime >= asset_path.stat().st_mtime):
            try:
                proxy_out = generate_proxy(asset, proxy_dir, proxy_policy)
                asset.proxy_path = str(proxy_out)
                asset.proxy_status = ProxyStatus.ready
                report.proxied_count += 1
                logger.info("Proxy generated: %s", proxy_out)
            except Exception as exc:  # noqa: BLE001
                asset.proxy_status = ProxyStatus.failed
                logger.warning("Proxy generation failed for %s: %s", asset_path.name, exc)
        else:
            asset.proxy_path = str(existing_proxy)
            asset.proxy_status = ProxyStatus.ready
    elif asset.media_type == "video":
        asset.proxy_status = ProxyStatus.not_needed

    # 4. Transcription (audio or video)
    if not config.ffmpeg_available:
        logger.warning("FFmpeg unavailable; skipping transcription for %s", asset_path.name)
        return

    if not whisper_engine.is_available():
        logger.warning("No Whisper backend; skipping transcription for %s", asset_path.name)
        return

    # Extract audio to WAV if needed
    audio_path = audio_dir / f"{stem}_audio.wav"
    if not audio_path.exists():
        try:
            whisper_engine.extract_audio(asset_path, audio_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Audio extraction failed for %s: %s", asset_path.name, exc)
            return

    # Transcribe
    asset.transcript_status = TranscriptStatus.processing
    try:
        transcript = whisper_engine.transcribe(
            audio_path=audio_path,
            model=config.whisper_model,
            asset_id=asset.id,
        )
        asset.transcript_status = TranscriptStatus.completed
    except Exception as exc:  # noqa: BLE001
        asset.transcript_status = TranscriptStatus.failed
        logger.warning("Transcription failed for %s: %s", asset_path.name, exc)
        return

    # 6. Save transcript artifacts
    transcript_json.write_text(whisper_engine.transcript_to_json(transcript), encoding="utf-8")

    txt_path = transcripts_dir / f"{stem}_transcript.txt"
    txt_path.write_text(transcript.raw_text, encoding="utf-8")

    srt_path = transcripts_dir / f"{stem}_transcript.srt"
    srt_path.write_text(whisper_engine.transcript_to_srt(transcript), encoding="utf-8")

    report.transcribed_count += 1
    logger.info("Transcript saved: %s", transcript_json)

    # 5. Silence detection
    try:
        silence_gaps = detect_silence(asset_path)
        if silence_gaps:
            report.silence_detected_count += 1

        silence_out = _silence_json_path(markers_dir, asset)
        silence_data = [
            {"start": start, "end": end}
            for start, end in silence_gaps
        ]
        silence_out.write_text(
            json.dumps(silence_data, indent=2), encoding="utf-8"
        )
        logger.info("Silence markers saved: %s (%d gap(s))", silence_out, len(silence_gaps))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Silence detection failed for %s: %s", asset_path.name, exc)
