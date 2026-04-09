"""Publishing models for YouTube publish-ready asset bundles."""
from __future__ import annotations

from ._base import SerializableMixin


class TitleVariants(SerializableMixin):
    """Four title style variants for A/B testing."""

    searchable: str = ""   # SEO-focused, includes key terms + category
    curiosity: str = ""    # Benefit/result framing
    how_to: str = ""       # "How to..." format
    short_punchy: str = "" # Under 40 chars, action-oriented


class VideoSummary(SerializableMixin):
    """Short, medium, and long summaries of the video."""

    short_summary: str = ""   # 1-2 sentences
    medium_summary: str = ""  # 3-5 sentences
    long_summary: str = ""    # Full paragraph


class PublishBundle(SerializableMixin):
    """Complete YouTube publish bundle with all generated assets."""

    title_variants: TitleVariants = TitleVariants()
    description: str = ""
    tags: list[str] = []
    hashtags: list[str] = []
    pinned_comment: str = ""
    chapters_text: str = ""
    summary: VideoSummary = VideoSummary()
    resources: list[dict] = []  # [{name, url_or_ref, context}]
