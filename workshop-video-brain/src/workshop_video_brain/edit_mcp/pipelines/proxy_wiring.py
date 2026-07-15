"""Proxy wiring -- §3 Medium "Proxy wiring".

``proxy_generate`` (``adapters/ffmpeg/proxy.py``) writes proxy files under
``media/proxies/`` but never tells Kdenlive to use them.  This module closes that
gap: it wires generated proxies into a project by setting the producer
``resource``/``kdenlive:proxy``/``kdenlive:originalurl`` properties and the
``kdenlive:docproperties.*`` proxy settings that Kdenlive reads.

Format verified against KDE source + a real proxied project -- see
``docs/research/2026-07-03-tutorial-effect-analysis/proxy-wiring.md``.

Pure functions only (no I/O); the bundle ``server/bundles/proxy_wiring.py`` wraps
these with parse/snapshot/serialize.  Render safety (``use_originals`` /
``originals_render_copy``) is consumed by ``pipelines/render_pipeline.run_render``
so a full-res render never silently uses a proxy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject, Producer

# Sentinel Kdenlive writes for "no proxy for this clip".
PROXY_SENTINEL = "-"

# ffmpeg params matching OUR generator (adapters/ffmpeg/proxy.py: 720p x264 CRF
# 23), so the doc-level proxyparams describes the files we actually produce.
PROXY_PARAMS = "-vf scale=-2:720 -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k"
PROXY_EXTENSION = "mp4"
PROXY_RESIZE = "720"
PROXY_MIN_SIZE = "1000"  # tutorial default: proxy videos wider than 1000 px

# mlt_services that are never video clips and so never get a proxy.
_NON_AV_SERVICES = frozenset(
    {"color", "kdenlivetitle", "qimage", "pixbuf", "xml", "consumer", "blank"}
)


# ---------------------------------------------------------------------------
# Naming (must match adapters/ffmpeg/proxy.proxy_path_for)
# ---------------------------------------------------------------------------

def default_proxy_path(source: str, proxy_dir: Path | str) -> Path:
    """Deterministic proxy path for *source*, matching ``proxy_generate``.

    ``proxy_path_for`` produces ``{proxy_dir}/{source.stem}_proxy.mp4``.
    """
    return Path(proxy_dir) / f"{Path(source).stem}_proxy.mp4"


# ---------------------------------------------------------------------------
# Producer inspection
# ---------------------------------------------------------------------------

def is_proxied(producer: Producer) -> bool:
    """True if *producer* carries an active proxy (``kdenlive:proxy`` set)."""
    proxy = producer.properties.get("kdenlive:proxy", "")
    return bool(proxy) and proxy != PROXY_SENTINEL


def _is_proxyable(producer: Producer) -> bool:
    if not producer.resource:
        return False
    service = producer.properties.get("mlt_service", "")
    if service in _NON_AV_SERVICES:
        return False
    return True


def proxyable_producers(project: KdenliveProject) -> list[Producer]:
    """Video producers eligible for a proxy (have a resource, are AV)."""
    return [p for p in project.producers if _is_proxyable(p)]


def _original_of(producer: Producer) -> str:
    """The producer's original source -- originalurl if proxied, else resource."""
    return producer.properties.get("kdenlive:originalurl") or producer.resource


def _matches_source(producer: Producer, source: str) -> bool:
    original = _original_of(producer)
    return original == source or Path(original).name == Path(source).name or (
        producer.resource == source
    )


def _select_targets(
    project: KdenliveProject, source: str, all_clips: bool
) -> list[Producer]:
    candidates = proxyable_producers(project)
    if source:
        return [p for p in candidates if _matches_source(p, source)]
    return candidates  # all_clips or default both operate over every AV producer


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@dataclass
class ProducerProxyStatus:
    producer_id: str
    original: str
    proxy: str  # "" when not wired
    proxied: bool
    proxy_file_exists: bool


@dataclass
class ProxyReport:
    attached: list[str] = field(default_factory=list)
    detached: list[str] = field(default_factory=list)
    skipped_missing_proxy: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "attached": self.attached,
            "detached": self.detached,
            "skipped_missing_proxy": self.skipped_missing_proxy,
            "unchanged": self.unchanged,
        }


# ---------------------------------------------------------------------------
# Doc-level proxy settings
# ---------------------------------------------------------------------------

def _enable_proxy_docproperties(project: KdenliveProject) -> None:
    project.docproperties.update(
        {
            "enableproxy": "1",
            "generateproxy": "1",
            "proxyparams": PROXY_PARAMS,
            "proxyextension": PROXY_EXTENSION,
            "proxyresize": PROXY_RESIZE,
            "proxyminsize": PROXY_MIN_SIZE,
        }
    )


# ---------------------------------------------------------------------------
# attach / detach
# ---------------------------------------------------------------------------

