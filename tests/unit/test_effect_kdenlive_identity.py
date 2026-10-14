"""Kdenlive registry ids are normalized on every clip-filter write path."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from tests._testkit import call_tool, sequence_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_ids import (
    EFFECT_IDS,
    KNOWN_EFFECT_IDS,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_identity import (
    normalize_effect_id,
)
from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import (
    emit_effect_ids_module,
    parse_effect_identity,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect


def _entry_filters(path: Path) -> list[ET.Element]:
    root = ET.parse(path).getroot()
    return [filt for entry in root.iter("entry") for filt in entry.findall("filter")]


def _all_filter_props(path: Path) -> list[dict[str, str]]:
    return [
        {
            prop.get("name", ""): prop.text or ""
            for prop in filt.findall("property")
        }
        for filt in ET.parse(path).getroot().iter("filter")
    ]


def _props(filt: ET.Element) -> dict[str, str]:
    return {
        prop.get("name", ""): prop.text or ""
        for prop in filt.findall("property")
    }


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    from workshop_video_brain.edit_mcp.server.tools import timeline_project, workspace_media

    media = tmp_path / "media"
    media.mkdir()
    created = call_tool(
        workspace_media.workspace_create,
        title="Effect identity",
        media_root=str(media),
    )
    assert created["status"] == "success", created
    root = Path(created["data"]["workspace_root"])
    result = call_tool(timeline_project.project_create_working_copy, str(root))
    assert result["status"] == "success", result
    project_path = max(
        (root / "projects" / "working_copies").glob("*.kdenlive"),
        key=lambda path: path.stat().st_mtime,
    )
    serialize_project(sequence_project(colors=["red"]), project_path)
    return root, project_path


def test_normalize_effect_id_rules():
    assert normalize_effect_id("avfilter.gblur") == "avfilter.gblur"
    assert normalize_effect_id("frei0r.cartoon", "frei0r_cartoon") == "frei0r.cartoon"
    assert normalize_effect_id("hslprimaries", "hsl_primaries") == "hslprimaries"
    assert normalize_effect_id("affine", "transform", ["transition.rect"]) == "pan_zoom"
    assert normalize_effect_id("foo.bar", "") is None


def test_generated_data_has_service_registry_id():
    assert EFFECT_IDS["avfilter_gblur"][0] == "avfilter.gblur"
    assert len(EFFECT_IDS) == 433


def test_identity_parser_handles_nested_effect_without_parsing_parameters(tmp_path):
    path = tmp_path / "grouped.xml"
    path.write_text(
        '<group xmlns="urn:kdenlive"><effect id="actual.id" tag="mlt.service">'
        '<parameter type="new-type" name="future"/></effect></group>',
        encoding="utf-8",
    )
    row = parse_effect_identity(path)
    assert row == ("grouped", "actual.id", "mlt.service")
    module = emit_effect_ids_module([row], "26.08.2")
    assert "Source: Kdenlive 26.08.2" in module
    assert "'grouped': ('actual.id', 'mlt.service')" in module


def test_effect_add_serializes_registry_identity_and_escapes_values(tmp_path):
    path = tmp_path / "effect.kdenlive"
    project = apply_effect(
        sequence_project(colors=["red"]),
        0,
        0,
        "avfilter.gblur",
        {"av.sigma": "12", "note": "fish & <chips>"},
    )
    serialize_project(project, path)
    filters = _entry_filters(path)
    props = _props(filters[0])
    assert props["mlt_service"] == "avfilter.gblur"
    assert props["kdenlive_id"] == "avfilter.gblur"
    assert props["note"] == "fish & <chips>"


def test_effect_add_unknown_service_reports_warning_and_omits_id(tmp_path):
    from workshop_video_brain.edit_mcp.server.tools import effects_catalog

    root, project_path = _workspace(tmp_path)
    result = call_tool(
        effects_catalog.effect_add,
        str(root),
        str(project_path),
        0,
        0,
        "foo.bar",
    )
    assert result["status"] == "success", result
    assert result["data"]["kdenlive_id"] is None
    assert result["data"]["warning"] == (
        "'foo.bar' is not a Kdenlive effect: melt renders it, Kdenlive will drop it."
    )
    filt = _entry_filters(project_path)[0]
    assert "kdenlive_id" not in _props(filt)


def test_cartoon_wrapper_resolves_catalog_stem(tmp_path):
    from workshop_video_brain.edit_mcp.pipelines.effect_wrappers.effect_frei0r_cartoon import (
        effect_frei0r_cartoon,
    )

    root, project_path = _workspace(tmp_path)
    result = call_tool(
        effect_frei0r_cartoon,
        str(root),
        str(project_path),
        0,
        0,
    )
    assert result["status"] == "success", result
    assert any(
        props.get("kdenlive_id") == "frei0r.cartoon"
        for props in _all_filter_props(project_path)
    )


def test_serializer_repairs_or_removes_existing_unknown_ids(tmp_path):
    from workshop_video_brain.core.models.kdenlive import OpaqueElement

    project = sequence_project(colors=["red"])
    for kid, service in (("avfilter_gblur", "avfilter.gblur"), ("bogus_id", "unknown.fx")):
        project.opaque_elements.append(
            OpaqueElement(
                tag="filter",
                xml_string=(
                    '<filter track="0" clip_index="0">'
                    f'<property name="mlt_service">{service}</property>'
                    f'<property name="kdenlive_id">{kid}</property>'
                    '</filter>'
                ),
                position_hint="after_tractor",
            )
        )
    path = tmp_path / "safety.kdenlive"
    serialize_project(project, path)
    filters = _entry_filters(path)
    assert _props(filters[0])["kdenlive_id"] == "avfilter.gblur"
    assert "kdenlive_id" not in _props(filters[1])


def test_all_tool_effect_outputs_use_registered_ids(tmp_path):
    from workshop_video_brain.edit_mcp.pipelines.effect_wrappers.effect_frei0r_cartoon import (
        effect_frei0r_cartoon,
    )
    from workshop_video_brain.edit_mcp.server.bundles import pan_zoom
    from workshop_video_brain.edit_mcp.server.tools import effects_color, effects_catalog

    root, project_path = _workspace(tmp_path)
    calls = [
        call_tool(effects_catalog.effect_add, str(root), str(project_path), 0, 0,
                  "avfilter.gblur", '{"av.sigma":"12"}'),
        call_tool(pan_zoom.effect_pan_zoom, str(project_path), 0, 0,
                  start_rect=[0, 0, 1000, 1080], end_rect=[500, 0, 1000, 1080]),
        call_tool(effect_frei0r_cartoon,
                  str(root), str(project_path), 0, 0),
        call_tool(effects_color.effect_color_wash, str(root), str(project_path), 0, 0),
    ]
    assert all(result["status"] == "success" for result in calls), calls
    for filt in _entry_filters(project_path):
        kid = _props(filt).get("kdenlive_id")
        assert kid is None or kid in KNOWN_EFFECT_IDS
