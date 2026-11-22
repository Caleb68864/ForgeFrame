"""Workspace undo/redo journal for project writes.

Every ``.kdenlive`` write that ``serialize_project`` (or ``snapshot.restore``)
makes inside a workspace is recorded in ``projects/undo/journal.json``. Writes
made inside one tool call share a *group* (``tool_guard`` opens one per call),
and undo/redo move whole groups.

Two kinds of entry:

* ``overwrite`` -- the file existed. ``atomic_write_bytes`` snapshotted it
  first, and the snapshot id is the way back.
* ``create`` -- the file is new (a ``_vN`` working copy). Undo moves it to
  ``projects/undo/trash/`` (never deletes it), so "latest" falls back to the
  previous version; redo moves it back.

Safety rule: an entry is only undone when the file on disk still has the
sha256 the journal recorded after the edit (``after_sha256``). Anything else
means the file changed outside ForgeFrame -- typically saved in Kdenlive --
and undoing would throw that work away, so it raises :class:`UndoConflict`
and touches nothing.

Lock order, everywhere: ``working_copies`` directory lock -> journal lock ->
target lock. :func:`edit_lock` takes the first two; ``serialize_versioned``
already holds the first when ``serialize_project`` takes the second.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Iterator
from uuid import uuid4

JOURNAL_REL = Path("projects") / "undo" / "journal.json"
TRASH_REL = Path("projects") / "undo" / "trash"
SNAPSHOTS_REL = Path("projects") / "snapshots"
MAX_GROUPS = 50

current_group: ContextVar[str | None] = ContextVar("wvb_undo_group", default=None)
current_label: ContextVar[str] = ContextVar("wvb_undo_label", default="")


class UndoConflict(RuntimeError):
    """A file changed since the journaled edit; undo/redo would lose that work."""


class NothingToUndo(ValueError):
    """The undo (or redo) stack is empty."""


class UndoBlocked(RuntimeError):
    """A detached job is active in the workspace."""


# ---------------------------------------------------------------------------
# Grouping and locks
# ---------------------------------------------------------------------------

@contextmanager
def edit_group(label: str) -> Iterator[str]:
    """Open an edit group unless one is already open (nested calls inherit it)."""
    existing = current_group.get()
    if existing is not None:
        yield existing
        return
    group_token = current_group.set(uuid4().hex)
    label_token = current_label.set(label)
    try:
        yield current_group.get()  # type: ignore[misc]
    finally:
        current_group.reset(group_token)
        current_label.reset(label_token)


def is_workspace(root: Path | str) -> bool:
    return (Path(root) / "workspace.yaml").exists()


def journal_path(root: Path | str) -> Path:
    return Path(root).resolve() / JOURNAL_REL


@contextmanager
def journal_lock(root: Path | str) -> Iterator[None]:
    from workshop_video_brain.workspace.safe_write import locked_path
    with locked_path(journal_path(root)):
        yield


@contextmanager
def edit_lock(root: Path | str) -> Iterator[None]:
    """``working_copies`` lock, then the journal lock (the documented order)."""
    from workshop_video_brain.workspace.safe_write import locked_path
    root = Path(root).resolve()
    with locked_path(root / "projects" / "working_copies"):
        with journal_lock(root):
            yield


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _empty() -> dict:
    return {"version": 1, "undo": [], "redo": []}


def _load(root: Path) -> dict:
    path = journal_path(root)
    if not path.exists():
        return _empty()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError(f"Unrecognised undo journal format: {path}")
    data.setdefault("undo", [])
    data.setdefault("redo", [])
    return data


def _save(root: Path, data: dict) -> None:
    from workshop_video_brain.workspace.safe_write import atomic_write_text
    atomic_write_text(journal_path(root), json.dumps(data, indent=2) + "\n")


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _file_sha(path: Path) -> str | None:
    return _sha(path.read_bytes()) if path.exists() else None


def _groups(entries: list[dict]) -> list[str]:
    """Distinct group ids, in order of first appearance."""
    seen: dict[str, None] = {}
    for entry in entries:
        seen.setdefault(entry["group"], None)
    return list(seen)


def _cap(entries: list[dict]) -> list[dict]:
    keep = set(_groups(entries)[-MAX_GROUPS:])
    return [e for e in entries if e["group"] in keep]


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_write(
    root: Path | str,
    path: Path | str,
    kind: str,
    before_snapshot_id: str | None,
    after_bytes: bytes,
    *,
    label: str | None = None,
) -> dict:
    """Append one write to the undo stack and clear redo."""
    if kind not in ("overwrite", "create"):
        raise ValueError(f"kind must be 'overwrite' or 'create', got {kind!r}")
    if kind == "overwrite" and not before_snapshot_id:
        raise ValueError("an overwrite entry needs its before_snapshot_id")
    root = Path(root).resolve()
    rel = Path(path).resolve().relative_to(root)
    entry = {
        "id": uuid4().hex,
        "group": current_group.get() or uuid4().hex,
        "label": label or current_label.get() or "write",
        "path": rel.as_posix(),
        "kind": kind,
        "before_snapshot_id": before_snapshot_id if kind == "overwrite" else None,
        "after_sha256": _sha(after_bytes),
        "created_at": _now(),
    }
    with journal_lock(root):
        data = _load(root)
        data["undo"] = _cap([*data["undo"], entry])
        data["redo"] = []
        _save(root, data)
    return entry


@contextmanager
def journaled_write(root: Path | str, target: Path | str, *, label: str | None = None):
    """Hold the journal lock around a write and record it as one step.

    Yields ``on_snapshot`` for ``atomic_write_bytes`` and a ``commit(data)``
    callable to call after the write succeeded.
    """
    root = Path(root).resolve()
    target = Path(target).resolve()
    with journal_lock(root):
        existed = target.exists()
        captured: list = []

        def commit(data: bytes) -> None:
            snapshot_id = captured[-1].snapshot_id if captured else None
            if existed and snapshot_id is None:
                return  # nothing to go back to: not undoable, so not journaled
            record_write(root, target, "overwrite" if existed else "create",
                         snapshot_id, data, label=label)

        yield captured.append, commit


# ---------------------------------------------------------------------------
# Undo / redo
# ---------------------------------------------------------------------------

def _active_job(root: Path) -> dict | None:
    from workshop_video_brain.workspace import jobs
    for record in jobs.list_jobs(root, reconcile=False):
        # A record left "running" by a crashed worker must not block undo for
        # ever, so liveness is checked here (list_jobs does not reconcile).
        if record.get("status") in jobs.ACTIVE and jobs._worker_alive(record):
            return record
    return None


def _check_jobs(root: Path) -> None:
    job = _active_job(root)
    if job is not None:
        raise UndoBlocked(
            f"Job {job.get('id', '?')} ({job.get('operation', '?')}) is "
            f"{job.get('status')} in this workspace. It pinned the project "
            "file's sha256 when it was submitted, so changing the file now "
            "would make it fail or render the wrong edit. Wait for it "
            "(job_status) or cancel it (job_cancel), then retry."
        )


def _snapshot_bytes(root: Path, snapshot_id: str, filename: str) -> bytes:
    snap = root / SNAPSHOTS_REL / snapshot_id / filename
    if not snap.is_file():
        raise UndoConflict(
            f"The snapshot {snapshot_id} that holds the earlier {filename} is "
            "missing, so this step cannot be undone or redone."
        )
    return snap.read_bytes()


def _conflict(rel: str) -> UndoConflict:
    return UndoConflict(
        f"{rel} changed outside ForgeFrame (e.g. saved in Kdenlive) since that "
        "edit, so undoing it would throw that change away. Use snapshot_list / "
        "snapshot_restore instead."
    )


def _pop_group(entries: list[dict]) -> tuple[str, list[dict], list[dict]]:
    group = entries[-1]["group"]
    members = [e for e in entries if e["group"] == group]
    rest = [e for e in entries if e["group"] != group]
    return group, members, rest


def _summary(group: str, members: list[dict]) -> dict:
    return {
        "group": group,
        "label": members[0]["label"],
        "files": list(dict.fromkeys(e["path"] for e in members)),
    }


def _undo_one(root: Path, data: dict) -> dict:
    from workshop_video_brain.workspace.safe_write import atomic_write_bytes

    group, members, rest = _pop_group(data["undo"])
    # Preflight every entry, newest first, simulating the file contents so a
    # group that wrote the same file twice checks each step against the state
    # the previous step would leave.
    sim: dict[str, str | None] = {}
    restore: dict[str, bytes] = {}
    for entry in reversed(members):
        rel = entry["path"]
        current = sim[rel] if rel in sim else _file_sha(root / rel)
        if current != entry["after_sha256"]:
            raise _conflict(rel)
        if entry["kind"] == "overwrite":
            restore[entry["id"]] = _snapshot_bytes(root, entry["before_snapshot_id"], Path(rel).name)
            sim[rel] = _sha(restore[entry["id"]])
        else:
            sim[rel] = None

    redo_entries: list[dict] = []
    for entry in reversed(members):
        target = root / entry["path"]
        redo = dict(entry)
        if entry["kind"] == "overwrite":
            captured: list = []
            atomic_write_bytes(target, restore[entry["id"]], workspace_root=root,
                               on_snapshot=captured.append,
                               description=f"Before undo of {entry['label']}")
            redo["redo_snapshot_id"] = captured[-1].snapshot_id
            redo["restored_sha256"] = _sha(restore[entry["id"]])
        else:
            trash = root / TRASH_REL / f"{entry['id']}__{target.name}"
            trash.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, trash)
            redo["trash_path"] = trash.relative_to(root).as_posix()
            redo["restored_sha256"] = None
        redo_entries.append(redo)

    data["undo"] = rest
    # Stored in original (forward) order so redo replays them as written.
    data["redo"] = [*data["redo"], *reversed(redo_entries)]
    return _summary(group, members)


def _redo_one(root: Path, data: dict) -> dict:
    from workshop_video_brain.workspace.safe_write import atomic_write_bytes

    group, members, rest = _pop_group(data["redo"])
    sim: dict[str, str | None] = {}
    payload: dict[str, bytes] = {}
    for entry in members:
        rel = entry["path"]
        current = sim[rel] if rel in sim else _file_sha(root / rel)
        if current != entry.get("restored_sha256"):
            raise _conflict(rel)
        if entry["kind"] == "overwrite":
            payload[entry["id"]] = _snapshot_bytes(root, entry["redo_snapshot_id"], Path(rel).name)
        elif not (root / entry["trash_path"]).is_file():
            raise UndoConflict(f"The undone copy of {rel} is no longer in {entry['trash_path']}.")
        sim[rel] = entry["after_sha256"]

    undo_entries: list[dict] = []
    for entry in members:
        target = root / entry["path"]
        back = {k: entry[k] for k in ("id", "group", "label", "path", "kind",
                                       "before_snapshot_id", "after_sha256", "created_at")}
        if entry["kind"] == "overwrite":
            captured: list = []
            atomic_write_bytes(target, payload[entry["id"]], workspace_root=root,
                               on_snapshot=captured.append,
                               description=f"Before redo of {entry['label']}")
            back["before_snapshot_id"] = captured[-1].snapshot_id
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(root / entry["trash_path"], target)
        undo_entries.append(back)

    data["redo"] = rest
    data["undo"] = _cap([*data["undo"], *undo_entries])
    return _summary(group, members)


def _step(root: Path | str, steps: int, which: str, *, check_jobs: bool = True) -> list[dict]:
    if steps < 1:
        raise ValueError("steps must be >= 1")
    root = Path(root).resolve()
    done: list[dict] = []
    with edit_lock(root):
        if check_jobs:
            _check_jobs(root)
        data = _load(root)
        for _ in range(steps):
            if not data[which]:
                break
            summary = (_undo_one if which == "undo" else _redo_one)(root, data)
            # Saved after every group: a conflict on step 3 keeps steps 1-2.
            _save(root, data)
            done.append(summary)
    if not done:
        raise NothingToUndo(f"Nothing to {which}")
    return done


def undo(root: Path | str, steps: int = 1) -> list[dict]:
    """Undo the last *steps* groups. Raises NothingToUndo, UndoConflict, UndoBlocked."""
    return _step(root, steps, "undo")


def redo(root: Path | str, steps: int = 1) -> list[dict]:
    """Redo the last *steps* undone groups."""
    return _step(root, steps, "redo")


def depth(root: Path | str) -> int:
    """Number of undo groups."""
    root = Path(root).resolve()
    with journal_lock(root):
        return len(_groups(_load(root)["undo"]))


def history(root: Path | str, limit: int = 20) -> dict:
    """Newest-first undo and redo groups (label, time, files)."""
    root = Path(root).resolve()
    with journal_lock(root):
        data = _load(root)

    def listing(entries: list[dict]) -> list[dict]:
        out = []
        for group in reversed(_groups(entries)):
            members = [e for e in entries if e["group"] == group]
            item = _summary(group, members)
            item["created_at"] = members[-1]["created_at"]
            out.append(item)
        return out[:limit]

    return {"undo": listing(data["undo"]), "redo": listing(data["redo"])}


def files_above(root: Path | str, target_depth: int) -> list[str]:
    """Files written by the undo groups above *target_depth*."""
    root = Path(root).resolve()
    with journal_lock(root):
        entries = _load(root)["undo"]
    keep = set(_groups(entries)[target_depth:])
    return list(dict.fromkeys(e["path"] for e in entries if e["group"] in keep))


def rollback_to(root: Path | str, target_depth: int) -> list[dict]:
    """Undo groups until the stack is *target_depth* deep; the rollback is not redoable.

    By depth, not by counting successful operations: a failing operation may
    already have written (and journaled) a file before it failed.
    Skips the active-job check: it only puts back what the caller itself
    wrote moments ago.
    """
    root = Path(root).resolve()
    undone: list[dict] = []
    with edit_lock(root):
        redo_before = len(_load(root)["redo"])
        while depth(root) > target_depth:
            undone.extend(_step(root, 1, "undo", check_jobs=False))
        data = _load(root)
        data["redo"] = data["redo"][:redo_before]
        _save(root, data)
    return undone
