"""Talk to the MLT bindings worker, and check a project against what MLT builds.

The bindings exist only for a system Python and segfault on bad handles, so they
always run in a separate one-shot process. A crash there comes back as an
exception or a validation item; it can never take this process down.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workshop_video_brain.core.models.enums import ValidationSeverity
from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.validation import ValidationItem
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    ANALYSIS_TIMEOUT_SECONDS,
    CAPABILITY_TIMEOUT_SECONDS,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import AUDIO_TWIN_SUFFIX

logger = logging.getLogger(__name__)

PROTOCOL = 1
WORKER_PATH = Path(__file__).with_name("_worker.py")
_LOAD_TIMEOUT_SECONDS = 120
_MLT_NOISE = re.compile(
    r"^mlt_repository_register: Duplicate|^mlt_repository_init: failed to dlopen|"
    r"^\s*\(lib\S+: cannot open shared object file"
)


class MltUnavailable(RuntimeError):
    """No interpreter here can import the MLT bindings."""


class MltWorkerError(RuntimeError):
    """The worker reported a failure, exited badly, or broke the protocol."""

    def __init__(self, message: str, stderr_tail: str = "") -> None:
        super().__init__(message)
        self.stderr_tail = stderr_tail


class MltWorkerCrashed(MltWorkerError):
    """The worker died on a signal, usually a segfault in the bindings."""

    def __init__(self, signal_name: str, stderr_tail: str = "") -> None:
        super().__init__(f"MLT worker crashed ({signal_name})", stderr_tail)
        self.signal_name = signal_name


@dataclass(frozen=True)
class MltInterpreter:
    path: str
    mlt_version: str
    python_version: str


@dataclass
class LoadCheckResult:
    engine: str
    items: list[ValidationItem] = field(default_factory=list)
    reason: str = ""


_cache_lock = threading.Lock()
_cache: dict[str, MltInterpreter | None] = {}


def _stderr_tail(stderr: str | None, lines: int = 20) -> str:
    kept = [line for line in (stderr or "").splitlines() if line.strip() and not _MLT_NOISE.match(line)]
    return "\n".join(kept[-lines:])


def _invoke(
    interpreter: str,
    op: str,
    args: dict,
    timeout: float,
    on_event: Callable[[dict], None] | None,
    worker_path: Path,
) -> dict:
    request = json.dumps({"protocol": PROTOCOL, "op": op, "args": args}) + "\n"
    proc = subprocess.run(
        [interpreter, "-I", str(worker_path)],
        input=request, capture_output=True, text=True, timeout=timeout, check=False,
    )
    tail = _stderr_tail(proc.stderr)
    if proc.returncode < 0:
        try:
            name = signal.Signals(-proc.returncode).name
        except ValueError:
            name = f"signal {-proc.returncode}"
        raise MltWorkerCrashed(name, tail)

    final = None
    for line in (proc.stdout or "").splitlines():
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError as exc:
            raise MltWorkerError(f"MLT worker broke the protocol: {line[:200]!r}", tail) from exc
        if not isinstance(message, dict):
            raise MltWorkerError(f"MLT worker broke the protocol: {line[:200]!r}", tail)
        if "event" in message:
            if on_event is not None:
                on_event(message)
        else:
            final = message
    if final is None:
        raise MltWorkerError(f"MLT worker gave no result (rc={proc.returncode}): {tail}", tail)
    if not final.get("ok"):
        error = final.get("error") or {}
        raise MltWorkerError(f"{error.get('type', 'Error')}: {error.get('message', 'unknown failure')}", tail)
    if proc.returncode != 0:
        raise MltWorkerError(f"MLT worker exited with rc={proc.returncode}: {tail}", tail)
    return final.get("result") or {}


def _probe(candidate: str, worker_path: Path) -> MltInterpreter | None:
    try:
        pong = _invoke(candidate, "ping", {}, CAPABILITY_TIMEOUT_SECONDS, None, worker_path)
    except (MltWorkerError, OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("%s cannot run the MLT worker: %s", candidate, exc)
        return None
    if pong.get("protocol") != PROTOCOL:
        return None
    return MltInterpreter(candidate, str(pong.get("mlt_version", "")), str(pong.get("python", "")))


def find_mlt_python(refresh: bool = False, *, _worker_path: Path | None = None) -> MltInterpreter | None:
    """Find an interpreter that can import the bindings, or None.

    ``WVB_MLT_PYTHON``, when set, is the only candidate: explicit configuration
    never silently falls back. The result is cached per configuration.
    """
    configured = os.environ.get("WVB_MLT_PYTHON", "")
    key = f"{configured}|{_worker_path or ''}"
    with _cache_lock:
        if not refresh and key in _cache:
            return _cache[key]
        candidates = [configured] if configured else [sys.executable, "/usr/bin/python3"]
        seen: set[str] = set()
        found = None
        for candidate in candidates:
            real = os.path.realpath(candidate)
            if real in seen or not os.path.exists(real):
                continue
            seen.add(real)
            found = _probe(candidate, _worker_path or WORKER_PATH)
            if found is not None:
                break
        _cache[key] = found
        return found


def run_worker(
    op: str,
    args: dict[str, Any],
    *,
    timeout: float,
    on_event: Callable[[dict], None] | None = None,
    _interpreter: str | None = None,
    _worker_path: Path | None = None,
) -> dict:
    """Run one op in a fresh worker and return its result.

    Raises :class:`MltUnavailable`, :class:`MltWorkerError` or
    :class:`MltWorkerCrashed`. ``subprocess.TimeoutExpired`` propagates, and
    ``tool_guard`` classifies it.
    """
    interpreter = _interpreter
    if interpreter is None:
        found = find_mlt_python()
        if found is None:
            raise MltUnavailable(
                "MLT bindings not found: install your distro's python3-mlt, or set WVB_MLT_PYTHON."
            )
        interpreter = found.path
    return _invoke(interpreter, op, args, timeout, on_event, _worker_path or WORKER_PATH)


def _item(severity: ValidationSeverity, message: str, location: str = "") -> ValidationItem:
    return ValidationItem(severity=severity, category="load_check", message=message, location=location)


def _error(message: str, location: str = "") -> ValidationItem:
    return _item(ValidationSeverity.error, message, location)


def _warning(message: str, location: str = "") -> ValidationItem:
    return _item(ValidationSeverity.warning, message, location)


def compare_inspection(inspection: dict, model: KdenliveProject) -> list[ValidationItem]:
    """Compare what MLT built with our parsed model; pure, for canned input."""
    items: list[ValidationItem] = []
    profile = inspection.get("profile") or {}
    width, height = profile.get("width"), profile.get("height")
    if (width, height) != (model.profile.width, model.profile.height):
        items.append(_error(
            f"Profile size differs: MLT {width}x{height}, model {model.profile.width}x{model.profile.height}.",
            "profile",
        ))
    den = profile.get("frame_rate_den") or 0
    mlt_fps = (profile.get("frame_rate_num") or 0) / den if den else 0.0
    if abs(mlt_fps - model.profile.fps) >= 1e-3:
        items.append(_error(f"Frame rate differs: MLT {mlt_fps:.3f}, model {model.profile.fps:.3f}.", "profile"))

    tracks = inspection.get("tracks") or []
    if not tracks:
        items.append(_error("MLT built no sequence tracks from this project.", "sequence"))

    mlt_playlists = {
        playlist.get("id"): playlist
        for track in tracks
        for playlist in track.get("playlists") or []
    }
    model_ids = {playlist.id for playlist in model.playlists}
    for playlist_id, playlist in mlt_playlists.items():
        if playlist_id in model_ids or str(playlist_id).endswith("_kdpair") or not playlist.get("clips"):
            continue
        items.append(_warning(f"MLT has playlist '{playlist_id}' with clips that the model does not.", str(playlist_id)))

    for playlist in model.playlists:
        built = mlt_playlists.get(playlist.id)
        placed = []
        start = 0
        for entry in playlist.entries:
            if entry.producer_id:
                placed.append((entry, start))
            start += entry.out_point - entry.in_point + 1
        if built is None:
            if placed:
                items.append(_error(f"Playlist '{playlist.id}' has clips but MLT did not build it.", playlist.id))
            continue
        clips = built.get("clips") or []
        if len(clips) != len(placed):
            items.append(_error(
                f"Playlist '{playlist.id}' has {len(placed)} clips in the model, {len(clips)} in MLT.",
                playlist.id,
            ))
            continue
        for index, ((entry, model_start), clip) in enumerate(zip(placed, clips)):
            location = f"{playlist.id}[{index}]"
            for label, ours, theirs in (
                ("in", entry.in_point, clip.get("in")),
                ("out", entry.out_point, clip.get("out")),
                ("start", model_start, clip.get("start")),
            ):
                if ours != theirs:
                    items.append(_error(
                        f"Playlist '{playlist.id}' clip {index}: {label} is {ours} in the model, {theirs} in MLT.",
                        location,
                    ))
            built_id = str(clip.get("producer_id") or "").removesuffix(AUDIO_TWIN_SUFFIX)
            if built_id != entry.producer_id:
                items.append(_warning(
                    f"Playlist '{playlist.id}' clip {index}: producer is '{entry.producer_id}' in the model, "
                    f"'{built_id}' in MLT.",
                    location,
                ))
    return items


def _melt_load_check(project_path: Path) -> LoadCheckResult:
    melt = shutil.which("melt")
    reason = "MLT bindings not available; melt can only say whether the project loads, not compare its structure."
    proc = subprocess.run(
        [melt, str(project_path), "out=0", "-consumer", "null:", "terminate_on_pause=1"],
        capture_output=True, text=True, timeout=_LOAD_TIMEOUT_SECONDS, check=False,
    )
    items = [_warning(line.strip()) for line in (proc.stderr or "").splitlines() if "failed to load" in line]
    if proc.returncode != 0:
        items.append(_error(f"melt exited with rc={proc.returncode}: {_stderr_tail(proc.stderr, 6)}"))
    return LoadCheckResult("melt", items, reason)


def load_check(project_path: Path | str, model: KdenliveProject, engine: str = "auto") -> LoadCheckResult:
    """Check a written project against what MLT builds from it. Never modifies it."""
    project_path = Path(project_path)
    if engine in ("auto", "bindings") and find_mlt_python() is not None:
        try:
            inspection = run_worker("inspect", {"path": str(project_path)}, timeout=_LOAD_TIMEOUT_SECONDS)
        except MltWorkerCrashed as exc:
            return LoadCheckResult("bindings", [_error(
                f"MLT crashed while loading this project ({exc.signal_name}) -- "
                "the file probably references something MLT cannot build.",
            )], str(exc))
        except MltWorkerError as exc:
            return LoadCheckResult("bindings", [_error(f"MLT could not inspect this project: {exc}")], str(exc))
        return LoadCheckResult("bindings", compare_inspection(inspection, model))
    if engine in ("auto", "melt") and shutil.which("melt"):
        return _melt_load_check(project_path)
    return LoadCheckResult(
        "skipped",
        [_item(ValidationSeverity.info, "No MLT engine available, so the load check did not run.")],
        "Neither MLT bindings nor melt are available.",
    )


def _melt_frame(project_path: Path, frame: int, size: tuple[int, int] | None, out_dir: Path, melt: str) -> Path:
    """Grab one frame with the melt CLI, at the project's size, then scale it if asked.

    The size is not passed to melt: ``width=``/``height=`` make it render through its
    default profile, which pillarboxes the picture and shifts its colours.
    """
    final = out_dir / f"f_{frame:06d}.png"
    with tempfile.TemporaryDirectory(prefix=".melt_", dir=out_dir) as scratch:
        pattern = Path(scratch) / "f_%05d.png"
        proc = subprocess.run(
            [melt, str(project_path), f"in={frame}", f"out={frame}",
             "-consumer", f"avformat:{pattern}", "vcodec=png", "an=1", "terminate_on_pause=1"],
            capture_output=True, text=True, timeout=ANALYSIS_TIMEOUT_SECONDS, check=False,
        )
        written = sorted(Path(scratch).glob("f_*.png"))
        if proc.returncode != 0 or not written:
            raise MltWorkerError(f"melt could not grab frame {frame}: {_stderr_tail(proc.stderr, 6)}")
        if size is None:
            written[-1].replace(final)
            return final
        scaled = subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", "-i", str(written[-1]), "-vf", f"scale={size[0]}:{size[1]}", str(final)],
            capture_output=True, text=True, timeout=ANALYSIS_TIMEOUT_SECONDS, check=False,
        )
        if scaled.returncode != 0:
            raise MltWorkerError(f"ffmpeg could not scale frame {frame}: {_stderr_tail(scaled.stderr, 6)}")
    return final


def timeline_frames(
    project_path: Path | str,
    frames: list[int],
    width: int,
    out_dir: Path | str,
    engine: str = "auto",
    *,
    profile_size: tuple[int, int] | None = None,
) -> dict:
    """Grab composited timeline frames as PNGs into *out_dir*.

    The bindings seek directly. The melt fallback runs once per frame, and needs
    ``profile_size`` to keep the aspect ratio. Raises :class:`MltUnavailable`
    when neither engine exists.
    """
    project_path, out_dir = Path(project_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if engine in ("auto", "bindings") and find_mlt_python() is not None:
        result = run_worker(
            "frames",
            {"path": str(project_path), "frames": list(frames), "width": width, "out_dir": str(out_dir)},
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
        return {**result, "engine": "bindings"}
    melt = shutil.which("melt")
    if engine not in ("auto", "melt") or not melt:
        raise MltUnavailable("Neither MLT bindings nor melt are available to grab timeline frames.")
    source_width, source_height = profile_size or (16, 9)
    height = round(width * source_height / source_width / 2) * 2
    size = None if (width, height) == (source_width, source_height) else (width, height)
    results = [
        {"requested": frame, "frame": frame, "width": width, "height": height,
         "path": str(_melt_frame(project_path, frame, size, out_dir, melt))}
        for frame in frames
    ]
    return {"frames": results, "length": None, "engine": "melt"}


def run_streaming_worker(
    op: str,
    args: dict[str, Any],
    *,
    timeout: float,
    on_event: Callable[[dict], None] | None = None,
    _interpreter: str | None = None,
    _worker_path: Path | None = None,
) -> tuple[dict, str]:
    """Run a long op, delivering events as they arrive. Returns ``(result, stderr)``.

    stderr goes to a temp file, because MLT's noise would fill an unread pipe and
    deadlock. On expiry the worker is killed and ``TimeoutExpired`` raised.
    """
    interpreter = _interpreter
    if interpreter is None:
        found = find_mlt_python()
        if found is None:
            raise MltUnavailable("MLT bindings not found: install python3-mlt, or set WVB_MLT_PYTHON.")
        interpreter = found.path
    command = [interpreter, "-I", str(_worker_path or WORKER_PATH)]
    deadline = time.monotonic() + timeout
    final: dict | None = None
    with tempfile.TemporaryFile("w+", encoding="utf-8") as stderr_file:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr_file, text=True,
        )
        timer = threading.Timer(max(0.0, deadline - time.monotonic()), process.kill)
        timer.daemon = True
        timer.start()
        try:
            process.stdin.write(json.dumps({"protocol": PROTOCOL, "op": op, "args": args}) + "\n")
            process.stdin.close()
            for line in process.stdout:
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except ValueError as exc:
                    process.kill()
                    raise MltWorkerError(f"MLT worker broke the protocol: {line[:200]!r}") from exc
                if "event" in message:
                    if on_event is not None:
                        on_event(message)
                else:
                    final = message
            returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()
        stderr_file.seek(0)
        stderr = stderr_file.read()
    if time.monotonic() >= deadline:
        raise subprocess.TimeoutExpired(command, timeout)
    tail = _stderr_tail(stderr)
    if returncode < 0:
        try:
            name = signal.Signals(-returncode).name
        except ValueError:
            name = f"signal {-returncode}"
        raise MltWorkerCrashed(name, tail)
    if final is None:
        raise MltWorkerError(f"MLT worker gave no result (rc={returncode}): {tail}", tail)
    if not final.get("ok"):
        error = final.get("error") or {}
        raise MltWorkerError(f"{error.get('type', 'Error')}: {error.get('message', 'unknown failure')}", tail)
    return final.get("result") or {}, stderr
