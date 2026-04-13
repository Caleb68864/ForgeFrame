"""Sub-Spec 1 IO tests for stack presets (IO-01..14)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from workshop_video_brain.edit_mcp.pipelines import stack_presets
from workshop_video_brain.edit_mcp.pipelines.stack_presets import (
    ApplyHints,
    Preset,
    PresetEffect,
    list_presets,
    load_preset,
    resolve_vault_root,
    save_preset,
)


_XML_SAMPLE = (
    '<filter id="filter0" in="0" out="100">\n'
    '  <property name="mlt_service">brightness</property>\n'
    '  <property name="level">1=0;50=1.5;100=1</property>\n'
    "</filter>"
)


def _make_preset(name: str = "demo", n_effects: int = 1, **kw) -> Preset:
    effects = tuple(
        PresetEffect(
            mlt_service=f"svc{i}",
            kdenlive_id=f"id{i}",
            xml=_XML_SAMPLE,
        )
        for i in range(n_effects)
    )
    return Preset(
        name=name,
        created_at=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
        created_by="tester",
        effects=effects,
        **kw,
    )


def test_module_exports():
    for attr in (
        "Preset",
        "PresetEffect",
        "ApplyHints",
        "save_preset",
        "load_preset",
        "list_presets",
        "resolve_vault_root",
    ):
        assert hasattr(stack_presets, attr), f"missing export: {attr}"


def test_preset_model_field_defaults():
    p = Preset(name="x", effects=())
    assert p.version == 1
    assert p.tags == ()
    assert p.description == ""
    assert p.source is None
    assert isinstance(p.apply_hints, ApplyHints)
    assert p.apply_hints.stack_order == "append"


def test_apply_hints_literal_validation():
    with pytest.raises(ValidationError):
        ApplyHints(stack_order="bogus")


def test_extra_fields_ignored():
    doc = """
