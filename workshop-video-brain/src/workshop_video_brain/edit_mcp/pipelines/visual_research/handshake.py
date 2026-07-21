"""Two-call agent handshake: generate candidate frames, then select from them.

``generate_handshake`` runs discovery only (probe -> regions ->
:func:`generate_candidates` -> :class:`FrameScorer` -> :func:`deduplicate`),
persists every surviving candidate frame under
``<output_dir>/candidates/*.png`` plus a schema-v1 ``candidates.json``
manifest, and returns that manifest so an agent can inspect thumbnails before
committing. ``select_from_handshake`` rehydrates the manifest, validates the
chosen ids and the source fingerprint, records the selection, and hands the
chosen candidates to :func:`export_package` for the final package.

Process spawning and MCP tool registration are deliberately absent from this
module -- those belong to the ffmpeg adapters and the ``research_candidates``
shell respectively.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from workshop_video_brain.core.models.visual_research import (
    FrameCandidate,
    ResearchCapture,
    ResearchConfig,
    ResearchManifest,
    ResearchQuery,
    ResearchRegion,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.transcript.parsers import parse_transcript
from workshop_video_brain.edit_mcp.pipelines.transcript_repository import (
    TranscriptRepository,
)
from workshop_video_brain.edit_mcp.pipelines.visual_research.candidates import (
    generate_candidates,
)
from workshop_video_brain.edit_mcp.pipelines.visual_research.dedup import deduplicate
from workshop_video_brain.edit_mcp.pipelines.visual_research.export import export_package
from workshop_video_brain.edit_mcp.pipelines.visual_research.regions import select_regions
from workshop_video_brain.edit_mcp.pipelines.visual_research.scoring import FrameScorer

SCHEMA_VERSION = 1
CANDIDATES_FILENAME = "candidates.json"
CANDIDATES_SUBDIR = "candidates"


class HandshakeError(ValueError):
    """Base class for handshake validation failures.

    Callers (the ``research_candidates`` tool shell) catch this family and
    translate it into the structured error contract -- this module never
    builds error envelopes itself.
    """


class OutputDirNotEmptyError(HandshakeError):
    """Raised when ``output_dir`` already has content and ``overwrite`` is False."""


class CandidatesManifestNotFoundError(HandshakeError):
    """Raised when ``candidates.json`` is missing from ``candidates_dir``."""


class UnknownCandidateIdsError(HandshakeError):
    """Raised when one or more requested candidate ids are not in the manifest."""

    def __init__(self, unknown_ids: list[str], valid_ids: list[str]):
        self.unknown_ids = unknown_ids
        self.valid_ids = valid_ids
        super().__init__(
            f"Unknown candidate id(s) {unknown_ids}; valid ids are {valid_ids}"
        )


class SourceFingerprintMismatchError(HandshakeError):
    """Raised when the source video no longer matches the recorded fingerprint."""


# ---------------------------------------------------------------------------
# Region resolution (mirrors service._fallback_region; no import of service
# privates needed since the fallback is this small)
# ---------------------------------------------------------------------------


def _fallback_region(source_id, duration_seconds: float, config: ResearchConfig) -> ResearchRegion:
    span = duration_seconds if duration_seconds > 0 else config.windowing.maximum_region_seconds
    end_seconds = min(span, config.windowing.maximum_region_seconds)
    return ResearchRegion(
        source_id=source_id,
        start_seconds=0.0,
        end_seconds=end_seconds,
        source_method="uniform_sampling",
        reason="no transcript and no explicit range: bounded uniform sampling",
    )


def _build_transcript_repository(transcript_path: str | Path | None) -> TranscriptRepository | None:
    if transcript_path is None:
        return None
    segments = parse_transcript(Path(transcript_path))
    return TranscriptRepository(segments)


def _resolve_regions(
    repo: TranscriptRepository | None,
    source_id,
    query: str | None,
    start_seconds: float | None,
    end_seconds: float | None,
    duration_seconds: float,
    config: ResearchConfig,
) -> list[ResearchRegion]:
    has_query = bool(query) or start_seconds is not None or end_seconds is not None
    if not has_query:
        return [_fallback_region(source_id, duration_seconds, config)]

    research_query = ResearchQuery(
        source_id=source_id,
        text=query or "",
        start_seconds=start_seconds,
        end_seconds=end_seconds,
    )
    regions = select_regions(repo, research_query, config)
    if not regions:
        return [_fallback_region(source_id, duration_seconds, config)]
    return regions


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def _fingerprint_source(video_path: Path) -> dict:
    stat = video_path.stat()
    return {
        "path": str(video_path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _fingerprint_matches(recorded: dict, video_path: Path) -> bool:
    if not video_path.exists():
        return False
    stat = video_path.stat()
    return (
        recorded.get("size_bytes") == stat.st_size
        and recorded.get("mtime_ns") == stat.st_mtime_ns
    )


# ---------------------------------------------------------------------------
# Directory prep
# ---------------------------------------------------------------------------


def _prepare_output_dir(output_dir: Path, overwrite: bool) -> None:
    manifest_path = output_dir / CANDIDATES_FILENAME
    if output_dir.exists() and any(output_dir.iterdir()):
        if not (overwrite and manifest_path.exists()):
            raise OutputDirNotEmptyError(
                f"Output directory already exists and is not empty: {output_dir}. "
                "Pass overwrite=True to regenerate an existing candidates package."
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# generate_handshake
# ---------------------------------------------------------------------------


def generate_handshake(
    video_path: Path | str,
    *,
    transcript_path: Path | str | None = None,
    query: str | None = None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    output_dir: Path | str,
    max_candidates: int | None = None,
    config: ResearchConfig | None = None,
    overwrite: bool = False,
) -> dict:
    """Run discovery only and persist a schema-v1 ``candidates.json`` manifest.

    Writes ``<output_dir>/candidates/cand-NNN.png`` for every surviving
    candidate (ordered by region, then timestamp) plus
    ``<output_dir>/candidates.json``, and returns that manifest dict.
    """
    video_path = Path(video_path).resolve()
    output_dir = Path(output_dir)
    cfg = config.model_copy(deep=True) if config is not None else ResearchConfig()
    if max_candidates is not None:
        cfg.candidate_generation.max_candidates_per_region = max_candidates

    _prepare_output_dir(output_dir, overwrite)
    candidates_dir = output_dir / CANDIDATES_SUBDIR
    candidates_dir.mkdir(parents=True, exist_ok=True)

    source_asset = probe_media(video_path)
    duration_seconds = source_asset.duration_seconds or source_asset.duration

    repo = _build_transcript_repository(transcript_path)
    regions = _resolve_regions(
        repo, source_asset.id, query, start_seconds, end_seconds, duration_seconds, cfg
    )

    per_region_candidates: list[tuple[ResearchRegion, list[FrameCandidate]]] = []
    for region in regions:
        raw = generate_candidates(video_path, region, source_asset, cfg)
        scorer = FrameScorer()
        ranked = scorer.rank(raw, cfg)
        if cfg.deduplication.enabled and ranked:
            kept, _duplicate_map = deduplicate(
                ranked, threshold=cfg.deduplication.max_hamming_distance
            )
        else:
            kept = ranked
        kept.sort(key=lambda c: c.timestamp_seconds)
        per_region_candidates.append((region, kept))

    all_entries: list[dict] = []
    total = sum(len(candidates) for _region, candidates in per_region_candidates)
    id_width = max(3, len(str(total)))

    counter = 0
    for region in regions:
        candidates = next(c for r, c in per_region_candidates if r.region_id == region.region_id)
        for candidate in candidates:
            counter += 1
            candidate_id = f"cand-{counter:0{id_width}d}"

            src_path = Path(candidate.image_path)
            dest_path = candidates_dir / f"{candidate_id}.png"
            if src_path.resolve() != dest_path.resolve():
                shutil.move(str(src_path), str(dest_path))
            candidate.image_path = str(dest_path)

            entry = candidate.model_dump(mode="json")
            entry["id"] = candidate_id
            entry["region_id"] = str(region.region_id)
            all_entries.append(entry)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": _fingerprint_source(video_path),
        "query": query,
        "regions": [region.model_dump(mode="json") for region in regions],
        "candidates": all_entries,
        "selections": [],
    }

    manifest_path = output_dir / CANDIDATES_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest


# ---------------------------------------------------------------------------
# load_handshake (public -- consumed by SS-04)
# ---------------------------------------------------------------------------


def load_handshake(candidates_dir: Path | str) -> dict:
    """Rehydrate and validate ``<candidates_dir>/candidates.json``.

    Raises :class:`CandidatesManifestNotFoundError` if the manifest is
    missing, or :class:`SourceFingerprintMismatchError` if the recorded
    source video no longer matches its fingerprint (size/mtime).
    """
    candidates_dir = Path(candidates_dir)
    manifest_path = candidates_dir / CANDIDATES_FILENAME
    if not manifest_path.exists():
        raise CandidatesManifestNotFoundError(
            f"candidates.json not found: {manifest_path}"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    source = manifest.get("source", {})
    video_path = Path(source.get("path", ""))
    if not _fingerprint_matches(source, video_path):
        raise SourceFingerprintMismatchError(
            f"Source video no longer matches the fingerprint recorded in "
            f"{manifest_path}: {video_path}. Re-run generate to refresh candidates."
        )

    return manifest


# ---------------------------------------------------------------------------
# select_from_handshake
# ---------------------------------------------------------------------------


def top_scored_candidate_ids(manifest: dict) -> list[str]:
    """Pick the deterministic top-scored candidate id for each region.

    Mirrors ``service._process_region``'s "top-ranked surviving candidate"
    selection, recomputed from the persisted manifest since
    :func:`generate_handshake` re-sorts candidates by timestamp (discarding
    rank order) before writing ``candidates.json``.
    """
    cfg = ResearchConfig()
    scorer = FrameScorer()

    by_region: dict[str, list[dict]] = {}
    for entry in manifest.get("candidates", []):
        by_region.setdefault(entry.get("region_id"), []).append(entry)

    selected_ids: list[str] = []
    for region in manifest.get("regions", []):
        region_id = region.get("region_id")
        entries = by_region.get(region_id, [])
        if not entries:
            continue

        id_by_candidate_uuid = {str(entry["candidate_id"]): entry["id"] for entry in entries}
        candidates = [
            FrameCandidate.model_validate({k: v for k, v in entry.items() if k != "id"})
            for entry in entries
        ]
        ranked = scorer.rank(candidates, cfg)
        top = ranked[0] if ranked else candidates[0]
        selected_ids.append(id_by_candidate_uuid[str(top.candidate_id)])

    return selected_ids


def _candidate_by_id(manifest: dict) -> dict[str, dict]:
    return {entry["id"]: entry for entry in manifest["candidates"]}


def select_from_handshake(
    candidates_dir: Path | str,
    candidate_ids: list[str],
    *,
    output_dir: Path | str | None = None,
    obsidian: bool = False,
    keep_candidates: bool = False,
    overwrite: bool = False,
) -> dict:
    """Rehydrate a handshake manifest, persist the selection, and export a package.

    Validates every id in *candidate_ids* against the manifest (raising
    :class:`UnknownCandidateIdsError` listing the valid ids on mismatch), then
    persists the chosen ids into the manifest's ``selections`` array *before*
    building the :class:`ResearchCapture` list handed to :func:`export_package`.
    """
    candidates_dir = Path(candidates_dir)
    manifest = load_handshake(candidates_dir)

    by_id = _candidate_by_id(manifest)
    unknown = [cid for cid in candidate_ids if cid not in by_id]
    if unknown:
        raise UnknownCandidateIdsError(unknown, sorted(by_id.keys()))

    manifest.setdefault("selections", [])
    for cid in candidate_ids:
        if cid not in manifest["selections"]:
            manifest["selections"].append(cid)
    manifest_path = candidates_dir / CANDIDATES_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    source = manifest["source"]
    source_id_by_region = {
        region["region_id"]: region["source_id"] for region in manifest.get("regions", [])
    }

    captures: list[ResearchCapture] = []
    for cid in candidate_ids:
        entry = dict(by_id[cid])
        region_id = entry.get("region_id")
        source_id = source_id_by_region.get(region_id, entry["source_id"])
        candidate_payload = {k: v for k, v in entry.items() if k != "id"}
        candidate = FrameCandidate.model_validate(candidate_payload)
        captures.append(
            ResearchCapture(
                region_id=region_id,
                source_id=source_id,
                candidates=[candidate],
            )
        )

    regions = [ResearchRegion.model_validate(region) for region in manifest.get("regions", [])]

    source_asset = probe_media(Path(source["path"]))
    if regions:
        source_asset.id = regions[0].source_id
    research_manifest = ResearchManifest(
        source=source_asset,
        regions=regions,
        captures=captures,
    )

    resolved_output_dir = (
        Path(output_dir) if output_dir is not None else candidates_dir / "export"
    )
    if resolved_output_dir.exists() and any(resolved_output_dir.iterdir()) and overwrite:
        shutil.rmtree(resolved_output_dir)

    export_package(
        research_manifest,
        resolved_output_dir,
        obsidian=obsidian,
        keep_candidates=keep_candidates,
    )

    return {
        "manifest": research_manifest.model_dump(mode="json"),
        "output_dir": str(resolved_output_dir),
        "selected_ids": list(candidate_ids),
    }