def attach_proxies(
    project: KdenliveProject,
    proxy_dir: Path | str,
    source: str = "",
    proxy_path: str = "",
    all_clips: bool = False,
    require_exists: bool = True,
) -> tuple[KdenliveProject, ProxyReport]:
    """Wire generated proxy files into *project* (in place) and enable proxies.

    For each targeted producer: set ``kdenlive:originalurl`` to its original
    source, ``kdenlive:proxy`` + ``resource`` to the proxy file.  Default
    (no *source*, ``all_clips=False``) auto-wires every AV producer that has a
    matching ``media/proxies/{stem}_proxy.mp4``.  A producer whose proxy file is
    missing is reported under ``skipped_missing_proxy`` and left untouched when
    *require_exists* (so the project always melt-accepts).

    ``proxy_path`` (explicit single file) is honoured only when *source* selects
    one producer.
    """
    report = ProxyReport()
    targets = _select_targets(project, source, all_clips)
    proxy_dir = Path(proxy_dir)
    any_attached = False

    for producer in targets:
        original = _original_of(producer)
        if proxy_path and source:
            candidate = Path(proxy_path)
        else:
            candidate = default_proxy_path(original, proxy_dir)

        exists = candidate.exists()
        if require_exists and not exists:
            report.skipped_missing_proxy.append(producer.id)
            continue

        producer.properties["kdenlive:originalurl"] = original
        producer.properties["kdenlive:proxy"] = str(candidate)
        producer.resource = str(candidate)
        producer.properties["resource"] = str(candidate)
        report.attached.append(producer.id)
        any_attached = True

    if any_attached:
        _enable_proxy_docproperties(project)

    return project, report


def detach_proxies(
    project: KdenliveProject,
    source: str = "",
    all_clips: bool = False,
) -> tuple[KdenliveProject, ProxyReport]:
    """Revert targeted producers to their originals (in place).

    ``resource`` <- ``kdenlive:originalurl``; ``kdenlive:proxy`` set to the
    ``"-"`` sentinel.  When no producer remains proxied, ``enableproxy`` is set
    to ``0``.
    """
    report = ProxyReport()
    targets = _select_targets(project, source, all_clips)

    for producer in targets:
        if not is_proxied(producer):
            report.unchanged.append(producer.id)
            continue
        original = producer.properties.get("kdenlive:originalurl") or producer.resource
        producer.resource = original
        producer.properties["resource"] = original
        producer.properties["kdenlive:proxy"] = PROXY_SENTINEL
        report.detached.append(producer.id)

    if not any(is_proxied(p) for p in project.producers):
        if "enableproxy" in project.docproperties:
            project.docproperties["enableproxy"] = "0"

    return project, report


def proxy_status(
    project: KdenliveProject,
    proxy_dir: Path | str,
) -> list[ProducerProxyStatus]:
    """Read-only per-producer proxy report (no mutation)."""
    proxy_dir = Path(proxy_dir)
    out: list[ProducerProxyStatus] = []
    for producer in proxyable_producers(project):
        proxied = is_proxied(producer)
        original = _original_of(producer)
        if proxied:
            proxy = producer.properties.get("kdenlive:proxy", "")
        else:
            # What proxy WOULD be used if generated (for the "missing" report).
            proxy = str(default_proxy_path(original, proxy_dir))
        out.append(
            ProducerProxyStatus(
                producer_id=producer.id,
                original=original,
                proxy=proxy if proxied else "",
                proxied=proxied,
                proxy_file_exists=Path(proxy).exists() if proxy else False,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Render safety -- Kdenlive's KdenliveDoc::useOriginals
# ---------------------------------------------------------------------------

def use_originals(project: KdenliveProject) -> KdenliveProject:
    """Swap every proxied producer's ``resource`` back to its original (in place).

    Reproduces Kdenlive's ``KdenliveDoc::useOriginals`` so a headless melt render
    uses full-resolution sources.  ``kdenlive:proxy`` is preserved (the wiring is
    re-enabled next time the project is opened in the GUI) -- only ``resource`` is
    pointed at ``kdenlive:originalurl``.
    """
    for producer in project.producers:
        if not is_proxied(producer):
            continue
        original = producer.properties.get("kdenlive:originalurl")
        if not original:
            continue
        producer.resource = original
        producer.properties["resource"] = original
    return project


def project_has_proxies(project: KdenliveProject) -> bool:
    return any(is_proxied(p) for p in project.producers)


def originals_render_copy(project_path: Path | str, dest_dir: Path | str) -> Path:
    """Return a path safe to feed melt for a FULL-RES render.

    If the project has no active proxies the original path is returned unchanged.
    Otherwise a resources-swapped copy is written under *dest_dir* and its path
    returned, so ``melt`` renders originals instead of proxies.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )

    project_path = Path(project_path)
    project = parse_project(project_path)
    if not project_has_proxies(project):
        return project_path

    use_originals(project)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{project_path.stem}.originals.kdenlive"
    serialize_project(project, out)
    return out
