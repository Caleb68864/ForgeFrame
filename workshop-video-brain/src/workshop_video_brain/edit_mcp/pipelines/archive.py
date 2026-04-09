"""Project archive pipeline -- bundle workspace into tar.gz or zip."""
from __future__ import annotations

import re
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from workshop_video_brain.core.models.archive import ArchiveManifest

VALID_FORMATS = {"tar.gz", "zip"}

# Directories/patterns always included (relative to workspace root)
ALWAYS_INCLUDE = ["workspace.yaml", "*.kdenlive", "reports", "transcripts"]


def create_archive(
    workspace_root: Path,
    output_dir: Path,
    include_renders: bool = True,
    include_raw: bool = False,
    format: str = "tar.gz",
) -> ArchiveManifest:
    """Archive a workspace into a tar.gz or zip file."""
    if format not in VALID_FORMATS:
        raise ValueError(f"Invalid format '{format}'; must be one of {VALID_FORMATS}")

    # Read workspace title
    ws_yaml = yaml.safe_load((workspace_root / "workspace.yaml").read_text())
    title = ws_yaml.get("title", "untitled")
    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title)

    # Collect files
    files: list[Path] = []
    for pattern in ALWAYS_INCLUDE:
        if "*" in pattern:
            files.extend(workspace_root.glob(pattern))
        else:
            target = workspace_root / pattern
            if target.is_file():
                files.append(target)
            elif target.is_dir():
                files.extend(f for f in target.rglob("*") if f.is_file())

    if include_renders and (workspace_root / "renders").is_dir():
        files.extend(f for f in (workspace_root / "renders").rglob("*") if f.is_file())

    if include_raw and (workspace_root / "media" / "raw").is_dir():
        files.extend(f for f in (workspace_root / "media" / "raw").rglob("*") if f.is_file())

    # Deduplicate
    files = sorted(set(files))

    # Calculate total size
    total_size = sum(f.stat().st_size for f in files)

    # Build archive name
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ext = ".tar.gz" if format == "tar.gz" else ".zip"
    archive_name = f"{safe_title}_{date_str}{ext}"
    archive_path = output_dir / archive_name

    # Write archive (streaming)
    if format == "tar.gz":
        with tarfile.open(archive_path, "w:gz") as tar:
            for f in files:
                arcname = f.relative_to(workspace_root)
                tar.add(f, arcname=str(arcname))
    else:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                arcname = f.relative_to(workspace_root)
                zf.write(f, arcname=str(arcname))

    return ArchiveManifest(
        workspace_title=title,
        archive_path=str(archive_path),
        created_at=datetime.now(timezone.utc).isoformat(),
        files_included=len(files),
        total_size_bytes=total_size,
        includes_renders=include_renders,
        includes_raw_media=include_raw,
    )
