"""B-Roll Library pipeline: cross-project clip index stored in the Obsidian vault."""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import date
from pathlib import Path

from workshop_video_brain.core.models.broll_library import BRollEntry, BRollLibrary
from workshop_video_brain.core.models.clips import ClipLabel

logger = logging.getLogger(__name__)

_INDEX_REL = "B-Roll Library/broll-index.json"
_SHOTS_REL = "B-Roll Library/Shots"
_INDEX_NOTE_REL = "B-Roll Library/Index.md"


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def _resolve_vault_path() -> Path | None:
    """Resolve vault path from env var or config."""
    vault = os.environ.get("WVB_VAULT_PATH")
    if vault:
        return Path(vault).expanduser()
    config_path = Path.home() / ".forgeframe" / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if "vault_path" in config:
                return Path(config["vault_path"]).expanduser()
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------


def load_library(vault_path: Path) -> BRollLibrary:
    """Load the B-roll library index from the vault.

    If the index file does not exist, returns an empty library.
    """
    index_path = Path(vault_path) / _INDEX_REL
    if not index_path.exists():
        return BRollLibrary()
    try:
        raw = index_path.read_text(encoding="utf-8")
        return BRollLibrary.from_json(raw)
    except Exception as exc:
        logger.warning("Failed to parse broll-index.json: %s — returning empty library", exc)
        return BRollLibrary()


def save_library(vault_path: Path, library: BRollLibrary) -> Path:
    """Save the B-roll library index to the vault.

    Returns the path of the written file.
    """
    index_path = Path(vault_path) / _INDEX_REL
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # Keep derived fields consistent
    library.total_clips = len(library.entries)
    library.last_updated = date.today().isoformat()
    library.projects_indexed = sorted(
        {e.source_project for e in library.entries if e.source_project}
    )

    index_path.write_text(library.to_json(), encoding="utf-8")
    return index_path


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def index_project(vault_path: Path, workspace_root: Path) -> dict:
    """Scan a project workspace and add its clips to the B-roll library.

    Reads clip labels from workspace/clips/, adds entries that don't
    already exist in the library (by source_path dedup).

    Returns:
        dict with keys: added, skipped, total
    """
    vault_path = Path(vault_path)
    workspace_root = Path(workspace_root)
    clips_dir = workspace_root / "clips"

    library = load_library(vault_path)

    # Build a set of known source_paths for fast dedup
    known_paths: set[str] = {e.source_path for e in library.entries}

    # Read project title from manifest if available
    project_title = workspace_root.name  # fallback
    manifest_path = workspace_root / "workspace.yaml"
    if manifest_path.exists():
        try:
            from workshop_video_brain.workspace.manifest import read_manifest
            manifest = read_manifest(workspace_root)
            project_title = manifest.project_title
        except Exception as exc:
            logger.warning("Could not read workspace manifest: %s", exc)

    added = 0
    skipped = 0

    if clips_dir.exists():
        for label_path in sorted(clips_dir.glob("*_label.json")):
            try:
                raw = label_path.read_text(encoding="utf-8")
                label = ClipLabel.from_json(raw)
            except Exception as exc:
                logger.warning("Skipping malformed label file %s: %s", label_path, exc)
                skipped += 1
                continue

            # Use source_path from the label if set; otherwise derive from workspace
            source_path = label.source_path or ""

            # Try to resolve a media file path if source_path is a transcript path
            if source_path and "_transcript" in source_path:
                # source_path points to the transcript; derive media path
                source_path = _derive_media_path(workspace_root, label.clip_ref, source_path)

            if not source_path:
                # If still empty, use workspace/clip_ref as a key
                source_path = str(workspace_root / label.clip_ref)

            if source_path in known_paths:
                skipped += 1
                continue

            entry = BRollEntry(
                clip_ref=label.clip_ref,
                source_project=project_title,
                source_workspace=str(workspace_root),
                source_path=source_path,
                content_type=label.content_type,
                shot_type=label.shot_type,
                topics=list(label.topics),
                tags=list(label.tags),
                description=label.summary,
                duration_seconds=label.duration,
                added_date=date.today().isoformat(),
            )
            library.entries.append(entry)
            known_paths.add(source_path)
            added += 1

    save_library(vault_path, library)
    generate_library_notes(vault_path, library)

    return {"added": added, "skipped": skipped, "total": len(library.entries)}


