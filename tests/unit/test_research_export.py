"""Unit tests for the research package exporter."""
from __future__ import annotations

import json

import pytest

from workshop_video_brain.core.models import (
    FrameCandidate,
    MediaAsset,
    ResearchCapture,
    ResearchConfig,
    ResearchManifest,
    ResearchRegion,
)
from workshop_video_brain.edit_mcp.pipelines.visual_research import export as export_mod
from workshop_video_brain.edit_mcp.pipelines.visual_research.export import (
    ExportError,
    export_package,
)


def _write_fake_frame(path, text="fake-jpeg-bytes"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _build_manifest(tmp_path, *, titles=("Intro shot", "Intro shot")):
    source = MediaAsset(path=str(tmp_path / "source.mp4"), relative_path="source.mp4")

    regions = []
    captures = []
    for i, title in enumerate(titles, start=1):
        region = ResearchRegion(
            source_id=source.id,
            start_seconds=float(i),
            end_seconds=float(i) + 2.0,
            label=title,
            reason=f"reason-{i}",
            transcript_excerpt=f"transcript excerpt {i}",
        )
        regions.append(region)

        frame_path = _write_fake_frame(tmp_path / "raw" / f"frame_{i}.jpg", text=f"frame-{i}")
        candidate = FrameCandidate(
            source_id=source.id,
            region_id=region.region_id,
            timestamp_seconds=float(i) + 0.5,
            image_path=str(frame_path),
            extraction_method="exact_timestamp",
        )
        capture = ResearchCapture(
            region_id=region.region_id,
            source_id=source.id,
            candidates=[candidate],
        )
        captures.append(capture)

    return ResearchManifest(source=source, regions=regions, captures=captures)


def test_export_package_writes_manifest_index_and_screenshots(tmp_path):
    manifest = _build_manifest(tmp_path, titles=("Intro shot", "Outro shot"))
    output_dir = tmp_path / "package"

    result = export_package(manifest, output_dir)

    assert result is manifest

    screenshots_dir = output_dir / "screenshots"
    shots = sorted(p.name for p in screenshots_dir.glob("*"))
    assert len(shots) == 2
    assert shots[0].startswith("001-")
    assert shots[1].startswith("002-")

    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["manifest_version"] == "1.0"
    assert len(payload["captures"]) == 2
    assert payload["captures"][0]["image_path"] == f"screenshots/{shots[0]}"
    assert not payload["captures"][0]["image_path"].startswith("/")
    assert payload["source"]["absolute_path"] == str((tmp_path / "source.mp4").resolve())
    assert "configuration" in payload["processing"]

    index_path = output_dir / "index.md"
    assert index_path.exists()
    index_text = index_path.read_text(encoding="utf-8")
    assert f"screenshots/{shots[0]}" in index_text
    assert "Timestamp:" in index_text
    assert "transcript excerpt 1" in index_text
    assert "reason-1" in index_text


def test_export_package_deduplicates_slugs_for_duplicate_titles(tmp_path):
    manifest = _build_manifest(tmp_path, titles=("Same Title", "Same Title"))
    output_dir = tmp_path / "package"

    export_package(manifest, output_dir)

    shots = sorted(p.name for p in (output_dir / "screenshots").glob("*"))
    assert shots[0] == "001-same-title.jpg"
    assert shots[1] == "002-same-title-2.jpg"


def test_export_package_slug_rejects_path_traversal(tmp_path):
    manifest = _build_manifest(tmp_path, titles=("../../etc/hosts", "..\\..\\windows"))
    output_dir = tmp_path / "package"

    export_package(manifest, output_dir)

    shots = sorted(p.name for p in (output_dir / "screenshots").glob("*"))
    for name in shots:
        assert ".." not in name
        assert "/" not in name
        assert "\\" not in name


def test_export_package_manifest_has_no_secret_key_markers(tmp_path):
    manifest = _build_manifest(tmp_path)
    output_dir = tmp_path / "package"

    export_package(manifest, output_dir)

    raw = (output_dir / "manifest.json").read_text(encoding="utf-8").lower()
    for marker in ("api_key", "password", "secret_key", "private_key", "access_key"):
        assert marker not in raw


def test_export_package_refuses_to_overwrite_nonempty_output_dir(tmp_path):
    manifest = _build_manifest(tmp_path)
    output_dir = tmp_path / "package"
    output_dir.mkdir()
    (output_dir / "existing.txt").write_text("hi", encoding="utf-8")

    with pytest.raises(ExportError):
        export_package(manifest, output_dir)


def test_export_package_keep_candidates_copies_extra_frames(tmp_path):
    source = MediaAsset(path=str(tmp_path / "source.mp4"))
    region = ResearchRegion(source_id=source.id, start_seconds=0.0, end_seconds=2.0, label="r1")
    frame_a = _write_fake_frame(tmp_path / "raw" / "a.jpg", "a")
    frame_b = _write_fake_frame(tmp_path / "raw" / "b.jpg", "b")
    candidate_a = FrameCandidate(
        source_id=source.id,
        region_id=region.region_id,
        timestamp_seconds=1.0,
        image_path=str(frame_a),
        metadata={"selected": True},
    )
    candidate_b = FrameCandidate(
        source_id=source.id,
        region_id=region.region_id,
        timestamp_seconds=1.2,
        image_path=str(frame_b),
    )
    capture = ResearchCapture(
        region_id=region.region_id, source_id=source.id, candidates=[candidate_a, candidate_b]
    )
    manifest = ResearchManifest(source=source, regions=[region], captures=[capture])
    output_dir = tmp_path / "package"

    export_package(manifest, output_dir, keep_candidates=True)

    # Selected candidate wins the screenshots/ slot.
    shots = list((output_dir / "screenshots").glob("*"))
    assert len(shots) == 1
    assert shots[0].read_bytes() == b"a"

    candidates_dir = output_dir / "candidates" / "001"
    assert (candidates_dir / "a.jpg").exists()
    assert (candidates_dir / "b.jpg").exists()


def test_export_package_processing_configuration_reflects_passed_config(tmp_path):
    manifest = _build_manifest(tmp_path, titles=("only",))
    output_dir = tmp_path / "package"
    config = ResearchConfig()
    config.export.image_format = "png"

    export_package(manifest, output_dir, config=config)

    payload = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert payload["processing"]["configuration"]["export"]["image_format"] == "png"


def test_export_package_obsidian_routes_through_note_writer(tmp_path, monkeypatch):
    manifest = _build_manifest(tmp_path, titles=("only",))
    output_dir = tmp_path / "package"

    vault_path = tmp_path / "vault"
    templates_dir = tmp_path / "templates" / "obsidian"
    templates_dir.mkdir(parents=True)
    (templates_dir / "visual-research-index.md").write_text(
        "# {{ frontmatter.source }}\n\n{{ sections.captures }}\n", encoding="utf-8"
    )

    monkeypatch.setenv("WVB_VAULT_PATH", str(vault_path))

    from workshop_video_brain.production_brain.notes import writer as writer_mod

    created_paths = []
    original_init = writer_mod.NoteWriter.__init__

    def _patched_init(self, templates_dir_arg=None):
        original_init(self, templates_dir_arg or templates_dir)

    monkeypatch.setattr(writer_mod.NoteWriter, "__init__", _patched_init)

    original_create = writer_mod.NoteWriter.create

    def _tracking_create(self, *args, **kwargs):
        result = original_create(self, *args, **kwargs)
        created_paths.append(result)
        return result

    monkeypatch.setattr(writer_mod.NoteWriter, "create", _tracking_create)

    export_package(manifest, output_dir, obsidian=True)

    assert len(created_paths) == 1
    note_path = created_paths[0]
    assert note_path.exists()
    assert note_path.is_relative_to(vault_path)
    text = note_path.read_text(encoding="utf-8")
    assert "source.mp4" in text


def test_export_package_obsidian_without_vault_raises(tmp_path, monkeypatch):
    manifest = _build_manifest(tmp_path, titles=("only",))
    output_dir = tmp_path / "package"
    monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
    monkeypatch.setattr(export_mod, "_resolve_vault_path", lambda: None)

    with pytest.raises(ExportError):
        export_package(manifest, output_dir, obsidian=True)
