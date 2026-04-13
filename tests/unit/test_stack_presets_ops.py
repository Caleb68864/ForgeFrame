"""Sub-Spec 2 tests for stack_presets operations pipeline (OP-01..16)."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.pipelines import effect_catalog, stack_presets
from workshop_video_brain.edit_mcp.pipelines.stack_presets import (
    ApplyHints,
    Preset,
    PresetEffect,
    apply_preset,
    promote_to_vault,
    render_vault_body,
    save_preset,
    serialize_clip_to_preset,
    validate_against_catalog,
)


# --- helpers (mirrors test_stack_ops_pipeline.py patterns) ----------------


def _filter_xml(
    track: int,
    clip: int,
    mlt_service: str,
    kdenlive_id: str = "",
    extra_properties: dict[str, str] | None = None,
    filter_id: str | None = None,
) -> str:
    fid = f' id="{filter_id}"' if filter_id else ""
    attrs = f'{fid} mlt_service="{mlt_service}" track="{track}" clip_index="{clip}"'
    inner = ""
    if kdenlive_id:
        inner += f'<property name="kdenlive_id">{kdenlive_id}</property>'
    for name, value in (extra_properties or {}).items():
        inner += f'<property name="{name}">{value}</property>'
    return f"<filter{attrs}>{inner}</filter>"


def _make_project(
    filters_per_clip: dict[tuple[int, int], list[tuple[str, str, dict[str, str] | None]]]
    | None = None,
) -> KdenliveProject:
    pl0 = Playlist(
        id="pl0",
        entries=[PlaylistEntry(producer_id="pa", in_point=0, out_point=100)],
    )
    pl1 = Playlist(id="pl1", entries=[])
    pl2 = Playlist(
        id="pl2",
        entries=[
            PlaylistEntry(producer_id="pb", in_point=0, out_point=100),
            PlaylistEntry(producer_id="pc", in_point=0, out_point=100),
        ],
    )
    project = KdenliveProject(playlists=[pl0, pl1, pl2])
    if filters_per_clip:
        for (t, c), flist in filters_per_clip.items():
            for svc, kid, extras in flist:
                project.opaque_elements.append(
                    OpaqueElement(
                        tag="filter",
                        xml_string=_filter_xml(t, c, svc, kid, extras),
                        position_hint="after_tractor",
                    )
                )
    return project


# A known-valid catalog service.
_KNOWN_SERVICE = "frei0r.contrast0r"
_KNOWN_KDENLIVE_ID = "frei0r_contrast0r"


# OP-01 ---------------------------------------------------------------------


def test_module_exports_ops():
    for attr in (
        "serialize_clip_to_preset",
        "validate_against_catalog",
        "apply_preset",
        "promote_to_vault",
        "render_vault_body",
    ):
        assert hasattr(stack_presets, attr), f"missing export: {attr}"


# OP-02 ---------------------------------------------------------------------


def test_serialize_clip_to_preset_field_count():
    project = _make_project(
        {
            (2, 0): [
                ("affine", "transform", None),
                ("avfilter.eq", "eq", None),
                ("volume", "volume", None),
            ]
        }
    )
    p = serialize_clip_to_preset(
        project, (2, 0), name="test", description="d", tags=("a", "b")
    )
    assert p.name == "test"
    assert p.description == "d"
    assert p.tags == ("a", "b")
    assert len(p.effects) == 3
    for e in p.effects:
        assert e.mlt_service
    assert p.source == {"clip_ref": [2, 0]}
    assert p.created_by == "effect_stack_preset"


# OP-03 ---------------------------------------------------------------------


def test_serialize_byte_exact_xml():
    project = _make_project(
        {
            (2, 0): [
                ("affine", "transform", {"rect": "0=0 0 100 100;50=50 50 200 200"}),
                ("volume", "volume", None),
            ]
        }
    )
    from workshop_video_brain.edit_mcp.pipelines import stack_ops

    source_stack = stack_ops.serialize_stack(project, (2, 0))
    preset = serialize_clip_to_preset(project, (2, 0), name="bx")
    assert len(preset.effects) == len(source_stack["effects"])
    for preset_eff, src in zip(preset.effects, source_stack["effects"]):
        assert preset_eff.xml == src["xml"]


# OP-04 ---------------------------------------------------------------------


def test_validate_against_catalog_clean_returns_empty():
    # Sanity: this service is actually in the catalog.
    assert effect_catalog.find_by_service(_KNOWN_SERVICE) is not None
    p = Preset(
        name="clean",
        effects=(
            PresetEffect(
                mlt_service=_KNOWN_SERVICE,
                kdenlive_id=_KNOWN_KDENLIVE_ID,
                xml="<filter/>",
            ),
        ),
    )
    assert validate_against_catalog(p, strict=True) == []


# OP-05 ---------------------------------------------------------------------


def test_validate_unknown_service_strict_raises():
    p = Preset(
        name="bad",
        effects=(PresetEffect(mlt_service="not.real", xml="<filter/>"),),
    )
    with pytest.raises(ValueError) as ei:
        validate_against_catalog(p, strict=True)
    msg = str(ei.value)
    assert "not.real" in msg
    assert "effect_list_common" in msg


# OP-06 ---------------------------------------------------------------------


def test_validate_unknown_service_non_strict_returns_warnings():
    p = Preset(
        name="bad",
        effects=(PresetEffect(mlt_service="not.real", xml="<filter/>"),),
    )
    warnings = validate_against_catalog(p, strict=False)
    assert len(warnings) == 1
    assert "not.real" in warnings[0]


# OP-07 ---------------------------------------------------------------------


def test_apply_preset_uses_hints_default_mode():
    project = _make_project(
        {
            (2, 0): [("affine", "transform", None)],  # 1 existing filter on target
        }
    )
    preset = Preset(
        name="p",
        effects=(
            PresetEffect(
                mlt_service="brightness",
                kdenlive_id="brightness",
                xml=_filter_xml(0, 0, "brightness", "brightness"),
            ),
            PresetEffect(
                mlt_service="avfilter.eq",
                kdenlive_id="eq",
                xml=_filter_xml(0, 0, "avfilter.eq", "eq"),
            ),
        ),
        apply_hints=ApplyHints(stack_order="prepend"),
    )
    result = apply_preset(project, (2, 0), preset)
    assert result["mode"] == "prepend"
    assert result["effects_applied"] == 2
    assert len(patcher.list_effects(project, (2, 0))) == 3
    services = [e["mlt_service"] for e in patcher.list_effects(project, (2, 0))]
    assert services == ["brightness", "avfilter.eq", "affine"]


# OP-08 ---------------------------------------------------------------------


def test_apply_preset_mode_override():
    project = _make_project(
        {
            (2, 0): [("affine", "transform", None)],
        }
    )
    preset = Preset(
        name="p",
        effects=(
            PresetEffect(
                mlt_service="brightness",
                kdenlive_id="brightness",
                xml=_filter_xml(0, 0, "brightness", "brightness"),
            ),
            PresetEffect(
                mlt_service="volume",
                kdenlive_id="volume",
                xml=_filter_xml(0, 0, "volume", "volume"),
            ),
        ),
        apply_hints=ApplyHints(stack_order="append"),
    )
    result = apply_preset(project, (2, 0), preset, mode_override="replace")
    assert result["mode"] == "replace"
    effects = patcher.list_effects(project, (2, 0))
    assert len(effects) == 2
    assert [e["mlt_service"] for e in effects] == ["brightness", "volume"]


# OP-09 ---------------------------------------------------------------------


def test_apply_preset_returns_response_dict_keys():
    project = _make_project({(2, 0): []})
    preset = Preset(
        name="p",
        effects=(
            PresetEffect(
                mlt_service="brightness",
                xml=_filter_xml(0, 0, "brightness"),
            ),
        ),
        apply_hints=ApplyHints(
            blend_mode="screen",
            track_placement="V2",
            required_producers=("audio",),
        ),
    )
    result = apply_preset(project, (2, 0), preset)
    assert set(result.keys()) == {
        "effects_applied",
        "mode",
        "blend_mode_hint",
        "track_placement_hint",
        "required_producers_hint",
    }
    assert isinstance(result["effects_applied"], int)
    assert result["effects_applied"] == 1
    assert result["blend_mode_hint"] == "screen"
    assert result["track_placement_hint"] == "V2"
    assert result["required_producers_hint"] == ("audio",)
    assert result["mode"] == "append"


# OP-10 (critical) ---------------------------------------------------------


def test_apply_preset_preserves_keyframes():
    rect_kf = "0=0 0 100 100;50=120 40 300 200;100=200 50 400 250"
    project = _make_project(
        {
            (2, 0): [("affine", "transform", {"rect": rect_kf})],
            (2, 1): [],  # target clip, empty
        }
    )
    preset = serialize_clip_to_preset(project, (2, 0), name="kf")
    apply_preset(project, (2, 1), preset)
    got = patcher.get_effect_property(project, (2, 1), 0, "rect")
    assert got == rect_kf  # byte-exact

    # Round-trip through save/load too.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        save_preset(preset, workspace_root=ws, scope="workspace")
        from workshop_video_brain.edit_mcp.pipelines.stack_presets import load_preset

        reloaded = load_preset("kf", workspace_root=ws, vault_root=None)
        project2 = _make_project({(2, 1): []})
        apply_preset(project2, (2, 1), reloaded)
        got2 = patcher.get_effect_property(project2, (2, 1), 0, "rect")
        assert got2 == rect_kf


# OP-11 ---------------------------------------------------------------------


def _save_sample_workspace_preset(ws: Path, name: str = "s") -> None:
    preset = Preset(
        name=name,
        description="a preset",
        tags=("x",),
        effects=(
            PresetEffect(
                mlt_service=_KNOWN_SERVICE,
                kdenlive_id=_KNOWN_KDENLIVE_ID,
                xml="<filter/>",
            ),
        ),
    )
    save_preset(preset, workspace_root=ws, scope="workspace")


def test_promote_to_vault_creates_markdown(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    _save_sample_workspace_preset(ws, "s")
    out = promote_to_vault("s", workspace_root=ws, vault_root=vault)
    assert out == vault / "patterns" / "effect-stacks" / "s.md"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: s" in text
    assert "# s" in text


# OP-12 ---------------------------------------------------------------------


def test_promote_to_vault_wikilink_embedded(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    _save_sample_workspace_preset(ws, "s")
    out = promote_to_vault(
        "s",
        workspace_root=ws,
        vault_root=vault,
        source_video_note_path=Path("Videos/My Video.md"),
    )
    text = out.read_text(encoding="utf-8")
    assert "[[My Video]]" in text
    assert "Referenced from" in text


# OP-13 ---------------------------------------------------------------------


def test_promote_to_vault_no_wikilink_when_none(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    _save_sample_workspace_preset(ws, "s")
    out = promote_to_vault("s", workspace_root=ws, vault_root=vault)
    text = out.read_text(encoding="utf-8")
    assert "Referenced from" not in text


# OP-14 ---------------------------------------------------------------------


def test_promote_to_vault_missing_workspace_raises(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    with pytest.raises(FileNotFoundError):
        promote_to_vault("nope", workspace_root=ws, vault_root=vault)


# OP-15 ---------------------------------------------------------------------


def test_render_vault_body_contains_effect_table():
    preset = Preset(
        name="n",
        effects=(
            PresetEffect(mlt_service="svc0", kdenlive_id="id0", xml="<filter/>"),
            PresetEffect(mlt_service="svc1", kdenlive_id="id1", xml="<filter/>"),
        ),
    )
    body = render_vault_body(preset)
    assert "mlt_service" in body
    assert "kdenlive_id" in body
    assert "svc0" in body and "svc1" in body
    assert "id0" in body and "id1" in body
    assert "# n" in body


# OP-16 ---------------------------------------------------------------------


def test_render_vault_body_with_source_note_has_wikilink():
    preset = Preset(
        name="n",
        effects=(
            PresetEffect(mlt_service="svc0", kdenlive_id="id0", xml="<filter/>"),
        ),
    )
    body = render_vault_body(preset, source_video_note_path=Path("Foo/Bar Video.md"))
    assert "[[Bar Video]]" in body
    assert "Referenced from" in body
    # and without it:
    body2 = render_vault_body(preset)
    assert "Referenced from" not in body2
