"""Visual research / media-intelligence domain models.

These models describe the frame-candidate research pipeline: a
``ResearchQuery`` scopes a search over a source asset (optionally within a
``ResearchRegion``); candidate frames are extracted into ``FrameCandidate``
records carrying ``FrameVisualMetrics``; a ``ResearchCapture`` groups the
candidates produced by one extraction run; a ``ResearchManifest`` is the
persisted top-level record tying a source ``MediaAsset`` to its regions and
captures; ``FrameEvaluation`` records a downstream pass/fail judgement of a
single candidate; ``SceneChange`` is a raw scene-detection hit.

Extraction/config precedence (enforced by callers, not by these models):
explicit function/CLI arguments > ``WVB_*`` environment variables >
``ResearchConfig`` defaults.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from ._base import SerializableMixin
from .media import MediaAsset

ExtractionMethod = Literal[
    "exact_timestamp",
    "uniform_burst",
    "scene_change",
    "adaptive",
    "manual",
]


class ResearchQuery(SerializableMixin):
    """A request to search a source asset for representative frames."""

    model_config = {"use_enum_values": True}

    query_id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    text: str = ""
    tags: list[str] = Field(default_factory=list)
    start_seconds: float | None = None
    end_seconds: float | None = None
    max_candidates: int = 20
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class ResearchRegion(SerializableMixin):
    """A time-bounded region of a source asset scoped for research."""

    model_config = {"use_enum_values": True}

    region_id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    start_seconds: float
    end_seconds: float
    label: str = ""
    tags: list[str] = Field(default_factory=list)


class FrameVisualMetrics(SerializableMixin):
    """Optional visual-quality/content metrics computed for one frame."""

    model_config = {"use_enum_values": True}

    sharpness: float | None = None
    brightness: float | None = None
    contrast: float | None = None
    entropy: float | None = None
    motion_score: float | None = None
    face_count: int | None = None
    ocr_text: str | None = None
    ocr_confidence: float | None = None
    dedup_hash: str | None = None
    is_duplicate: bool | None = None
    scene_score: float | None = None


class FrameCandidate(SerializableMixin):
    """A single extracted candidate frame."""

    model_config = {"use_enum_values": True}

    candidate_id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    region_id: UUID | None = None
    timestamp_seconds: float
    image_path: str
    width: int = 0
    height: int = 0
    extraction_method: ExtractionMethod = "exact_timestamp"
    metrics: FrameVisualMetrics = Field(default_factory=FrameVisualMetrics)
    metadata: dict = Field(default_factory=dict)


class ResearchCapture(SerializableMixin):
    """A group of candidates produced by one extraction run."""

    model_config = {"use_enum_values": True}

    capture_id: UUID = Field(default_factory=uuid4)
    region_id: UUID | None = None
    source_id: UUID
    candidates: list[FrameCandidate] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class FrameEvaluation(SerializableMixin):
    """A downstream pass/fail judgement of a single candidate."""

    model_config = {"use_enum_values": True}

    candidate_id: UUID
    score: float = 0.0
    passed: bool = False
    notes: str = ""
    metrics: FrameVisualMetrics = Field(default_factory=FrameVisualMetrics)


class SceneChange(SerializableMixin):
    """A raw scene-change detection hit."""

    model_config = {"use_enum_values": True}

    timestamp_seconds: float
    score: float


class ResearchManifest(SerializableMixin):
    """Top-level persisted record for a visual-research run over one asset."""

    model_config = {"use_enum_values": True}

    manifest_id: UUID = Field(default_factory=uuid4)
    source: MediaAsset
    regions: list[ResearchRegion] = Field(default_factory=list)
    captures: list[ResearchCapture] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class _WindowingConfig(SerializableMixin):
    window_seconds: float = 10.0
    stride_seconds: float = 5.0


class _CandidateGenerationConfig(SerializableMixin):
    max_candidates_per_region: int = 20
    burst_count: int = 3
    burst_spacing_seconds: float = 0.5


class _SceneDetectionConfig(SerializableMixin):
    threshold: float = 0.3
    min_scene_length_seconds: float = 1.0


class _QualityConfig(SerializableMixin):
    min_sharpness: float = 0.0
    min_brightness: float = 0.0
    max_brightness: float = 1.0


class _DeduplicationConfig(SerializableMixin):
    enabled: bool = True
    hash_size: int = 8
    max_hamming_distance: int = 5


class _OcrConfig(SerializableMixin):
    enabled: bool = False
    language: str = "eng"
    min_confidence: float = 0.5


class _VisionConfig(SerializableMixin):
    enabled: bool = False
    face_detection: bool = False


class _ExportConfig(SerializableMixin):
    image_format: str = "jpg"
    jpeg_quality: int = 90
    output_dir: str = "research_frames"


class ResearchConfig(SerializableMixin):
    """Nested-group configuration for the visual-research pipeline.

    Precedence (enforced by callers): explicit args/CLI > ``WVB_*`` env
    vars > these defaults.
    """

    model_config = {"use_enum_values": True}

    windowing: _WindowingConfig = Field(default_factory=_WindowingConfig)
    candidate_generation: _CandidateGenerationConfig = Field(
        default_factory=_CandidateGenerationConfig
    )
    scene_detection: _SceneDetectionConfig = Field(default_factory=_SceneDetectionConfig)
    quality: _QualityConfig = Field(default_factory=_QualityConfig)
    deduplication: _DeduplicationConfig = Field(default_factory=_DeduplicationConfig)
    ocr: _OcrConfig = Field(default_factory=_OcrConfig)
    vision: _VisionConfig = Field(default_factory=_VisionConfig)
    export: _ExportConfig = Field(default_factory=_ExportConfig)
