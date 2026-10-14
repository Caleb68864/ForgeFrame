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


def run_ingest(workspace: Workspace, config: Config, *, progress=None, pending_output=None, completed_output=None) -> IngestReport:
    """Run the full ingest pipeline for *workspace*.

    Steps per asset:
    1. Scan workspace media/raw/ for media files.
    2. Resume fresh artifacts independently.
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

    for index, asset in enumerate(assets):
        asset_name = Path(asset.path).name
        if progress:
            progress("transcribe", index, len(assets), source=asset.path)
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
                pending_output=pending_output,
                completed_output=completed_output,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Error processing {asset_name}: {exc}"
            logger.error(msg)
            report.errors.append(msg)
    if progress:
        progress("transcribe", len(assets), len(assets))

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
    pending_output=None,
    completed_output=None,
) -> None:
    """Process a single asset through the ingest pipeline."""
    asset_path = Path(asset.path)
    stem = safe_filename(asset_path.stem)

    logger.info("Processing asset: %s", asset_path.name)

    # Resume each artifact independently: an existing transcript must not hide
    # a missing proxy, subtitle, or silence report from interrupted work.
    transcript_json = _transcript_json_path(transcripts_dir, asset)
    source_mtime = asset_path.stat().st_mtime

    def fresh(path: Path) -> bool:
        return path.is_file() and path.stat().st_size > 0 and path.stat().st_mtime >= source_mtime

    # 3. Proxy generation
    if config.ffmpeg_available and needs_proxy(asset, proxy_policy):
        existing_proxy = proxy_path_for(asset, proxy_dir)
        if not fresh(existing_proxy):
            try:
                if pending_output:
                    pending_output(existing_proxy)
                if existing_proxy.is_file() and existing_proxy.stat().st_size == 0:
                    existing_proxy.unlink()
                proxy_out = generate_proxy(asset, proxy_dir, proxy_policy)
                if completed_output:
                    completed_output(proxy_out)
                asset.proxy_path = str(proxy_out)
                asset.proxy_status = ProxyStatus.ready
                report.proxied_count += 1
                logger.info("Proxy generated: %s", proxy_out)
            except Exception as exc:  # noqa: BLE001
                asset.proxy_status = ProxyStatus.failed
                logger.warning("Proxy generation failed for %s: %s", asset_path.name, exc)
                report.errors.append(f"Proxy generation failed for {asset_path.name}: {exc}")
        else:
            asset.proxy_path = str(existing_proxy)
            asset.proxy_status = ProxyStatus.ready
    elif asset.media_type == "video":
        asset.proxy_status = ProxyStatus.not_needed

    if not asset.audio_codec and not asset.channels and asset.media_type != "audio":
        logger.info("No audio stream in %s; skipping transcription", asset_path.name)
        return

    # 4. Transcription (audio or video)
    if not config.ffmpeg_available:
        logger.warning("FFmpeg unavailable; skipping transcription for %s", asset_path.name)
        return

    if not fresh(transcript_json) and not whisper_engine.is_available():
        logger.warning("No Whisper backend; skipping transcription for %s", asset_path.name)
        return

    # Extract audio to WAV if needed
    audio_path = audio_dir / f"{stem}_audio.wav"
    # Transcribe
    asset.transcript_status = TranscriptStatus.processing
    try:
        from workshop_video_brain.core.models.transcript import Transcript
        if fresh(transcript_json):
            transcript = Transcript.from_json(transcript_json.read_text(encoding="utf-8"))
        else:
            if not fresh(audio_path):
                if pending_output:
                    pending_output(audio_path)
                whisper_engine.extract_audio(asset_path, audio_path)
                if completed_output:
                    completed_output(audio_path)
            transcript = whisper_engine.transcribe(
                audio_path=audio_path, model=config.whisper_model, asset_id=asset.id,
            )
            report.transcribed_count += 1
        asset.transcript_status = TranscriptStatus.completed
    except Exception as exc:  # noqa: BLE001
        asset.transcript_status = TranscriptStatus.failed
        logger.warning("Transcription failed for %s: %s", asset_path.name, exc)
        report.errors.append(f"Transcription failed for {asset_path.name}: {exc}")
        return

    # 6. Save transcript artifacts
    from workshop_video_brain.workspace.safe_write import atomic_write_text
    if not fresh(transcript_json):
        atomic_write_text(transcript_json, whisper_engine.transcript_to_json(transcript))

    txt_path = transcripts_dir / f"{stem}_transcript.txt"
    if not fresh(txt_path):
        atomic_write_text(txt_path, transcript.raw_text)

    srt_path = transcripts_dir / f"{stem}_transcript.srt"
    if not fresh(srt_path):
        atomic_write_text(srt_path, whisper_engine.transcript_to_srt(transcript))

    logger.info("Transcript saved: %s", transcript_json)

    # 5. Silence detection
    silence_out = _silence_json_path(markers_dir, asset)
    if fresh(silence_out):
        try:
            json.loads(silence_out.read_text(encoding="utf-8"))
            return
        except (ValueError, OSError):
            pass
    try:
        silence_gaps = detect_silence(asset_path)
        if silence_gaps:
            report.silence_detected_count += 1

        silence_data = [
            {"start": start, "end": end}
            for start, end in silence_gaps
        ]
        atomic_write_text(silence_out,
            json.dumps(silence_data, indent=2), encoding="utf-8"
        )
        logger.info("Silence markers saved: %s (%d gap(s))", silence_out, len(silence_gaps))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Silence detection failed for %s: %s", asset_path.name, exc)
        report.errors.append(f"Silence detection failed for {asset_path.name}: {exc}")
