"""SS-05: registry proof + full handshake E2E for the research_* tool surface.

Registry: a plain server import must expose all ten research_* tools via
pkgutil auto-discovery (zero ``__init__.py`` edits). E2E: drive the real
generate -> select flow with real ffmpeg against the greenscreen fixture and
verify the exported package on disk.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests._testkit import assert_registered, call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.server.tools import research_candidates

FIXTURE = Path("tests/fixtures/media_generated/greenscreen_reporter_720.mp4").resolve()

ALL_RESEARCH_TOOLS = (
    "research_probe_video",
    "research_extract_frame",
    "research_extract_frame_burst",
    "research_detect_scenes",
    "research_transcript_search",
    "research_transcript_context",
    "research_generate_candidates",
    "research_select_candidate",
    "research_run",
    "research_export_package",
)


def test_all_research_tools_registered_via_auto_discovery():
    assert_registered(*ALL_RESEARCH_TOOLS)


@requires_ffmpeg_ffprobe
def test_full_handshake_generate_select_export(tmp_path):
    candidates_dir = tmp_path / "handshake"

    generated = call_tool(
        research_candidates.research_generate_candidates,
        str(FIXTURE),
        str(candidates_dir),
        start_seconds=0.0,
        end_seconds=2.0,
    )
    assert generated["status"] != "error"
    gen_data = generated["data"] if "data" in generated else generated

    manifest_path = candidates_dir / "candidates.json"
    assert manifest_path.exists()
    on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 1
    assert len(on_disk["candidates"]) >= 1
    assert on_disk["candidates"][0]["id"] == gen_data["candidates"][0]["id"]

    chosen = on_disk["candidates"][0]

    selected = call_tool(
        research_candidates.research_select_candidate,
        str(candidates_dir),
        [chosen["id"]],
    )
    assert selected["status"] != "error"
    sel_data = selected["data"] if "data" in selected else selected

    export_dir = Path(sel_data["output_dir"])
    assert (export_dir / "index.md").exists()

    export_manifest = json.loads(
        (export_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert export_manifest["captures"][0]["timestamp_seconds"] == (
        chosen["timestamp_seconds"]
    )

    screenshots = sorted((export_dir / "screenshots").glob("*.png"))
    assert screenshots, "exported package has no screenshots/*.png"
    assert screenshots[0].stat().st_size > 0

    from PIL import Image

    with Image.open(screenshots[0]) as img:
        width, height = img.size
    assert (width, height) == (chosen["width"], chosen["height"])

    reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert chosen["id"] in reloaded["selections"]
