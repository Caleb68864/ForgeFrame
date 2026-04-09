"""ForgeFrame initialization system.

Creates vault structure, media organization folders, Obsidian templates,
.env file, and ~/.forgeframe/config.json on first run.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "0.1.0"

VAULT_FOLDERS: list[str] = [
    "Ideas",
    "In Progress",
    "Published",
    "Archived",
    "B-Roll Library",
    "B-Roll Library/Shots",
    "B-Roll Library/Sound Effects",
    "B-Roll Library/Music",
    "Templates",
    "Templates/YouTube",
    "Research",
    "Research/MYOG",
    "Research/Gear",
    "Research/Techniques",
]

MEDIA_FOLDERS: list[str] = [
    "video/raw",
    "video/proxies",
    "video/processed",
    "video/exports",
    "audio/raw",
    "audio/processed",
    "audio/voiceover",
    "audio/music",
    "audio/sfx",
    "images/stills",
    "images/thumbnails",
    "images/overlays",
    "images/logos",
    "graphics/title-cards",
    "graphics/lower-thirds",
    "graphics/transitions",
    "documents/scripts",
    "documents/notes",
    "documents/releases",
]

_MEDIA_FOLDER_READMES: dict[str, str] = {
    "video": "Raw footage, proxies, processed clips, and final exports",
    "audio": "Voice recordings, processed audio, music, and sound effects",
    "images": "Screenshots, thumbnails, overlay graphics, and logos",
    "graphics": "Title cards, lower thirds, and transition graphics",
    "documents": "Scripts, production notes, and release forms",
}

# Obsidian template content keyed by relative path inside vault
_VAULT_TEMPLATES: dict[str, str] = {
    "Templates/YouTube/Video Idea.md": """\
---
title: "{{ title }}"
status: idea
content_type: tutorial
created: {{ date }}
tags: [video, idea]
---

## Viewer Promise
What will the viewer be able to do after watching?

## What We're Making

## Materials & Tools

## Why This Matters

## Open Questions
""",
    "Templates/YouTube/In Progress.md": """\
---
title: "{{ title }}"
status: in-progress
content_type: tutorial
workspace_path: ""
created: {{ date }}
tags: [video, in-progress]
---

## Viewer Promise

## Script Status
- [ ] Outline complete
- [ ] Script drafted
- [ ] Shot plan ready

## Shot Plan

## Filming Notes

## Pickup Shots Needed

## Edit Notes
""",
    "Templates/YouTube/Published.md": """\
---
title: "{{ title }}"
status: published
publish_date: {{ date }}
youtube_url: ""
tags: [video, published]
---

## Final Stats

## Chapter Timestamps

## Lessons Learned

## What Worked

## What to Improve Next Time
""",
    "Templates/YouTube/B-Roll Entry.md": """\
---
title: "{{ title }}"
type: broll
tags: [broll]
source_projects: []
---

## Clips
| File | Project | Time Range | Description | Tags |
|------|---------|------------|-------------|------|
|      |         |            |             |      |

