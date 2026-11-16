"""Quality-check report models."""
from __future__ import annotations

from pydantic import BaseModel


class TimeRange(BaseModel):
    """A contiguous time span in seconds."""
    start_seconds: float
    end_seconds: float


class QCReport(BaseModel):
    """Structured result of run_qc()."""
    file_path: str
    black_frames: list[TimeRange] = []
    silence_regions: list[TimeRange] = []
    silence_total_seconds: float = 0.0
    silence_longest_seconds: float = 0.0
    audio_clipping: bool = False
    audio_peak_db: float | None = None
    audio_flat_factor: float | None = None
    loudness_lufs: float | None = None
    true_peak_dbtp: float | None = None
    loudness_target_lufs: float | None = None
    loudness_tolerance_lu: float | None = None
    # measured - target; negative is quieter than the target
    loudness_delta_lu: float | None = None
    # profile check: what the render was expected to be and what it is
    profile_expected: dict | None = None
    profile_actual: dict | None = None
    profile_mismatches: list[str] = []
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    checks_passed: list[str] = []
    checks_failed: list[str] = []
    checks_skipped: list[str] = []
    # check name -> why it was skipped (ffmpeg missing/failed, no stream, ...)
    check_errors: dict[str, str] = {}
    # check name -> why it failed (or what it found), in words
    check_notes: dict[str, str] = {}
    overall_pass: bool = True
