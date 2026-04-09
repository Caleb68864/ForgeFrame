"""B-Roll Library models for cross-project clip indexing."""
from __future__ import annotations

from ._base import SerializableMixin


class BRollEntry(SerializableMixin):
    """A single reusable B-roll clip entry in the library."""

    clip_ref: str = ""                  # filename
    source_project: str = ""            # project title/slug
    source_workspace: str = ""          # absolute path to workspace
    source_path: str = ""               # absolute path to media file
    content_type: str = ""              # from clip label
    shot_type: str = ""                 # from clip label
    topics: list[str] = []             # from clip label
    tags: list[str] = []               # from clip label + user tags
    description: str = ""              # from clip label summary or user-provided
    duration_seconds: float = 0.0
    in_seconds: float = 0.0            # useful portion start
    out_seconds: float = -1.0          # useful portion end (-1 = full clip)
    times_used: int = 0                # how many projects have used this
    added_date: str = ""
    rating: int = 0                    # 0-5 user rating


class BRollLibrary(SerializableMixin):
    """The full cross-project B-roll index."""

    entries: list[BRollEntry] = []
    last_updated: str = ""
    total_clips: int = 0
    projects_indexed: list[str] = []
