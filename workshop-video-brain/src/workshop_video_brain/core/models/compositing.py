"""Compositing models -- PiP presets and layout geometry."""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class PipPreset(str, Enum):
    top_left = "top_left"
    top_right = "top_right"
    bottom_left = "bottom_left"
    bottom_right = "bottom_right"
    center = "center"
    custom = "custom"


class PipLayout(BaseModel):
    x: int
    y: int
    width: int
    height: int
