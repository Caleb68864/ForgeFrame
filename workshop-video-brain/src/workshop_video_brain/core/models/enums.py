"""Shared enumerations for workshop-video-brain models."""
from __future__ import annotations

from enum import Enum


class ProjectStatus(str, Enum):
    idea = "idea"
    outlining = "outlining"
    scripting = "scripting"
    filming = "filming"
    ingesting = "ingesting"
    editing = "editing"
    review = "review"
    rendering = "rendering"
    published = "published"
    archived = "archived"


class MarkerCategory(str, Enum):
    intro_candidate = "intro_candidate"
    hook_candidate = "hook_candidate"
    materials_mention = "materials_mention"
    step_explanation = "step_explanation"
    measurement_detail = "measurement_detail"
    important_caution = "important_caution"
    mistake_problem = "mistake_problem"
    fix_recovery = "fix_recovery"
    broll_candidate = "broll_candidate"
    closeup_needed = "closeup_needed"
    dead_air = "dead_air"
    repetition = "repetition"
    ending_reveal = "ending_reveal"
    chapter_candidate = "chapter_candidate"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ShotType(str, Enum):
    a_roll = "a_roll"
    overhead = "overhead"
    closeup = "closeup"
    measurement = "measurement"
    insert = "insert"
    glamour = "glamour"
    pickup = "pickup"


class ProxyStatus(str, Enum):
    not_needed = "not_needed"
    pending = "pending"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class TranscriptStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class AnalysisStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ValidationSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"
    blocking_error = "blocking_error"
