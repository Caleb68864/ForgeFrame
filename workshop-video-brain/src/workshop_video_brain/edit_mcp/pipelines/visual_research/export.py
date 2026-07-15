"""Research package export: selected frames + manifest.json + index.md.

Copies the selected candidate frame from each :class:`ResearchCapture` into
``output_dir/screenshots/NNN-slug.ext``, writes a secret-free ``manifest.json``
(versioned) and a human-readable ``index.md`` alongside it, and optionally
routes an Obsidian note through :class:`~workshop_video_brain.production_brain.notes.writer.NoteWriter`
(no parallel markdown/frontmatter implementation lives here).
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from workshop_video_brain.core.models.visual_research import (
    FrameCandidate,
    ResearchCapture,
    ResearchConfig,
    ResearchManifest,
    ResearchRegion,
)
from workshop_video_brain.core.utils.naming import slugify

MANIFEST_VERSION = "1.0"

_OBSIDIAN_FOLDER = "Visual Research"
_OBSIDIAN_TEMPLATE = "visual-research-index.md"

# Substrings that must never appear (case-insensitively) anywhere in a
# written manifest.json -- a cheap belt-and-braces scan on top of the fact
# that ResearchConfig itself carries no credential-shaped fields.
_SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "access_key",
    "secret_key",
    "client_secret",
    "password",
    "passwd",
    "private_key",
    "bearer ",
)


class ExportError(RuntimeError):
    """Raised when a research package export cannot proceed safely."""


def export_package(
    manifest: ResearchManifest,
    output_dir: Path | str,
    obsidian: bool = False,
    keep_candidates: bool = False,
    config: ResearchConfig | None = None,
) -> ResearchManifest:
    """Write a research package (screenshots + manifest.json + index.md) for *manifest*.

    Args:
        manifest: The research manifest whose captures should be exported.
        output_dir: Destination directory. Must not already exist with
            content in it -- callers must remove/rename an existing package
            explicitly rather than have it silently overwritten.
        obsidian: When True, also write an Obsidian note via
            :class:`NoteWriter` (vault resolved from ``WVB_VAULT_PATH`` or
            ``~/.forgeframe/config.json``).
        keep_candidates: When True, also copy every non-selected candidate
            image for each capture into ``candidates/<index>/``.
        config: The :class:`ResearchConfig` used to produce *manifest*,
            recorded (sanitized) as ``processing.configuration`` in
            ``manifest.json``. Defaults to ``ResearchConfig()`` when omitted.

    Returns:
        The *manifest* passed in, unmodified.
    """
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ExportError(
            f"Output directory already exists and is not empty: {output_dir}. "
            "Remove or rename it before exporting -- export_package never "
            "silently overwrites an existing package."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = output_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    cfg = config or ResearchConfig()
    region_by_id = {region.region_id: region for region in manifest.regions}

    seen_slugs: set[str] = set()
    entries: list[dict] = []

    for index, capture in enumerate(manifest.captures, start=1):
        candidate = _select_candidate(capture)
        if candidate is None:
            continue

        region = region_by_id.get(capture.region_id)
        title = _capture_title(candidate, region, index)
        slug = _unique_slug(title, seen_slugs)
        ext = _frame_extension(candidate, cfg)
        filename = f"{index:03d}-{slug}.{ext}"
        dest_path = screenshots_dir / filename

        src_path = Path(candidate.image_path)
        if not src_path.exists():
            raise ExportError(f"Candidate image not found: {src_path}")
        shutil.copy2(src_path, dest_path)

        if keep_candidates:
            _copy_candidates(capture, output_dir / "candidates" / f"{index:03d}")

        entries.append(
            {
                "index": index,
                "capture_id": str(capture.capture_id),
                "region_id": str(capture.region_id) if capture.region_id else None,
                "candidate_id": str(candidate.candidate_id),
                "image_path": f"screenshots/{filename}",
                "timestamp_seconds": candidate.timestamp_seconds,
                "extraction_method": candidate.extraction_method,
                "metrics": candidate.metrics.model_dump(mode="json"),
                "label": region.label if region else "",
                "reason": region.reason if region else "",
                "transcript_excerpt": region.transcript_excerpt if region else "",
            }
        )

    manifest_payload = {
        "manifest_version": MANIFEST_VERSION,
        "manifest_id": str(manifest.manifest_id),
        "created_at": manifest.created_at.isoformat(),
        "source": {
            "absolute_path": str(Path(manifest.source.path).resolve()),
            "relative_path": manifest.source.relative_path,
            "media_type": manifest.source.media_type,
            "duration_seconds": manifest.source.duration_seconds or manifest.source.duration,
        },
        "captures": entries,
        "processing": {
            "configuration": cfg.model_dump(mode="json"),
        },
    }
    _assert_no_secrets(manifest_payload)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    index_path = output_dir / "index.md"
    index_path.write_text(_render_index(manifest, entries), encoding="utf-8")

    if obsidian:
        _write_obsidian_note(manifest, entries, output_dir)

    return manifest


# ---------------------------------------------------------------------------
# Selection / naming
# ---------------------------------------------------------------------------


def _select_candidate(capture: ResearchCapture) -> FrameCandidate | None:
    """Pick the representative candidate for a capture.

    Prefers a candidate explicitly flagged ``metadata["selected"] = True``
    (set by an upstream scoring/dedup stage); falls back to the first
    candidate in extraction order.
    """
    if not capture.candidates:
        return None
    for candidate in capture.candidates:
        if candidate.metadata.get("selected"):
            return candidate
    return capture.candidates[0]


def _capture_title(candidate: FrameCandidate, region: ResearchRegion | None, index: int) -> str:
    if candidate.metadata.get("title"):
        return str(candidate.metadata["title"])
    if region is not None and region.label:
        return region.label
    if region is not None and region.reason:
        return region.reason
    return f"capture-{index}"


def _unique_slug(title: str, seen: set[str]) -> str:
    """Slugify *title*, de-colliding against *seen* (mutated in place).

    ``slugify`` already strips everything but word characters/hyphens, so
    path-traversal sequences (``../``, ``..\\``, absolute prefixes) cannot
    survive into the returned slug.
    """
    base = slugify(title) or "frame"
    slug = base
    suffix = 2
    while slug in seen:
        slug = f"{base}-{suffix}"
        suffix += 1
    seen.add(slug)
    return slug


def _frame_extension(candidate: FrameCandidate, config: ResearchConfig) -> str:
    ext = Path(candidate.image_path).suffix.lstrip(".")
    return ext or config.export.image_format


def _copy_candidates(capture: ResearchCapture, dest_dir: Path) -> None:
    for candidate in capture.candidates:
        src_path = Path(candidate.image_path)
        if not src_path.exists():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_dir / src_path.name)


# ---------------------------------------------------------------------------
# Secret scan
# ---------------------------------------------------------------------------


def _assert_no_secrets(payload: dict) -> None:
    haystack = json.dumps(payload).lower()
    for marker in _SECRET_KEY_MARKERS:
        if marker in haystack:
            raise ExportError(
                f"Refusing to write manifest.json: potential secret material found ({marker!r})"
            )


# ---------------------------------------------------------------------------
# index.md rendering
# ---------------------------------------------------------------------------


def _render_index(manifest: ResearchManifest, entries: list[dict]) -> str:
    lines = [
        "# Visual Research Package",
        "",
        f"Source: `{manifest.source.path}`",
        f"Generated: {manifest.created_at.isoformat()}",
        f"Frames: {len(entries)}",
        "",
    ]
    for entry in entries:
        title = entry["label"] or entry["reason"] or f"Capture {entry['index']}"
        lines.append(f"## {entry['index']:03d} — {title}")
        lines.append("")
        lines.append(f"![{title}]({entry['image_path']})")
        lines.append("")
        lines.append(f"- Timestamp: {entry['timestamp_seconds']:.2f}s")
        if entry["transcript_excerpt"]:
            lines.append(f"- Transcript: {entry['transcript_excerpt']}")
        if entry["reason"]:
            lines.append(f"- Selection reason: {entry['reason']}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Obsidian output (routed through production_brain.notes.writer.NoteWriter)
# ---------------------------------------------------------------------------


def _resolve_vault_path() -> Path | None:
    """Resolve vault path from ``WVB_VAULT_PATH`` env var or the user config file."""
    vault = os.environ.get("WVB_VAULT_PATH")
    if vault:
        return Path(vault).expanduser()
    config_path = Path.home() / ".forgeframe" / "config.json"
    if config_path.exists():
        try:
            raw_config = json.loads(config_path.read_text(encoding="utf-8"))
            if "vault_path" in raw_config:
                return Path(raw_config["vault_path"]).expanduser()
        except Exception:
            pass
    return None


def _write_obsidian_note(
    manifest: ResearchManifest, entries: list[dict], output_dir: Path
) -> Path:
    from workshop_video_brain.production_brain.notes.writer import NoteWriter

    vault_path = _resolve_vault_path()
    if vault_path is None:
        raise ExportError(
            "Obsidian export requested but no vault is configured. "
            "Set WVB_VAULT_PATH or run `wvb init`."
        )

    source_stem = Path(manifest.source.relative_path or manifest.source.path).stem
    short_id = str(manifest.manifest_id)[:8]
    filename = f"{slugify(source_stem) or 'research'}-{short_id}.md"

    note_dir = Path(vault_path) / _OBSIDIAN_FOLDER
    captures_section = _render_obsidian_captures(entries, output_dir, note_dir)

    frontmatter = {
        "type": "visual-research-package",
        "manifest_id": str(manifest.manifest_id),
        "source": manifest.source.relative_path or manifest.source.path,
        "capture_count": len(entries),
        "created_at": manifest.created_at.isoformat(),
    }

    writer = NoteWriter()
    return writer.create(
        vault_path=vault_path,
        folder=_OBSIDIAN_FOLDER,
        filename=filename,
        template_name=_OBSIDIAN_TEMPLATE,
        frontmatter=frontmatter,
        sections={"captures": captures_section},
    )


def _render_obsidian_captures(entries: list[dict], output_dir: Path, note_dir: Path) -> str:
    lines = []
    for entry in entries:
        title = entry["label"] or entry["reason"] or f"Capture {entry['index']}"
        image_abs = output_dir / entry["image_path"]
        try:
            image_ref = os.path.relpath(image_abs, start=note_dir).replace(os.sep, "/")
        except ValueError:
            # Different drives on Windows -- relpath can't cross them.
            image_ref = str(image_abs).replace(os.sep, "/")
        lines.append(f"### {entry['index']:03d} — {title}")
        lines.append("")
        lines.append(f"![{title}]({image_ref})")
        lines.append("")
        lines.append(f"- Timestamp: {entry['timestamp_seconds']:.2f}s")
        if entry["transcript_excerpt"]:
            lines.append(f"- Transcript: {entry['transcript_excerpt']}")
        if entry["reason"]:
            lines.append(f"- Selection reason: {entry['reason']}")
        lines.append("")
    return "\n".join(lines)
