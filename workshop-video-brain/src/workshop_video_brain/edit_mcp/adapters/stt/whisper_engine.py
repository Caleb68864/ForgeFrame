"""Whisper STT engine adapter with faster-whisper primary and whisper fallback."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from uuid import UUID

from workshop_video_brain.core.models import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """Return True if at least one Whisper backend is importable."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        pass
    return False


def _has_faster_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def extract_audio(video_path: Path, output_path: Path) -> Path:
    """Extract a 16-kHz mono PCM WAV from *video_path* into *output_path*.

    Args:
        video_path: Source video (or audio) file.
        output_path: Destination WAV file path.

    Returns:
        *output_path* after successful extraction.

    Raises:
        subprocess.CalledProcessError: if ffmpeg fails.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-y",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def transcribe(
    audio_path: Path,
    model: str = "small",
    language: str | None = None,
    asset_id: UUID | None = None,
) -> Transcript:
    """Transcribe *audio_path* using faster-whisper (or whisper as fallback).

    Args:
        audio_path: Path to audio file (WAV recommended).
        model: Whisper model size (tiny, base, small, medium, large).
        language: ISO-639-1 language code, or None for auto-detection.
        asset_id: UUID of the associated :class:`MediaAsset`.

    Returns:
        A :class:`Transcript` populated with segments and raw text.

    Raises:
        RuntimeError: if no Whisper backend is installed.
    """
    from uuid import uuid4

    audio_path = Path(audio_path)
    _asset_id = asset_id if asset_id is not None else uuid4()

    if _has_faster_whisper():
        return _transcribe_faster_whisper(audio_path, model, language, _asset_id)
    else:
        try:
            import whisper  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "No Whisper backend available. "
                "Install faster-whisper or openai-whisper."
            ) from exc
        return _transcribe_openai_whisper(audio_path, model, language, _asset_id)


def _transcribe_faster_whisper(
    audio_path: Path,
    model: str,
    language: str | None,
    asset_id: UUID,
) -> Transcript:
    from faster_whisper import WhisperModel

    logger.info("Transcribing %s with faster-whisper model=%s", audio_path, model)

    wm = WhisperModel(model, device="cpu", compute_type="int8")
    kwargs: dict = {}
    if language:
        kwargs["language"] = language

    segments_iter, info = wm.transcribe(str(audio_path), **kwargs)

    segments: list[TranscriptSegment] = []
    raw_parts: list[str] = []

    for seg in segments_iter:
        ts = TranscriptSegment(
            start_seconds=seg.start,
            end_seconds=seg.end,
            text=seg.text.strip(),
            confidence=float(getattr(seg, "avg_logprob", 1.0)),
        )
        segments.append(ts)
        raw_parts.append(seg.text.strip())

    detected_lang = getattr(info, "language", language or "")

    return Transcript(
        asset_id=asset_id,
        engine="faster-whisper",
        model=model,
        language=detected_lang,
        segments=segments,
        raw_text=" ".join(raw_parts),
    )


def _transcribe_openai_whisper(
    audio_path: Path,
    model: str,
    language: str | None,
    asset_id: UUID,
) -> Transcript:
    import whisper

    logger.info("Transcribing %s with openai-whisper model=%s", audio_path, model)

    wm = whisper.load_model(model)
    kwargs: dict = {}
    if language:
        kwargs["language"] = language

    result = wm.transcribe(str(audio_path), **kwargs)

    raw_segments = result.get("segments", [])
    segments: list[TranscriptSegment] = []
    for seg in raw_segments:
        ts = TranscriptSegment(
            start_seconds=float(seg["start"]),
            end_seconds=float(seg["end"]),
            text=seg["text"].strip(),
        )
        segments.append(ts)

    return Transcript(
        asset_id=asset_id,
        engine="whisper",
        model=model,
        language=result.get("language", language or ""),
        segments=segments,
        raw_text=result.get("text", "").strip(),
    )


def transcript_to_srt(transcript: Transcript) -> str:
    """Format *transcript* as an SRT subtitle file string."""

    def _fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: list[str] = []
    for idx, seg in enumerate(transcript.segments, start=1):
        lines.append(str(idx))
        lines.append(f"{_fmt_time(seg.start_seconds)} --> {_fmt_time(seg.end_seconds)}")
        lines.append(seg.text)
        lines.append("")  # blank line between entries

    return "\n".join(lines)


def transcript_to_json(transcript: Transcript) -> str:
    """Serialize *transcript* to a JSON string."""
    return transcript.to_json()
