"""Audio processing tools built on FFmpeg."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegResult, run_ffmpeg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voice enhancement presets
# ---------------------------------------------------------------------------

VOICE_PRESETS: dict[str, dict] = {
    "youtube_voice": {
        "highpass_hz": 80,
        "noise_floor_db": -25,
        "compress_threshold_db": -18,
        "compress_ratio": 3.0,
        "target_lufs": -16.0,
        "limit_db": -1.0,
    },
    "podcast": {
        "highpass_hz": 60,
        "noise_floor_db": -20,
        "compress_threshold_db": -20,
        "compress_ratio": 4.0,
        "target_lufs": -16.0,
        "limit_db": -1.5,
    },
    "raw_cleanup": {
        "highpass_hz": 80,
        "noise_floor_db": -30,
        "compress_threshold_db": -15,
        "compress_ratio": 2.0,
        "target_lufs": -14.0,
        "limit_db": -1.0,
    },
}

# ---------------------------------------------------------------------------
# Individual processing tools
# ---------------------------------------------------------------------------


def normalize_audio(
    input_path: Path,
    output_path: Path,
    target_lufs: float = -16.0,
    true_peak: float = -1.5,
    loudness_range: float = 11.0,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Normalize audio to consistent loudness (EBU R128 / YouTube standard).

    Uses loudnorm filter targeting -16 LUFS (YouTube recommended).

    Args:
        input_path: Source audio/video file.
        output_path: Destination file.
        target_lufs: Integrated loudness target in LUFS (default -16.0).
        true_peak: Maximum true peak in dBTP (default -1.5).
        loudness_range: Loudness range target in LU (default 11.0).
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    af = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={loudness_range}"
    return run_ffmpeg(
        ["-af", af],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def compress_audio(
    input_path: Path,
    output_path: Path,
    threshold_db: float = -18.0,
    ratio: float = 3.0,
    attack_ms: float = 5.0,
    release_ms: float = 50.0,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Reduce dynamic range -- make quiet parts louder, loud parts softer.

    Good for inconsistent speaking volume.

    Args:
        input_path: Source audio/video file.
        output_path: Destination file.
        threshold_db: Compression threshold in dB (default -18.0).
        ratio: Compression ratio (default 3.0).
        attack_ms: Attack time in ms (default 5.0).
        release_ms: Release time in ms (default 50.0).
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    af = (
        f"acompressor=threshold={threshold_db}dB"
        f":ratio={ratio}"
        f":attack={attack_ms}"
        f":release={release_ms}"
    )
    return run_ffmpeg(
        ["-af", af],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def remove_background_noise(
    input_path: Path,
    output_path: Path,
    noise_floor_db: float = -25.0,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Reduce constant background noise (fans, hum, room noise).

    Uses FFT-based denoise filter.

    Args:
        input_path: Source audio/video file.
        output_path: Destination file.
        noise_floor_db: Noise floor in dB (default -25.0).
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    af = f"afftdn=nf={noise_floor_db}"
    return run_ffmpeg(
        ["-af", af],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def highpass_filter(
    input_path: Path,
    output_path: Path,
    cutoff_hz: float = 80.0,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Remove low-frequency rumble (desk bumps, mic handling noise).

    Cuts frequencies below cutoff.

    Args:
        input_path: Source audio/video file.
        output_path: Destination file.
        cutoff_hz: High-pass filter cutoff frequency in Hz (default 80.0).
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    af = f"highpass=f={cutoff_hz}"
    return run_ffmpeg(
        ["-af", af],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def de_ess(
    input_path: Path,
    output_path: Path,
    frequency_hz: float = 6000.0,
    bandwidth: float = 2.0,
    gain_db: float = -5.0,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Reduce harsh 's' and 't' sounds in voice recordings.

    Targets the 4-8kHz sibilance range.

    Args:
        input_path: Source audio/video file.
        output_path: Destination file.
        frequency_hz: Center frequency for sibilance reduction (default 6000.0).
        bandwidth: Filter bandwidth in octaves (default 2.0).
        gain_db: Gain reduction in dB (default -5.0, negative = cut).
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    af = f"equalizer=f={frequency_hz}:t=q:w={bandwidth}:g={gain_db}"
    return run_ffmpeg(
        ["-af", af],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def remove_silence(
    input_path: Path,
    output_path: Path,
    threshold_db: float = -40.0,
    min_duration: float = 0.5,
    trim_start: bool = True,
    trim_end: bool = True,
    trim_middle: bool = False,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Trim silence from audio.

    Can trim start, end, and optionally middle silence.

    Args:
        input_path: Source audio/video file.
        output_path: Destination file.
        threshold_db: Silence detection threshold in dB (default -40.0).
        min_duration: Minimum silence duration to remove in seconds (default 0.5).
        trim_start: Remove silence at the start (default True).
        trim_end: Remove silence at the end (default True).
        trim_middle: Remove silence in the middle (default False).
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    parts: list[str] = ["silenceremove"]
    if trim_start:
        parts.append(f"start_periods=1:start_duration={min_duration}:start_threshold={threshold_db}dB")
    if trim_end:
        parts.append(f"stop_periods=-1:stop_duration={min_duration}:stop_threshold={threshold_db}dB")
    elif trim_middle:
        # trim_middle without trim_end: still need stop config
        parts.append(f"stop_periods=-1:stop_duration={min_duration}:stop_threshold={threshold_db}dB")

    if trim_middle and not trim_end:
        # already handled above
        pass

    af = ":".join(parts)
    return run_ffmpeg(
        ["-af", af],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def limit_peaks(
    input_path: Path,
    output_path: Path,
    limit_db: float = -1.0,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Prevent clipping by limiting maximum volume.

    Use as the final step to ensure no peaks exceed limit.

    Args:
        input_path: Source audio/video file.
        output_path: Destination file.
        limit_db: Peak limit in dB (default -1.0).
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    af = f"alimiter=limit={limit_db}dB"
    return run_ffmpeg(
        ["-af", af],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def convert_format(
    input_path: Path,
    output_path: Path,
    sample_rate: int = 44100,
    channels: int = 1,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Convert audio to a standard format (WAV by default, based on output extension).

    Standardizes sample rate and channels.

    Args:
        input_path: Source audio/video file.
        output_path: Destination file (extension determines format).
        sample_rate: Output sample rate in Hz (default 44100).
        channels: Number of output channels (default 1 = mono).
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    return run_ffmpeg(
        ["-ar", str(sample_rate), "-ac", str(channels)],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def export_compressed(
    input_path: Path,
    output_path: Path,
    bitrate: str = "192k",
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Export to compressed format (MP3/AAC based on output extension).

    High quality: 192k or 256k recommended for voice.

    Args:
        input_path: Source audio/video file.
        output_path: Destination file (extension determines codec).
        bitrate: Audio bitrate string (default "192k").
        overwrite: Overwrite output if it exists.
        dry_run: Return command without executing.

    Returns:
        FFmpegResult with success status and timing.
    """
    return run_ffmpeg(
        ["-b:a", bitrate],
        input_path=input_path,
        output_path=output_path,
        overwrite=overwrite,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Voice enhancement chain
# ---------------------------------------------------------------------------


def voice_enhance_chain(
    input_path: Path,
    output_path: Path,
    preset: str = "youtube_voice",
    include_de_ess: bool = True,
    dry_run: bool = False,
) -> dict:
    """Apply full voice-over enhancement pipeline in one call.

    Chain: highpass -> noise reduction -> compression -> normalization -> limiter
    Optionally includes de-esser after compression.

    Args:
        input_path: Raw audio/video file.
        output_path: Enhanced output.
        preset: One of "youtube_voice", "podcast", "raw_cleanup".
        include_de_ess: Whether to apply de-esser.
        dry_run: Return commands without executing.

    Returns:
        Dict with: success, steps (list of FFmpegResult dicts), final_output,
        preset_used.
    """
    params = VOICE_PRESETS.get(preset, VOICE_PRESETS["youtube_voice"])
    actual_preset = preset if preset in VOICE_PRESETS else "youtube_voice"

    steps: list[FFmpegResult] = []
    output_dir = output_path.parent
    stem = output_path.stem

    # Build temp file paths in the same directory as the output
    def _tmp(n: int) -> Path:
        return output_dir / f".{stem}_tmp{n}.wav"

    temp_files: list[Path] = []

    # Step pipeline: (function, kwargs_override)
    pipeline: list[tuple] = [
        (
            highpass_filter,
            {"cutoff_hz": float(params["highpass_hz"])},
        ),
        (
            remove_background_noise,
            {"noise_floor_db": float(params["noise_floor_db"])},
        ),
        (
            compress_audio,
            {
                "threshold_db": float(params["compress_threshold_db"]),
                "ratio": float(params["compress_ratio"]),
            },
        ),
    ]

    if include_de_ess:
        pipeline.append((de_ess, {}))

    pipeline.append(
        (
            normalize_audio,
            {"target_lufs": float(params["target_lufs"])},
        )
    )
    pipeline.append(
        (
            limit_peaks,
            {"limit_db": float(params["limit_db"])},
        )
    )

    current_input = input_path
    n_steps = len(pipeline)

    for i, (fn, kwargs) in enumerate(pipeline):
        is_last = i == n_steps - 1
        if is_last:
            current_output = output_path
        else:
            current_output = _tmp(i + 1)
            temp_files.append(current_output)

        result = fn(
            input_path=current_input,
            output_path=current_output,
            overwrite=True,
            dry_run=dry_run,
            **kwargs,
        )
        steps.append(result)

        if not result.success and not dry_run:
            # Clean up temp files on failure
            for tf in temp_files:
                if tf.exists():
                    tf.unlink(missing_ok=True)
            return {
                "success": False,
                "steps": [s.model_dump() for s in steps],
                "final_output": None,
                "preset_used": actual_preset,
                "error": f"Step {i + 1} ({getattr(fn, '__name__', str(fn))}) failed",
            }

        current_input = current_output

    # Clean up temp files on success
    if not dry_run:
        for tf in temp_files:
            if tf.exists():
                tf.unlink(missing_ok=True)

    return {
        "success": True,
        "steps": [s.model_dump() for s in steps],
        "final_output": str(output_path),
        "preset_used": actual_preset,
    }


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

_DEFAULT_AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".wav", ".mp3", ".flac", ".m4a", ".aac"}
)


def batch_process(
    input_dir: Path,
    output_dir: Path,
    preset: str = "youtube_voice",
    extensions: set[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Process all audio files in a directory.

    Args:
        input_dir: Directory containing source audio files.
        output_dir: Directory where processed files will be written.
        preset: Voice enhancement preset name.
        extensions: Set of file extensions to process (default: wav/mp3/flac/m4a/aac).
        dry_run: Return commands without executing.

    Returns:
        Dict with: processed (int), failed (int), results (dict mapping filename
        to chain result).
    """
    if extensions is None:
        extensions = set(_DEFAULT_AUDIO_EXTENSIONS)

    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    processed = 0
    failed = 0

    for source in sorted(input_dir.iterdir()):
        if not source.is_file():
            continue
        if source.suffix.lower() not in extensions:
            continue

        dest = output_dir / source.name
        chain_result = voice_enhance_chain(
            input_path=source,
            output_path=dest,
            preset=preset,
            dry_run=dry_run,
        )
        results[source.name] = chain_result

        if chain_result["success"]:
            processed += 1
        else:
            failed += 1

    return {
        "processed": processed,
        "failed": failed,
        "results": results,
    }
