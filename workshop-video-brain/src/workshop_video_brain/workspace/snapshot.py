"""Snapshot manager: copy-first safety layer for project files."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


from workshop_video_brain.core.models.project import SnapshotRecord
from workshop_video_brain.core.utils.naming import slugify, timestamp_prefix

logger = logging.getLogger(__name__)

_SNAPSHOTS_DIR = "projects/snapshots"
_METADATA_FILENAME = "metadata.yaml"


def _assert_not_protected(workspace_root: Path, path: Path) -> None:
    """Raise ValueError if *path* falls under a protected directory."""
    from workshop_video_brain.core.utils.paths import assert_not_protected
    assert_not_protected(path, "restored project")


def create(
    workspace_root: Path | str,
    file_to_snapshot: Path | str,
    description: str = "",
) -> SnapshotRecord:
    """Copy *file_to_snapshot* into a new timestamped snapshot directory.

    Returns a SnapshotRecord describing the snapshot.
    Reading a protected source is allowed; snapshots never replace that source.
    """
    workspace_root = Path(workspace_root).resolve()
    file_to_snapshot = Path(file_to_snapshot).resolve()

    from workshop_video_brain.workspace.safe_write import locked_path
    with locked_path(file_to_snapshot):
        return _create_locked(workspace_root, file_to_snapshot, description)


def _create_locked(workspace_root: Path, file_to_snapshot: Path, description: str) -> SnapshotRecord:
    from workshop_video_brain.core.utils.paths import assert_not_protected
    ts = timestamp_prefix()
    slug = slugify(file_to_snapshot.stem) or "snapshot"
    base_snap_name = f"{ts}-{slug}"
    counter = 0
    while True:
        snap_name = base_snap_name if counter == 0 else f"{base_snap_name}-{counter}"
        snap_dir = assert_not_protected(workspace_root / _SNAPSHOTS_DIR / snap_name)
        try:
            snap_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            counter += 1

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
        timestamp=datetime.now(tz=timezone.utc),
        project_file_path=str(file_to_snapshot),
        manifest_snapshot=manifest_snapshot,
        description=description,
        snapshot_id=snap_name,
    )

    # Persist metadata
    meta_path = snap_dir / _METADATA_FILENAME
    from workshop_video_brain.workspace.safe_write import atomic_write_text
    atomic_write_text(meta_path, record.to_yaml())

    return record


def restore(workspace_root: Path | str, snapshot_id: str) -> None:
    """Restore a snapshot by its directory name (timestamp-slug).

    Copies the snapshot file back to its original location.
    Will NOT restore into media/raw or projects/source.
    """
    workspace_root = Path(workspace_root).resolve()
    if Path(snapshot_id).name != snapshot_id or snapshot_id in ("", ".", ".."):
        raise ValueError("snapshot_id must name a snapshot directory")
    snapshots_root = (workspace_root / _SNAPSHOTS_DIR).resolve()
    snap_dir = (snapshots_root / snapshot_id).resolve()
    if snap_dir.parent != snapshots_root:
        raise ValueError("Snapshot directory must remain inside projects/snapshots")
    meta_path = snap_dir / _METADATA_FILENAME
    record = SnapshotRecord.from_yaml(meta_path.read_text(encoding="utf-8"))

    original = Path(record.project_file_path).resolve()
    _assert_not_protected(workspace_root, original)
    if not original.is_relative_to(workspace_root):
        raise ValueError("Snapshot destination must remain inside the workspace")

    # Find the copied file in the snapshot dir (first non-metadata file)
    snap_file = snap_dir / original.name
    if not snap_file.is_file() or not snap_file.resolve().is_relative_to(snap_dir):
        raise FileNotFoundError(f"No matching snapshot file found in {snap_dir}")

    from workshop_video_brain.workspace.safe_write import atomic_write_bytes
    atomic_write_bytes(original, snap_file.read_bytes(), workspace_root=workspace_root,
                       description=f"Before restoring snapshot {snapshot_id}")


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
        except Exception as exc:  # noqa: BLE001 -- best-effort: skip corrupt entries
            # Corrupt/unreadable snapshot metadata is skipped so one bad entry
            # cannot hide the rest, but it is logged (not silently dropped).
            logger.warning("Skipping unreadable snapshot metadata %s: %s", meta_path, exc)

    return sorted(records, key=lambda r: r.timestamp)
