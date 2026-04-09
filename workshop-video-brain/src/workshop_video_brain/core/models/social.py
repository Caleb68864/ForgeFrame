"""Social media clip models for short-form content extraction."""
from __future__ import annotations

from ._base import SerializableMixin


class ClipCandidate(SerializableMixin):
    """A candidate clip extracted from a longer video."""

    start_seconds: float
    end_seconds: float
    duration_seconds: float
    hook_text: str = ""           # opening line of the clip
    content_summary: str = ""     # what happens in this clip
    hook_strength: float = 0.0    # 0-1 score
    clarity: float = 0.0          # 0-1 score (standalone understandability)
    engagement: float = 0.0       # 0-1 score
    overall_score: float = 0.0    # weighted average
    source_step: str = ""         # which tutorial step this comes from


class ClipExport(SerializableMixin):
    """Export specification for a social media clip."""

    clip_id: str = ""
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    title: str = ""
    caption: str = ""             # overlay text
    description: str = ""         # social post text
    hashtags: list[str] = []
    aspect_ratio: str = "9:16"    # 9:16 for Shorts/Reels, 16:9 for YouTube
    source_video: str = ""


class SocialPost(SerializableMixin):
    """Social media post for a clip."""

    platform: str = "youtube"     # youtube, instagram, tiktok, twitter
    post_text: str = ""
    hashtags: list[str] = []
    clip_title: str = ""