## Usage Notes
""",
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ForgeFrameConfig(BaseModel):
    """Global ForgeFrame configuration."""

    vault_path: str
    projects_root: str
    media_library_root: str = ""
    ffmpeg_path: str = "ffmpeg"
    whisper_model: str = "small"
    default_preset: str = "youtube_voice"


class InitResult(BaseModel):
    """Result of initialization."""

    vault_path: str
    projects_root: str
    vault_folders_created: list[str]
    media_folders_created: list[str]
    config_file_written: str
    env_file_written: str
    notes: list[str] = []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _expand(p: Path | str) -> Path:
    return Path(p).expanduser().resolve()


def _create_folders(root: Path, folders: list[str]) -> list[str]:
    """Create subdirectories under *root*.  Returns list of folders that were
    actually created (did not already exist)."""
    created: list[str] = []
    for folder in folders:
        target = root / folder
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(folder)
        else:
            target.mkdir(parents=True, exist_ok=True)  # idempotent no-op
    return created


def _write_if_missing(path: Path, content: str) -> bool:
    """Write *content* to *path* only if *path* does not already exist.
    Returns True if the file was written."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def initialize_forgeframe(
    vault_path: Path | str,
    projects_root: Path | str,
    media_library_root: Path | str | None = None,
    ffmpeg_path: str = "ffmpeg",
    whisper_model: str = "small",
    *,
    repo_root: Path | str | None = None,
    config_dir: Path | str | None = None,
) -> InitResult:
    """Initialize ForgeFrame environment.

    Creates:
    1. Obsidian vault folder structure at vault_path
    2. .obsidian/ directory with basic config (if not exists)
    3. Obsidian template notes in Templates/YouTube/
    4. Media organization template at media_library_root (or projects_root/Media Library/)
    5. .env file at ForgeFrame repo root (defaults to package grandparent)
    6. forge-config.json at ~/.forgeframe/config.json

    Args:
        vault_path: Path to the Obsidian vault root (created if missing).
        projects_root: Root folder for all project workspaces.
        media_library_root: Optional separate media library path.
            Defaults to ``projects_root / "Media Library"``.
        ffmpeg_path: Path or command name for FFmpeg binary.
        whisper_model: Whisper model size to use (tiny/base/small/medium/large).
        repo_root: Path to the ForgeFrame repository root for .env placement.
            Defaults to the package's repository root.

    Returns:
        :class:`InitResult` describing everything that was created.
    """
    notes: list[str] = []

    # ------------------------------------------------------------------ #
    # Resolve paths
    # ------------------------------------------------------------------ #
    vault = _expand(vault_path)
    projects = _expand(projects_root)

    if media_library_root:
        media_lib = _expand(media_library_root)
    else:
        media_lib = projects / "Media Library"

    if repo_root is None:
        # Climb up from this file: .../app/init_system.py → repo root is 5
        # levels up (app -> workshop_video_brain -> src -> workshop-video-brain
        # -> ForgeFrame)
        repo_root = Path(__file__).parent.parent.parent.parent.parent.parent
    repo_root = Path(repo_root).resolve()

    # ------------------------------------------------------------------ #
    # Step 1: Vault structure
    # ------------------------------------------------------------------ #
    vault.mkdir(parents=True, exist_ok=True)
    vault_created = _create_folders(vault, VAULT_FOLDERS)

    # .obsidian/ with minimal app.json
    obsidian_dir = vault / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)
    app_json = obsidian_dir / "app.json"
    if not app_json.exists():
        app_json.write_text('{"livePreview": true}\n', encoding="utf-8")
        notes.append("Created .obsidian/app.json")

    # ------------------------------------------------------------------ #
    # Step 2: Vault template notes
    # ------------------------------------------------------------------ #
    templates_written: list[str] = []
    for rel_path, content in _VAULT_TEMPLATES.items():
        target = vault / rel_path
        written = _write_if_missing(target, content)
        if written:
            templates_written.append(rel_path)

    if templates_written:
        notes.append(f"Created {len(templates_written)} template note(s)")

    # ------------------------------------------------------------------ #
    # Step 3: Media library structure
    # ------------------------------------------------------------------ #
    media_lib.mkdir(parents=True, exist_ok=True)
    media_created = _create_folders(media_lib, MEDIA_FOLDERS)

    # README.md in each top-level media folder
    for top_folder, description in _MEDIA_FOLDER_READMES.items():
        readme = media_lib / top_folder / "README.md"
        _write_if_missing(readme, f"# {top_folder.title()}\n\n{description}\n")

    # ------------------------------------------------------------------ #
    # Step 4: Config files
    # ------------------------------------------------------------------ #

    # .env at repo root
    env_path = repo_root / ".env"
    env_content = (
        f"WVB_VAULT_PATH={vault}\n"
        f"WVB_WORKSPACE_ROOT={projects}\n"
        f"WVB_FFMPEG_PATH={ffmpeg_path}\n"
        f"WVB_WHISPER_MODEL={whisper_model}\n"
        f"WVB_MEDIA_LIBRARY={media_lib}\n"
        f"WVB_AUDIO_PRESET=youtube_voice\n"
    )
    env_existed = env_path.exists()
    env_path.write_text(env_content, encoding="utf-8")
    if env_existed:
        notes.append(f"Updated existing .env at {env_path}")

    # ~/.forgeframe/config.json (or custom config_dir for testing)
    if config_dir is None:
        config_dir = Path.home() / ".forgeframe"
    else:
        config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    config_data = {
        "vault_path": str(vault),
        "projects_root": str(projects),
        "media_library_root": str(media_lib),
        "ffmpeg_path": ffmpeg_path,
        "whisper_model": whisper_model,
        "default_audio_preset": "youtube_voice",
        "initialized": date.today().isoformat(),
        "version": VERSION,
    }
    config_path.write_text(
        json.dumps(config_data, indent=4) + "\n", encoding="utf-8"
    )

    # ------------------------------------------------------------------ #
    # Step 5: Return result
    # ------------------------------------------------------------------ #
    return InitResult(
        vault_path=str(vault),
        projects_root=str(projects),
        vault_folders_created=vault_created,
        media_folders_created=media_created,
        config_file_written=str(config_path),
        env_file_written=str(env_path),
        notes=notes,
    )


