"""One cached registry of the MLT services this host can load.

Filled from the bindings worker, else ``melt -query``. It answers "can MLT load
this?" and :data:`KDENLIVE_UNSUPPORTED` answers "will Kdenlive keep it?". Those are
two different gates; see ``vault/wiki/mlt-service-registry-vs-kdenlive-registry.md``.
"""
from __future__ import annotations

import difflib
import logging
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import CAPABILITY_TIMEOUT_SECONDS
from workshop_video_brain.edit_mcp.adapters.mlt import engine

logger = logging.getLogger(__name__)

KINDS = ("filters", "transitions", "producers", "consumers", "links")

#: Services MLT may well load but that CLAUDE.md hard rule 11 says Kdenlive drops,
#: mapped to the substitute to use.
KDENLIVE_UNSUPPORTED: dict[str, str] = {
    "avfilter.crop": "crop",
    "avfilter.curves": "frei0r.curves",
    "avfilter.boxblur": "box_blur",
}

_FAILURE_TTL_SECONDS = 60.0
_QUERY_LINE = re.compile(r"^  - (\S+)$", re.M)


@dataclass(frozen=True)
class ServiceRegistry:
    engine: str  # "bindings" | "melt"
    mlt_version: str
    services: dict[str, frozenset[str]]

    def has(self, kind: str, name: str) -> bool:
        return name in self.services.get(kind, frozenset())


class UnregisteredServiceError(ValueError):
    """A service MLT on this host cannot load, or Kdenlive would drop."""

    def __init__(self, kind: str, name: str, suggestions: list[str], substitute: str | None) -> None:
        self.kind = kind
        self.name = name
        self.suggestions = suggestions
        self.substitute = substitute
        if substitute:
            message = f"Kdenlive drops '{name}' on load; use '{substitute}' instead."
        else:
            hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            message = f"'{name}' is not an MLT {kind.rstrip('s')} on this host.{hint}"
        super().__init__(message)


_lock = threading.Lock()
_cached: ServiceRegistry | None = None
_failed_at: float | None = None
_override: ServiceRegistry | None = None


def parse_melt_query(stdout: str) -> list[str]:
    """Names from ``melt -query <kind>`` YAML, skipping its ``---`` and ``<kind>:`` lines."""
    return _QUERY_LINE.findall(stdout)


def _from_bindings() -> ServiceRegistry | None:
    if engine.find_mlt_python() is None:
        return None
    try:
        result = engine.run_worker("registry", {}, timeout=CAPABILITY_TIMEOUT_SECONDS)
    except (engine.MltWorkerError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("MLT worker could not list services: %s", exc)
        return None
    return ServiceRegistry(
        "bindings",
        str(result.get("mlt_version", "")),
        {kind: frozenset(result.get(kind) or ()) for kind in KINDS},
    )


def _from_melt() -> ServiceRegistry | None:
    melt = shutil.which("melt")
    if not melt:
        return None
    services: dict[str, frozenset[str]] = {}
    try:
        for kind in KINDS:
            proc = subprocess.run(
                [melt, "-query", kind], capture_output=True, text=True,
                timeout=CAPABILITY_TIMEOUT_SECONDS, check=False,
            )
            if proc.returncode != 0:
                return None
            services[kind] = frozenset(parse_melt_query(proc.stdout))
        version = subprocess.run(
            [melt, "--version"], capture_output=True, text=True,
            timeout=CAPABILITY_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("melt could not list services: %s", exc)
        return None
    match = re.search(r"melt\s+(\S+)", (version.stdout or "") + (version.stderr or ""))
    return ServiceRegistry("melt", match.group(1) if match else "", services)


def get_registry(refresh: bool = False) -> ServiceRegistry | None:
    """Return the host's registry, or None without MLT. A miss is remembered for 60 s."""
    global _cached, _failed_at
    if _override is not None:
        return _override
    with _lock:
        if not refresh:
            if _cached is not None:
                return _cached
            if _failed_at is not None and time.monotonic() - _failed_at < _FAILURE_TTL_SECONDS:
                return None
        registry = _from_bindings() or _from_melt()
        _cached = registry
        _failed_at = None if registry is not None else time.monotonic()
        return registry


def loaded_registry() -> ServiceRegistry | None:
    """The registry if one is already in memory. Never loads, so it never spawns."""
    return _override if _override is not None else _cached


@contextmanager
def use_registry(registry: ServiceRegistry | None) -> Iterator[None]:
    """Test seam: answer from *registry* for the duration of the block."""
    global _override
    previous = _override
    _override = registry
    try:
        yield
    finally:
        _override = previous


def service_info(kind: str, name: str) -> str | None:
    """YAML metadata for one service, or None if unknown. *kind* is plural, like ``filters``."""
    singular = kind.rstrip("s")
    if engine.find_mlt_python() is not None:
        try:
            return engine.run_worker(
                "service_info", {"kind": singular, "name": name}, timeout=CAPABILITY_TIMEOUT_SECONDS
            ).get("yaml")
        except (engine.MltWorkerError, subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("MLT worker could not describe %s: %s", name, exc)
    melt = shutil.which("melt")
    if not melt:
        return None
    try:
        proc = subprocess.run(
            [melt, "-query", f"{singular}={name}"], capture_output=True, text=True,
            timeout=CAPABILITY_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 and "identifier" in proc.stdout else None


def check_service(
    kind: str,
    name: str,
    *,
    registry: ServiceRegistry | None = None,
    check_host: bool = True,
) -> str:
    """Return ``"ok"``, ``"unchecked"`` or ``"skipped"``, or raise :class:`UnregisteredServiceError`.

    The Kdenlive denylist always applies. With no registry (a host without MLT) this
    fails open. ``check_host=False`` skips the host check, for a project that will
    render on another machine.
    """
    if name in KDENLIVE_UNSUPPORTED:
        raise UnregisteredServiceError(kind, name, [], KDENLIVE_UNSUPPORTED[name])
    if not check_host:
        return "skipped"
    active = registry if registry is not None else get_registry()
    if active is None:
        return "unchecked"
    if active.has(kind, name):
        return "ok"
    close = difflib.get_close_matches(name, sorted(active.services.get(kind, ())), n=3, cutoff=0.6)
    raise UnregisteredServiceError(kind, name, close, None)
