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
    audio_clipping: bool = False
    loudness_lufs: float | None = None
    true_peak_dbtp: float | None = None
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    checks_passed: list[str] = []
    checks_failed: list[str] = []
    checks_skipped: list[str] = []
    overall_pass: bool = True
