"""Assembly models for Script-to-Timeline Assembler."""
from __future__ import annotations

from pydantic import Field

from ._base import SerializableMixin


class ClipAssignment(SerializableMixin):
    """A clip assigned to a script step."""

    clip_ref: str = ""              # filename
    source_path: str = ""           # full path
    role: str = "primary"           # "primary", "insert", "broll"
    score: float = 0.0              # match confidence 0-1
    in_seconds: float = 0.0         # trim in
    out_seconds: float = -1.0       # trim out (-1 = full clip)
    reason: str = ""                # why this clip was matched


class StepAssembly(SerializableMixin):
    """Clips assembled for one script step."""

    step_number: int = 0
    step_description: str = ""
    clips: list[ClipAssignment] = Field(default_factory=list)
    chapter_title: str = ""


class AssemblyPlan(SerializableMixin):
    """Complete assembly plan: script steps matched to clips."""

    project_title: str = ""
    steps: list[StepAssembly] = Field(default_factory=list)
    unmatched_clips: list[str] = Field(default_factory=list)  # clips that didn't match any step
    total_estimated_duration: float = 0.0
    assembly_report: str = ""
