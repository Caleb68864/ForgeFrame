"""Validated atomic writes and shared locks for workspace artifacts."""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import threading
from typing import Callable, Iterator

from workshop_video_brain.core.utils.paths import assert_not_protected

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()
_held = threading.local()


@contextmanager
def locked_path(path: Path | str) -> Iterator[None]:
    """Lock a target (or version allocation directory) across threads/processes.

    Locks are reentrant within one thread. Advisory OS locks are released when
    a process exits; lock files deliberately remain to avoid inode races.
    """
    key = str(Path(path).resolve())
    with _locks_guard:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        held = getattr(_held, "keys", None)
        if held is None:
            held = _held.keys = set()
        if key in held:
            yield
            return
        lock_dir = Path(tempfile.gettempdir()) / f"wvb-write-locks-{getattr(os, 'getuid', lambda: 0)()}"
        lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = lock_dir / (sha256(key.encode()).hexdigest() + ".lock")
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if handle.read(1) == b"":
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_bytes(
    path: Path | str,
    data: bytes,
    *,
    workspace_root: Path | str | None = None,
    snapshot_project: bool = True,
    validator: Callable[[Path], object] | None = None,
    description: str = "",
) -> Path:
    """Validate staged bytes, snapshot an existing project, then replace it.

    Validation must raise on failure (or return ``False``). Snapshot failures
    abort the write. A workspace root is required when replacing a project.
    """
    target = assert_not_protected(path).resolve()
    root = Path(workspace_root).resolve() if workspace_root is not None else None
    with locked_path(target):
        assert_not_protected(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        staged: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=f".{target.stem}-", suffix=target.suffix,
                delete=False,
            ) as handle:
                staged = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists():
                os.chmod(staged, target.stat().st_mode & 0o777)
            if validator is not None and validator(staged) is False:
                raise ValueError(f"Validation failed for {target}")
            if target.exists() and target.suffix.lower() == ".kdenlive" and snapshot_project:
                if root is None:
                    raise ValueError("workspace_root is required to snapshot an existing project")
                from workshop_video_brain.workspace.snapshot import create
                create(root, target, description or f"Pre-write snapshot of {target.name}")
            os.replace(staged, target)
            staged = None
            if os.name != "nt":
                fd = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
    return target


def atomic_write_text(
    path: Path | str, text: str, *, encoding: str = "utf-8", **kwargs,
) -> Path:
    """Encode text and write it with :func:`atomic_write_bytes`."""
    return atomic_write_bytes(path, text.encode(encoding), **kwargs)