def check_status(config_dir: Path | str | None = None) -> dict:
    """Check ForgeFrame initialization status.

    Returns a structured status report covering config presence, path
    existence, and tool availability.
    """
    if config_dir is None:
        config_path = Path.home() / ".forgeframe" / "config.json"
    else:
        config_path = Path(config_dir) / "config.json"

    if not config_path.exists():
        return {
            "initialized": False,
            "config_path": str(config_path),
            "message": "ForgeFrame has not been initialized. Run `wvb init` to get started.",
        }

    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "initialized": False,
            "config_path": str(config_path),
            "message": f"Config file exists but could not be read: {exc}",
        }

    vault_path = cfg.get("vault_path", "")
    projects_root = cfg.get("projects_root", "")
    media_library_root = cfg.get("media_library_root", "")
    ffmpeg_path = cfg.get("ffmpeg_path", "ffmpeg")
    whisper_model = cfg.get("whisper_model", "small")

    vault_ok = bool(vault_path) and Path(vault_path).is_dir()
    projects_ok = bool(projects_root) and Path(projects_root).is_dir()
    media_ok = bool(media_library_root) and Path(media_library_root).is_dir()
    ffmpeg_ok = shutil.which(ffmpeg_path) is not None

    whisper_ok = False
    try:
        import faster_whisper  # noqa: F401
        whisper_ok = True
    except ImportError:
        pass

    # Check for expected vault folders
    missing_vault_folders: list[str] = []
    if vault_ok:
        vault = Path(vault_path)
        missing_vault_folders = [
            f for f in VAULT_FOLDERS if not (vault / f).is_dir()
        ]

    issues: list[str] = []
    if not vault_ok:
        issues.append(f"Vault path does not exist: {vault_path or '(not set)'}")
    elif missing_vault_folders:
        issues.append(
            f"Vault is missing {len(missing_vault_folders)} expected folder(s)"
        )
    if not projects_ok:
        issues.append(
            f"Projects root does not exist: {projects_root or '(not set)'}"
        )
    if not media_ok:
        issues.append(
            f"Media library path does not exist: {media_library_root or '(not set)'}"
        )
    if not ffmpeg_ok:
        issues.append(f"FFmpeg not found at '{ffmpeg_path}'")
    if not whisper_ok:
        issues.append("faster-whisper is not installed")

    return {
        "initialized": True,
        "config_path": str(config_path),
        "vault_path": vault_path,
        "projects_root": projects_root,
        "media_library_root": media_library_root,
        "ffmpeg_path": ffmpeg_path,
        "whisper_model": whisper_model,
        "initialized_date": cfg.get("initialized", "unknown"),
        "version": cfg.get("version", "unknown"),
        "checks": {
            "vault_exists": vault_ok,
            "projects_root_exists": projects_ok,
            "media_library_exists": media_ok,
            "ffmpeg_available": ffmpeg_ok,
            "whisper_available": whisper_ok,
            "vault_folders_complete": vault_ok and not missing_vault_folders,
        },
        "missing_vault_folders": missing_vault_folders,
        "issues": issues,
        "all_clear": len(issues) == 0,
    }
