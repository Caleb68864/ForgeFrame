"""Unit tests for the two-call agent handshake pipeline (generate/select)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests._testkit import requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.pipelines.visual_research.handshake import (
    CandidatesManifestNotFoundError,
    OutputDirNotEmptyError,
    SourceFingerprintMismatchError,
    UnknownCandidateIdsError,
    generate_handshake,
    load_handshake,
    select_from_handshake,
)

FIXTURE = Path("tests/fixtures/media_generated/greenscreen_reporter_720.mp4").resolve()

pytestmark = requires_ffmpeg_ffprobe


def test_generate_handshake_writes_candidate_pngs_and_valid_manifest(tmp_path):
    output_dir = tmp_path / "run"

    manifest = generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
    )

    assert manifest["schema_version"] == 1
    assert manifest["source"]["path"] == str(FIXTURE)
    assert manifest["selections"] == []
    assert len(manifest["candidates"]) >= 1

    ids = [c["id"] for c in manifest["candidates"]]
    assert len(ids) == len(set(ids))
    assert all(cid.startswith("cand-") for cid in ids)

    for candidate in manifest["candidates"]:
        assert Path(candidate["image_path"]).exists()
        assert Path(candidate["image_path"]).suffix == ".png"

    manifest_path = output_dir / "candidates.json"
    assert manifest_path.exists()
    on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert on_disk == manifest


def test_generate_handshake_ids_stable_across_two_runs(tmp_path):
    manifest_1 = generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=tmp_path / "run1"
    )
    manifest_2 = generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=tmp_path / "run2"
    )

    ids_1 = [c["id"] for c in manifest_1["candidates"]]
    ids_2 = [c["id"] for c in manifest_2["candidates"]]
    assert ids_1 == ids_2


def test_generate_handshake_rejects_nonempty_output_dir_without_overwrite(tmp_path):
    output_dir = tmp_path / "run"
    generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
    )

    with pytest.raises(OutputDirNotEmptyError):
        generate_handshake(
            FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
        )


def test_generate_handshake_overwrite_regenerates_existing_package(tmp_path):
    output_dir = tmp_path / "run"
    generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
    )

    manifest = generate_handshake(
        FIXTURE,
        start_seconds=0.0,
        end_seconds=2.0,
        output_dir=output_dir,
        overwrite=True,
    )
    assert (output_dir / "candidates.json").exists()
    assert len(manifest["candidates"]) >= 1


def test_select_from_handshake_exports_package_with_chosen_timestamp(tmp_path):
    output_dir = tmp_path / "run"
    manifest = generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
    )
    chosen = manifest["candidates"][0]

    result = select_from_handshake(output_dir, [chosen["id"]])

    export_dir = Path(result["output_dir"])
    manifest_path = export_dir / "manifest.json"
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(payload["captures"]) == 1
    assert payload["captures"][0]["timestamp_seconds"] == pytest.approx(
        chosen["timestamp_seconds"]
    )


def test_select_from_handshake_persists_selection_into_candidates_json(tmp_path):
    output_dir = tmp_path / "run"
    manifest = generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
    )
    chosen_id = manifest["candidates"][0]["id"]

    select_from_handshake(output_dir, [chosen_id])

    on_disk = json.loads((output_dir / "candidates.json").read_text(encoding="utf-8"))
    assert chosen_id in on_disk["selections"]


def test_select_from_handshake_unknown_id_lists_valid_ids(tmp_path):
    output_dir = tmp_path / "run"
    manifest = generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
    )
    valid_ids = {c["id"] for c in manifest["candidates"]}

    with pytest.raises(UnknownCandidateIdsError) as exc_info:
        select_from_handshake(output_dir, ["cand-999"])

    assert exc_info.value.unknown_ids == ["cand-999"]
    assert set(exc_info.value.valid_ids) == valid_ids


def test_select_from_handshake_missing_candidates_json_names_expected_path(tmp_path):
    missing_dir = tmp_path / "does-not-exist"

    with pytest.raises(CandidatesManifestNotFoundError) as exc_info:
        select_from_handshake(missing_dir, ["cand-001"])

    assert str(missing_dir / "candidates.json") in str(exc_info.value)


def test_select_from_handshake_detects_source_fingerprint_mismatch(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(FIXTURE.read_bytes())

    output_dir = tmp_path / "run"
    manifest = generate_handshake(
        source, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
    )
    chosen_id = manifest["candidates"][0]["id"]

    # Replace the source file's bytes/mtime after generation.
    source.write_bytes(FIXTURE.read_bytes() + b"\x00")
    stat = source.stat()
    os.utime(source, (stat.st_atime, stat.st_mtime + 1000))

    with pytest.raises(SourceFingerprintMismatchError):
        select_from_handshake(output_dir, [chosen_id])


def test_load_handshake_rehydrates_manifest(tmp_path):
    output_dir = tmp_path / "run"
    manifest = generate_handshake(
        FIXTURE, start_seconds=0.0, end_seconds=2.0, output_dir=output_dir
    )

    rehydrated = load_handshake(output_dir)

    assert rehydrated["schema_version"] == manifest["schema_version"]
    assert rehydrated["candidates"] == manifest["candidates"]


def test_generate_handshake_overwrite_never_honored_under_protected_paths(tmp_path):
    protected = tmp_path / "projects" / "source" / "handshake_out"
    protected.mkdir(parents=True)
    (protected / "candidates.json").write_text("{}", encoding="utf-8")

    with pytest.raises(OutputDirNotEmptyError):
        generate_handshake(
            FIXTURE,
            start_seconds=0.0,
            end_seconds=1.0,
            output_dir=protected,
            overwrite=True,
        )
    assert (protected / "candidates.json").exists()
