"""Resolve a project-version reference (latest / previous / snapshot id / path) to a file."""
from __future__ import annotations

from pathlib import Path


class VersionNotFound(LookupError):
    """The reference names no working copy, snapshot or project file in this workspace."""


def _working_copies(ws_path: Path) -> list[Path]:
    from workshop_video_brain.edit_mcp.server.tools_helpers._projects import _project_version_key

    folder = ws_path / "projects" / "working_copies"
    return sorted(folder.glob("*.kdenlive"), key=_project_version_key) if folder.is_dir() else []


def resolve_version(ws_path: Path, ref: str) -> Path:
    """``latest``, ``previous``, a snapshot id, or a .kdenlive path inside the workspace.

    Raises VersionNotFound for anything that does not resolve inside the
    workspace (snapshot ids are validated as ``snapshot.restore`` does).
    """
    ws_path = Path(ws_path).resolve()
    ref = (ref or "").strip()
    copies = _working_copies(ws_path)
    if ref == "latest":
        if not copies:
            raise VersionNotFound("There are no working copies in projects/working_copies/.")
        return copies[-1]
    if ref == "previous":
        if len(copies) < 2:
            raise VersionNotFound("There is no working copy before the latest one.")
        return copies[-2]

    snapshots_root = (ws_path / "projects" / "snapshots").resolve()
    if ref and Path(ref).name == ref and ref not in (".", "..") and (snapshots_root / ref).is_dir():
        snap_dir = (snapshots_root / ref).resolve()
        if snap_dir.parent != snapshots_root:
            raise VersionNotFound(f"Snapshot {ref!r} is outside projects/snapshots.")
        meta = snap_dir / "metadata.yaml"
        if meta.is_file():
            from workshop_video_brain.core.models.project import SnapshotRecord
            try:
                name = Path(SnapshotRecord.from_yaml(meta.read_text(encoding="utf-8")).project_file_path).name
            except Exception:  # noqa: BLE001 -- fall back to the only project file
                name = ""
            if name and (snap_dir / name).is_file():
                return snap_dir / name
        found = sorted(snap_dir.glob("*.kdenlive"))
        if len(found) == 1:
            return found[0]
        raise VersionNotFound(f"Snapshot {ref!r} holds {len(found)} project files; cannot tell which one.")

    if ref.endswith(".kdenlive"):
        path = Path(ref)
        path = (path if path.is_absolute() else ws_path / path).resolve()
        if not path.is_relative_to(ws_path):
            raise VersionNotFound(f"{ref!r} is outside the workspace.")
        if not path.is_file():
            raise FileNotFoundError(f"Project file does not exist: {path}")
        return path
    raise VersionNotFound(f"{ref!r} is not 'latest', 'previous', a snapshot id or a .kdenlive path.")
