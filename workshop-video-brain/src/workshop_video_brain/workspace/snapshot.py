"""Snapshot manager: copy-first safety layer for project files."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import yaml

from workshop_video_brain.core.models.project import SnapshotRecord
from workshop_video_brain.core.utils.naming import slugify, timestamp_prefix

_SNAPSHOTS_DIR = "projects/snapshots"
_METADATA_FILENAME = "metadata.yaml"

# Paths that must NEVER be overwritten
_PROTECTED_PREFIXES = ("media/raw", "projects/source")


def _assert_not_protected(workspace_root: Path, path: Path) -> None:
    """Raise ValueError if *path* falls under a protected directory."""
    try:
        rel = path.relative_to(workspace_root)
    except ValueError:
        return  # outside workspace – allow
    rel_str = str(rel).replace("\\", "/")
    for prefix in _PROTECTED_PREFIXES:
        if rel_str == prefix or rel_str.startswith(prefix + "/"):
            raise ValueError(
                f"Refusing to overwrite protected path: {path}"
            )


def create(
    workspace_root: Path | str,
    file_to_snapshot: Path | str,
    description: str = "",
) -> SnapshotRecord:
    """Copy *file_to_snapshot* into a new timestamped snapshot directory.

    Returns a SnapshotRecord describing the snapshot.
    The source file is NEVER a protected path (media/raw, projects/source).
    """
    workspace_root = Path(workspace_root)
    file_to_snapshot = Path(file_to_snapshot)

    ts = timestamp_prefix()
    slug = slugify(file_to_snapshot.stem) or "snapshot"
    base_snap_name = f"{ts}-{slug}"
    # Ensure unique directory even when called multiple times within one second
    snap_name = base_snap_name
    counter = 1
    while (workspace_root / _SNAPSHOTS_DIR / snap_name).exists():
        snap_name = f"{base_snap_name}-{counter}"
        counter += 1
    snap_dir = workspace_root / _SNAPSHOTS_DIR / snap_name
    snap_dir.mkdir(parents=True, exist_ok=True)

    # Capture manifest state
    manifest_snapshot: dict = {}
    manifest_path = workspace_root / "workspace.yaml"
    if manifest_path.exists():
        import yaml as _yaml
        manifest_snapshot = _yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    # Copy the project file
    dest = snap_dir / file_to_snapshot.name
    shutil.copy2(file_to_snapshot, dest)

    record = SnapshotRecord(
        workspace_id=uuid4(),  # placeholder; manager can fill workspace id
        timestamp=datetime.utcnow(),
        project_file_path=str(file_to_snapshot),
        manifest_snapshot=manifest_snapshot,
        description=description,
    )

    # Persist metadata
    meta_path = snap_dir / _METADATA_FILENAME
    meta_path.write_text(record.to_yaml(), encoding="utf-8")

    return record


def restore(workspace_root: Path | str, snapshot_id: str) -> None:
    """Restore a snapshot by its directory name (timestamp-slug).

    Copies the snapshot file back to its original location.
    Will NOT restore into media/raw or projects/source.
    """
    workspace_root = Path(workspace_root)
    snap_dir = workspace_root / _SNAPSHOTS_DIR / snapshot_id
    meta_path = snap_dir / _METADATA_FILENAME
    record = SnapshotRecord.from_yaml(meta_path.read_text(encoding="utf-8"))

    original = Path(record.project_file_path)
    _assert_not_protected(workspace_root, original)

    # Find the copied file in the snapshot dir (first non-metadata file)
    candidates = [f for f in snap_dir.iterdir() if f.name != _METADATA_FILENAME]
    if not candidates:
        raise FileNotFoundError(f"No snapshot file found in {snap_dir}")
    snap_file = candidates[0]

    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snap_file, original)


def list_snapshots(workspace_root: Path | str) -> list[SnapshotRecord]:
    """Return all snapshot records found in the workspace, sorted by timestamp."""
    workspace_root = Path(workspace_root)
    snaps_dir = workspace_root / _SNAPSHOTS_DIR
    if not snaps_dir.exists():
        return []

    records: list[SnapshotRecord] = []
    for meta_path in sorted(snaps_dir.rglob(_METADATA_FILENAME)):
        try:
            records.append(
                SnapshotRecord.from_yaml(meta_path.read_text(encoding="utf-8"))
            )
        except Exception:
            pass  # skip corrupt entries

    return sorted(records, key=lambda r: r.timestamp)