name: x
effects: []
foo: bar
"""
    data = yaml.safe_load(doc)
    p = Preset.model_validate(data)
    assert p.name == "x"


def test_save_then_load_workspace_round_trip(tmp_path: Path):
    p = _make_preset("rt", n_effects=1, tags=("a", "b"), description="desc")
    path = save_preset(p, workspace_root=tmp_path, scope="workspace")
    assert path.exists()
    reloaded = load_preset("rt", workspace_root=tmp_path, vault_root=None)
    assert reloaded.model_dump(mode="json") == p.model_dump(mode="json")
    assert reloaded.effects[0].xml == _XML_SAMPLE


def test_save_creates_stacks_dir(tmp_path: Path):
    assert not (tmp_path / "stacks").exists()
    p = _make_preset()
    save_preset(p, workspace_root=tmp_path, scope="workspace")
    assert (tmp_path / "stacks").is_dir()


def test_save_workspace_path_is_correct(tmp_path: Path):
    p = _make_preset("foo")
    path = save_preset(p, workspace_root=tmp_path, scope="workspace")
    assert path == tmp_path / "stacks" / "foo.yaml"


def test_save_vault_writes_markdown_with_frontmatter(tmp_path: Path):
    p = _make_preset("vname")
    path = save_preset(
        p,
        vault_root=tmp_path,
        scope="vault",
        body_renderer=lambda preset: "BODY-MARKER",
    )
    assert path == tmp_path / "patterns" / "effect-stacks" / "vname.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: vname" in text
    assert "\n---\n" in text
    assert "BODY-MARKER" in text


def test_load_prefers_workspace_over_vault(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    p_ws = _make_preset("shared", description="from-ws")
    p_vault = _make_preset("shared", description="from-vault")
    save_preset(p_ws, workspace_root=ws, scope="workspace")
    save_preset(p_vault, vault_root=vault, scope="vault")
    got = load_preset("shared", workspace_root=ws, vault_root=vault)
    assert got.description == "from-ws"


def test_load_falls_back_to_vault(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    p = _make_preset("only-vault", description="v")
    save_preset(p, vault_root=vault, scope="vault")
    got = load_preset("only-vault", workspace_root=ws, vault_root=vault)
    assert got.description == "v"


def test_load_missing_raises_with_both_paths(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    with pytest.raises(FileNotFoundError) as ei:
        load_preset("nope", workspace_root=ws, vault_root=vault)
    msg = str(ei.value)
    assert "stacks/nope.yaml" in msg
    assert "patterns/effect-stacks/nope.md" in msg


def test_load_vault_markdown_parses_frontmatter(tmp_path: Path):
    vault = tmp_path
    md_dir = vault / "patterns" / "effect-stacks"
    md_dir.mkdir(parents=True)
    fm = {
        "name": "handwritten",
        "version": 1,
        "created_at": "2026-04-13T12:00:00+00:00",
        "updated_at": "2026-04-13T12:00:00+00:00",
        "created_by": "hand",
        "tags": ["x"],
        "description": "hand-written",
        "effects": [
            {"mlt_service": "svc0", "kdenlive_id": "", "xml": "<filter/>"}
        ],
    }
    text = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n# body\n"
    (md_dir / "handwritten.md").write_text(text, encoding="utf-8")
    got = load_preset("handwritten", workspace_root=None, vault_root=vault)
    assert got.name == "handwritten"
    assert got.description == "hand-written"
    assert got.effects[0].mlt_service == "svc0"


def test_list_enumerates_both_tiers(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    for i in range(2):
        save_preset(_make_preset(f"w{i}"), workspace_root=ws, scope="workspace")
    for i in range(3):
        save_preset(_make_preset(f"v{i}"), vault_root=vault, scope="vault")
    result = list_presets(ws, vault, scope="all")
    assert len(result["presets"]) == 5
    assert result["skipped"] == []
    for entry in result["presets"]:
        assert set(entry.keys()) == {
            "name",
            "scope",
            "tags",
            "effect_count",
            "description",
            "path",
        }


def test_list_workspace_scope_only(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    for i in range(2):
        save_preset(_make_preset(f"w{i}"), workspace_root=ws, scope="workspace")
    for i in range(3):
        save_preset(_make_preset(f"v{i}"), vault_root=vault, scope="vault")
    result = list_presets(ws, vault, scope="workspace")
    assert len(result["presets"]) == 2
    assert all(e["scope"] == "workspace" for e in result["presets"])


def test_list_skips_malformed_files(tmp_path: Path):
    ws = tmp_path / "ws"
    (ws / "stacks").mkdir(parents=True)
    save_preset(_make_preset("good"), workspace_root=ws, scope="workspace")
    (ws / "stacks" / "bad.yaml").write_text("{{{not yaml", encoding="utf-8")
    result = list_presets(ws, None, scope="workspace")
    assert len(result["presets"]) == 1
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["path"].endswith("bad.yaml")
    assert "error" in result["skipped"][0]


def test_list_empty_returns_empty_lists(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    result = list_presets(ws, vault, scope="all")
    assert result == {"presets": [], "skipped": []}


def test_list_workspace_and_vault_share_name(tmp_path: Path):
    ws = tmp_path / "ws"
    vault = tmp_path / "vault"
    ws.mkdir()
    vault.mkdir()
    save_preset(_make_preset("shared"), workspace_root=ws, scope="workspace")
    save_preset(_make_preset("shared"), vault_root=vault, scope="vault")
    result = list_presets(ws, vault, scope="all")
    scopes = sorted(e["scope"] for e in result["presets"])
    assert scopes == ["vault", "workspace"]


def test_resolve_vault_root_from_project_json(tmp_path: Path):
    target = tmp_path / "v"
    target.mkdir()
    pj = tmp_path / "forge-project.json"
    pj.write_text(json.dumps({"vault_root": str(target)}), encoding="utf-8")
    missing = tmp_path / "missing.json"
    got = resolve_vault_root(project_json_path=pj, forge_config_path=missing)
    assert got == target.resolve()


def test_resolve_vault_root_from_personal_vault(tmp_path: Path):
    pj = tmp_path / "forge-project.json"
    pj.write_text(json.dumps({}), encoding="utf-8")
    target = tmp_path / "p"
    target.mkdir()
    fc = tmp_path / "forge.json"
    fc.write_text(json.dumps({"personal_vault": str(target)}), encoding="utf-8")
    got = resolve_vault_root(project_json_path=pj, forge_config_path=fc)
    assert got == target.resolve()


def test_resolve_vault_root_returns_none_when_neither_set(tmp_path: Path):
    got = resolve_vault_root(
        project_json_path=tmp_path / "missing.json",
        forge_config_path=tmp_path / "also-missing.json",
    )
    assert got is None


def test_resolve_vault_root_expands_user_and_relative(tmp_path: Path):
    pj = tmp_path / "forge-project.json"
    pj.write_text(json.dumps({"vault_root": "~/foo"}), encoding="utf-8")
    got = resolve_vault_root(project_json_path=pj, forge_config_path=tmp_path / "nope.json")
    assert got is not None
    assert got.is_absolute()
    assert "foo" in str(got)
    assert "~" not in str(got)


def test_save_slugifies_path_separators(tmp_path: Path):
    p = _make_preset("my/preset")
    path = save_preset(p, workspace_root=tmp_path, scope="workspace")
    assert path.name == "my-preset.yaml"
    assert path.exists()
