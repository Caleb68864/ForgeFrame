"""Color analysis models."""
from __future__ import annotations

from pydantic import BaseModel


class ColorAnalysis(BaseModel):
    """Result of analyze_color() -- color metadata and recommendations."""
    file_path: str
    color_space: str | None = None
    color_primaries: str | None = None
    color_transfer: str | None = None
    bit_depth: int | None = None
    is_hdr: bool = False
    recommendations: list[str] = []