def _derive_media_path(workspace_root: Path, clip_ref: str, transcript_path: str) -> str:
    """Try to find the actual media file for a clip given its workspace and clip_ref."""
    # Common locations relative to workspace
    media_dirs = [
        workspace_root / "media" / "raw",
        workspace_root / "media" / "proxies",
        workspace_root,
    ]
    extensions = [".mp4", ".mov", ".mkv", ".avi", ".MP4", ".MOV", ".MKV"]
    for media_dir in media_dirs:
        if not media_dir.exists():
            continue
        for ext in extensions:
            candidate = media_dir / f"{clip_ref}{ext}"
            if candidate.exists():
                return str(candidate)
    # Fall back to the transcript path itself
    return transcript_path


def index_all_projects(vault_path: Path, projects_root: Path) -> dict:
    """Scan all project workspaces under projects_root and rebuild the B-roll library.

    Finds all workspace.yaml files under projects_root, indexes each.

    Returns:
        dict with keys: projects_scanned, total_added, total_clips
    """
    vault_path = Path(vault_path)
    projects_root = Path(projects_root)

    projects_scanned = 0
    total_added = 0

    for manifest_file in sorted(projects_root.rglob("workspace.yaml")):
        workspace_root = manifest_file.parent
        try:
            result = index_project(vault_path, workspace_root)
            projects_scanned += 1
            total_added += result["added"]
            logger.info(
                "Indexed workspace %s: +%d clips", workspace_root.name, result["added"]
            )
        except Exception as exc:
            logger.warning("Failed to index workspace %s: %s", workspace_root, exc)

    library = load_library(vault_path)
    return {
        "projects_scanned": projects_scanned,
        "total_added": total_added,
        "total_clips": len(library.entries),
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_library(
    vault_path: Path,
    query: str,
    filters: dict | None = None,
) -> list[BRollEntry]:
    """Search the B-roll library across all projects.

    Scoring:
    - Exact tag match: 1.0
    - Topic match (word in topic): 0.8
    - Description match (word in description): 0.5

    Args:
        vault_path: Path to Obsidian vault root.
        query: Text to match against tags, topics, description.
        filters: Optional dict with keys:
            - content_type: str
            - shot_type: str
            - project: str (limit to specific project)
            - min_rating: int
            - min_duration: float
            - max_duration: float

    Returns:
        Ranked list of matching BRollEntry objects.
    """
    library = load_library(Path(vault_path))
    filters = filters or {}

    query_words = [w.lower() for w in query.split() if w.strip()]
    if not query_words:
        entries = list(library.entries)
        _apply_filters(entries, filters)
        return entries

    scored: list[tuple[float, BRollEntry]] = []

    for entry in library.entries:
        score = _score_entry(entry, query_words)
        if score > 0:
            scored.append((score, entry))

    # Apply filters
    filtered = [
        (score, entry) for score, entry in scored
        if _entry_matches_filters(entry, filters)
    ]

    # Sort by score desc, then rating desc
    filtered.sort(key=lambda t: (t[0], t[1].rating), reverse=True)
    return [entry for _, entry in filtered]


def _score_entry(entry: BRollEntry, query_words: list[str]) -> float:
    """Score a BRollEntry against normalized query words."""
    total = 0.0
    tags_lower = {t.lower() for t in entry.tags}
    topics_lower = [t.lower() for t in entry.topics]
    description_lower = entry.description.lower()

    for word in query_words:
        word = word.lower()
        if word in tags_lower:
            total += 1.0
        for topic in topics_lower:
            if word in topic:
                total += 0.8
                break
        if word in description_lower:
            total += 0.5

    return round(total, 4)


def _entry_matches_filters(entry: BRollEntry, filters: dict) -> bool:
    """Return True if the entry passes all specified filters."""
    if "content_type" in filters and filters["content_type"]:
        if entry.content_type != filters["content_type"]:
            return False
    if "shot_type" in filters and filters["shot_type"]:
        if entry.shot_type != filters["shot_type"]:
            return False
    if "project" in filters and filters["project"]:
        if filters["project"].lower() not in entry.source_project.lower():
            return False
    if "min_rating" in filters and filters["min_rating"]:
        if entry.rating < filters["min_rating"]:
            return False
    if "min_duration" in filters and filters["min_duration"]:
        if entry.duration_seconds < filters["min_duration"]:
            return False
    if "max_duration" in filters and filters["max_duration"]:
        if entry.duration_seconds > filters["max_duration"]:
            return False
    return True


def _apply_filters(entries: list[BRollEntry], filters: dict) -> None:
    """In-place filter a list of entries (for unscored search)."""
    to_remove = [e for e in entries if not _entry_matches_filters(e, filters)]
    for e in to_remove:
        entries.remove(e)


# ---------------------------------------------------------------------------
# Tag / Update
# ---------------------------------------------------------------------------


def tag_clip(
    vault_path: Path,
    source_path: str,
    tags: list[str] | None = None,
    rating: int = -1,
    description: str = "",
    in_seconds: float = -1,
    out_seconds: float = -1,
) -> BRollEntry:
    """Add or update tags/rating/trim on a B-roll library entry.

    If the clip is not in the library, a minimal entry is added.
    Only non-default values update the existing fields.
    Tags are merged (not replaced).
    """
    library = load_library(Path(vault_path))

    # Find existing entry
    entry: BRollEntry | None = None
    for e in library.entries:
        if e.source_path == source_path:
            entry = e
            break

    if entry is None:
        # Create minimal new entry
        entry = BRollEntry(
            clip_ref=Path(source_path).name,
            source_path=source_path,
            added_date=date.today().isoformat(),
        )
        library.entries.append(entry)

    # Merge tags (not replace)
    if tags:
        existing = set(entry.tags)
        existing.update(t.lower() for t in tags)
        entry.tags = sorted(existing)

    if rating >= 0:
        entry.rating = rating

    if description:
        entry.description = description

    if in_seconds >= 0:
        entry.in_seconds = in_seconds

    if out_seconds >= 0:
        entry.out_seconds = out_seconds

    save_library(Path(vault_path), library)
    generate_library_notes(Path(vault_path), library)
    return entry


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


def remove_clip(vault_path: Path, source_path: str) -> bool:
    """Remove a clip from the B-roll library.

    Returns True if the clip was found and removed, False if not found.
    """
    library = load_library(Path(vault_path))
    original_count = len(library.entries)
    library.entries = [e for e in library.entries if e.source_path != source_path]

    if len(library.entries) == original_count:
        return False

    save_library(Path(vault_path), library)
    generate_library_notes(Path(vault_path), library)
    return True


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def get_library_stats(vault_path: Path) -> dict:
    """Get statistics about the B-roll library.

    Returns:
        dict with: total_clips, projects_indexed, top_tags, content_type_breakdown
    """
    library = load_library(Path(vault_path))

    tag_counter: Counter[str] = Counter()
    content_counter: Counter[str] = Counter()

    for entry in library.entries:
        for tag in entry.tags:
            tag_counter[tag] += 1
        if entry.content_type:
            content_counter[entry.content_type] += 1

    return {
        "total_clips": len(library.entries),
        "projects_indexed": list(library.projects_indexed),
        "top_tags": dict(tag_counter.most_common(20)),
        "content_type_breakdown": dict(content_counter),
    }


# ---------------------------------------------------------------------------
# Obsidian note generation
# ---------------------------------------------------------------------------


def generate_library_notes(vault_path: Path, library: BRollLibrary) -> list[Path]:
    """Generate Obsidian notes for the B-roll library.

    Creates/updates notes in B-Roll Library/Shots/ grouped by primary tag.
    Each note has a table of clips with filename, project, duration, tags, path.

    Also generates a master index note at B-Roll Library/Index.md.

    Returns:
        List of paths of created/updated notes.
    """
    vault_path = Path(vault_path)
    shots_dir = vault_path / _SHOTS_REL
    shots_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    written: list[Path] = []

    # Group entries by primary tag
    tag_groups: dict[str, list[BRollEntry]] = {}
    for entry in library.entries:
        primary = _primary_tag(entry)
        tag_groups.setdefault(primary, []).append(entry)

    # Generate per-tag notes
    for tag, entries in sorted(tag_groups.items()):
        note_path = shots_dir / f"{tag}.md"
        content = _render_tag_note(tag, entries, today)
        note_path.write_text(content, encoding="utf-8")
        written.append(note_path)

    # Generate master index
    index_note_path = vault_path / _INDEX_NOTE_REL
    index_content = _render_index_note(library, tag_groups, today)
    index_note_path.write_text(index_content, encoding="utf-8")
    written.append(index_note_path)

    return written


def _primary_tag(entry: BRollEntry) -> str:
    """Return the primary (most meaningful) tag for grouping."""
    # Skip content_type and shot_type values as primary — prefer topic-like tags
    skip = {
        entry.content_type.lower(),
        entry.shot_type.lower(),
        "unlabeled",
        "b_roll",
        "medium",
        "closeup",
        "overhead",
        "tutorial_step",
        "talking_head",
        "materials_overview",
    }
    for tag in entry.tags:
        if tag.lower() not in skip:
            return tag.lower()
    # Fallback to content_type
    return entry.content_type.lower() or "uncategorized"


def _render_tag_note(tag: str, entries: list[BRollEntry], today: str) -> str:
    """Render a per-tag Obsidian note."""
    header = (
        f"---\n"
        f"type: broll-collection\n"
        f"tag: {tag}\n"
        f"clip_count: {len(entries)}\n"
        f"last_updated: {today}\n"
        f"---\n\n"
        f"# B-Roll: {tag.replace('_', ' ').title()}\n\n"
        f"| Clip | Project | Duration | Shot Type | Tags | Path |\n"
        f"|------|---------|----------|-----------|------|------|\n"
    )
    rows = []
    for e in entries:
        duration = f"{e.duration_seconds:.1f}s" if e.duration_seconds else "-"
        tags_str = ", ".join(e.tags[:5])
        rows.append(
            f"| {e.clip_ref} | [[{e.source_project}]] | {duration} "
            f"| {e.shot_type} | {tags_str} | {e.source_path} |"
        )
    return header + "\n".join(rows) + "\n"


def _render_index_note(
    library: BRollLibrary,
    tag_groups: dict[str, list[BRollEntry]],
    today: str,
) -> str:
    """Render the master B-Roll Library Index note."""
    total_clips = len(library.entries)
    project_count = len(library.projects_indexed)

    frontmatter = (
        f"---\n"
        f"type: broll-index\n"
        f"total_clips: {total_clips}\n"
        f"projects: {project_count}\n"
        f"last_updated: {today}\n"
        f"---\n\n"
        f"# B-Roll Library Index\n\n"
    )

    # By Category section
    tag_section = "## By Category\n\n| Tag | Clips | Projects |\n|-----|-------|----------|\n"
    for tag in sorted(tag_groups):
        entries = tag_groups[tag]
        projects = {e.source_project for e in entries}
        tag_section += f"| [[{tag}]] | {len(entries)} | {len(projects)} |\n"

    # By Project section
    project_clips: Counter[str] = Counter()
    for entry in library.entries:
        project_clips[entry.source_project] += 1

    project_section = "\n## By Project\n\n| Project | Clips Added |\n|---------|-------------|\n"
    for proj, count in sorted(project_clips.items(), key=lambda x: x[1], reverse=True):
        project_section += f"| [[{proj}]] | {count} |\n"

    return frontmatter + tag_section + project_section
