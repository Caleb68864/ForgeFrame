"""Integration tests for Stack Presets MCP tools.

Covers ``effect_stack_preset``, ``effect_stack_apply``, ``effect_stack_promote``,
and ``effect_stack_list``, registered in
``workshop_video_brain.edit_mcp.server.tools`` as part of Sub-Spec 3 of the
Stack Presets feature.
"""
from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools
from workshop_video_brain.edit_mcp.server.tools import (
    effect_add,
    effect_keyframe_set_rect,
    effect_stack_apply,
    effect_stack_list,
    effect_stack_preset,
    effect_stack_promote,
    workspace_create,
)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

SRC = (2, 0)
DST = (1, 0)


def _add_second_clip(project_path: Path) -> None:
    tree = ET.parse(project_path)
    root = tree.getroot()
    playlist1 = None
    for pl in root.findall("playlist"):
        if pl.get("id") == "playlist1":
            playlist1 = pl
            break
    assert playlist1 is not None
    entry = ET.SubElement(playlist1, "entry")
    entry.set("producer", "producer0")
    entry.set("in", "0")
    entry.set("out", "299")
    tree.write(project_path, encoding="utf-8", xml_declaration=True)


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Stack Presets Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    _add_second_clip(dest)
    return ws_root, project_name


def _reparse(ws: Path, pf: str):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    return parse_project(ws / pf)


def _effect_count(project, clip_ref) -> int:
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    return len(patcher.list_effects(project, clip_ref))


@pytest.fixture(autouse=True)
def _isolate_vault(monkeypatch, tmp_path):
    """Default: no vault configured. Tests opt-in by patching _resolve_vault_root_for_tools."""
    monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", lambda: None)


# ---------------------------------------------------------------------------
# MCP-01: registration / importability
# ---------------------------------------------------------------------------


def test_tools_importable_and_callable():
    for name in (
        "effect_stack_preset",
        "effect_stack_apply",
        "effect_stack_promote",
        "effect_stack_list",
    ):
        assert callable(getattr(tools, name)), f"{name} missing"


# ---------------------------------------------------------------------------
# MCP-02..05: effect_stack_preset
# ---------------------------------------------------------------------------


def test_preset_writes_yaml_and_returns_path(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="test-preset",
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["scope"] == "workspace"
    assert data["effect_count"] >= 1
    yaml_path = ws / "stacks" / "test-preset.yaml"
    assert yaml_path.is_file()
    loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert loaded["name"] == "test-preset"
    assert len(loaded["effects"]) >= 1


def test_preset_unknown_service_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Mutate the source clip's filter to use an unknown mlt_service.
    proj_path = ws / pf
    tree = ET.parse(proj_path)
    root = tree.getroot()
    # Find filters on SRC (track 2). The fixture has a transform filter on producer0.
    # Simpler: change any <filter> element's mlt_service prop to nonexistent.service
    changed = False
    for filt in root.iter("filter"):
        if filt.get("mlt_service"):
            filt.set("mlt_service", "nonexistent.service")
            changed = True
            break
        for prop in filt.findall("property"):
            if prop.get("name") == "mlt_service":
                prop.text = "nonexistent.service"
                changed = True
                break
        if changed:
            break
    assert changed, "expected a filter element in fixture"
    tree.write(proj_path, encoding="utf-8", xml_declaration=True)

    out = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="bad",
    )
    assert out["status"] == "error", out
    assert "nonexistent.service" in out["message"]


def test_preset_with_tags_and_apply_hints_json(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="tagged",
        tags='["a","b"]',
        apply_hints='{"blend_mode":"screen","stack_order":"prepend"}',
    )
    assert out["status"] == "success", out
    data = yaml.safe_load((ws / "stacks" / "tagged.yaml").read_text(encoding="utf-8"))
    assert data["tags"] == ["a", "b"]
    assert data["apply_hints"]["blend_mode"] == "screen"
    assert data["apply_hints"]["stack_order"] == "prepend"


def test_preset_invalid_tags_json_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="bad-tags",
        tags="not-json",
    )
    assert out["status"] == "error", out
    assert "JSON" in out["message"] or "json" in out["message"].lower()


def test_preset_no_snapshot(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="no-snap",
    )
    assert out["status"] == "success"
    snap_dir = ws / "projects" / "snapshots"
    # It might exist but should be empty (or not exist at all).
    if snap_dir.is_dir():
        assert not any(snap_dir.iterdir()), "preset must not create snapshots"


# ---------------------------------------------------------------------------
# MCP-06..10: effect_stack_apply
# ---------------------------------------------------------------------------


def test_apply_round_trip_filter_count(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="roundtrip",
    )
    assert out["status"] == "success"
    source_count = out["data"]["effect_count"]

    project = _reparse(ws, pf)
    original_target = _effect_count(project, DST)

    ap = effect_stack_apply(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], name="roundtrip",
    )
    assert ap["status"] == "success", ap
    assert ap["data"]["effects_applied"] == source_count

    project2 = _reparse(ws, pf)
    assert _effect_count(project2, DST) == original_target + source_count


def test_apply_mode_override_replace(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Preset the source stack first
    effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="p",
    )
    # Pre-add a filter on the target clip
    r = effect_add(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], effect_name="avfilter.eq",
        params=json.dumps({"av.brightness": "0.1"}),
    )
    assert r["status"] == "success", r

    src_count = _effect_count(_reparse(ws, pf), SRC)

    ap = effect_stack_apply(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], name="p", mode="replace",
    )
    assert ap["status"] == "success", ap
    assert ap["data"]["mode"] == "replace"

    project = _reparse(ws, pf)
    assert _effect_count(project, DST) == src_count


def test_apply_default_mode_uses_preset_hints(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="ph",
        apply_hints='{"stack_order":"prepend"}',
    )
    assert out["status"] == "success", out
    ap = effect_stack_apply(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], name="ph", mode="",
    )
    assert ap["status"] == "success", ap
    assert ap["data"]["mode"] == "prepend"


def test_apply_missing_preset_returns_err_with_paths(tmp_path):
    ws, pf = _make_ws(tmp_path)
    ap = effect_stack_apply(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], name="nonexistent",
    )
    assert ap["status"] == "error"
    # FileNotFoundError message lists both workspace and vault search paths.
    assert "stacks" in ap["message"]


def test_apply_returns_snapshot_id_and_dir_exists(tmp_path):
    ws, pf = _make_ws(tmp_path)
    effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="snapp",
    )
    ap = effect_stack_apply(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], name="snapp",
    )
    assert ap["status"] == "success", ap
    snap_id = ap["data"]["snapshot_id"]
    assert isinstance(snap_id, str) and snap_id
    assert (ws / "projects" / "snapshots" / snap_id).is_dir()


def test_apply_response_includes_hint_fields(tmp_path):
    ws, pf = _make_ws(tmp_path)
    effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="hh",
        apply_hints=(
            '{"blend_mode":"screen","track_placement":"V2",'
            '"required_producers":["audio"]}'
        ),
    )
    ap = effect_stack_apply(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], name="hh",
    )
    assert ap["status"] == "success", ap
    d = ap["data"]
    assert d["blend_mode_hint"] == "screen"
    assert d["track_placement_hint"] == "V2"
    assert d["required_producers_hint"] == ["audio"]


def test_apply_keyframe_byte_exact(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([
        {"frame": 0, "value": [0, 0, 1920, 1080, 1], "easing": "linear"},
        {"frame": 30, "value": [100, 100, 1000, 800, 1], "easing": "linear"},
    ])
    kf = effect_keyframe_set_rect(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], effect_index=0, property="rect",
        keyframes=kfs, mode="replace",
    )
    assert kf["status"] == "success", kf

    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    source_rect = patcher.get_effect_property(_reparse(ws, pf), SRC, 0, "rect")
    assert source_rect

    ps = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="kf",
    )
    assert ps["status"] == "success"

    ap = effect_stack_apply(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], name="kf",
    )
    assert ap["status"] == "success", ap

    project = _reparse(ws, pf)
    names = [e["kdenlive_id"] for e in patcher.list_effects(project, DST)]
    transform_idx = None
    for i, n in enumerate(names):
        if n == "transform":
            transform_idx = i
    assert transform_idx is not None, f"no transform on target: {names}"
    pasted = patcher.get_effect_property(project, DST, transform_idx, "rect")
    assert pasted == source_rect, (
        f"rect mismatch:\n  source={source_rect!r}\n  pasted={pasted!r}"
    )


# ---------------------------------------------------------------------------
# MCP-11..14: effect_stack_promote
# ---------------------------------------------------------------------------


def test_promote_writes_vault_md_when_vault_configured(tmp_path, monkeypatch):
    ws, pf = _make_ws(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", lambda: vault)

    ps = effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="prom",
    )
    assert ps["status"] == "success", ps

    pr = effect_stack_promote(workspace_path=str(ws), name="prom")
    assert pr["status"] == "success", pr
    vault_md = vault / "patterns" / "effect-stacks" / "prom.md"
    assert vault_md.is_file()
    assert pr["data"]["vault_path"] == str(vault_md)


def test_promote_no_vault_returns_err(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    pr = effect_stack_promote(workspace_path=str(ws), name="anything")
    assert pr["status"] == "error"
    msg = pr["message"]
    assert "Vault root not configured" in msg
    assert "vault_root" in msg
    assert "personal_vault" in msg


def test_promote_embeds_wikilink_from_manifest(tmp_path, monkeypatch):
    ws, pf = _make_ws(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", lambda: vault)

    # Set vault_note_path on the workspace manifest.
    from workshop_video_brain.workspace.manifest import read_manifest, write_manifest
    manifest = read_manifest(ws)
    manifest.vault_note_path = "Videos/My Vid.md"
    write_manifest(ws, manifest)

    effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="wl",
    )
    pr = effect_stack_promote(workspace_path=str(ws), name="wl")
    assert pr["status"] == "success", pr
    body = (vault / "patterns" / "effect-stacks" / "wl.md").read_text(encoding="utf-8")
    assert "[[My Vid]]" in body


def test_promote_no_snapshot(tmp_path, monkeypatch):
    ws, pf = _make_ws(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", lambda: vault)

    effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="ns",
    )
    # Snapshot dir may exist from other ops, but promote shouldn't add new ones.
    snap_dir = ws / "projects" / "snapshots"
    before = set(p.name for p in snap_dir.iterdir()) if snap_dir.is_dir() else set()

    pr = effect_stack_promote(workspace_path=str(ws), name="ns")
    assert pr["status"] == "success", pr

    after = set(p.name for p in snap_dir.iterdir()) if snap_dir.is_dir() else set()
    assert after == before, f"promote created snapshot(s): {after - before}"


# ---------------------------------------------------------------------------
# MCP-15..17: effect_stack_list
# ---------------------------------------------------------------------------


def test_list_all_returns_both_tiers(tmp_path, monkeypatch):
    ws, pf = _make_ws(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", lambda: vault)

    for name in ("a", "b"):
        out = effect_stack_preset(
            workspace_path=str(ws), project_file=pf,
            track=SRC[0], clip=SRC[1], name=name,
        )
        assert out["status"] == "success"

    # Hand-craft a vault preset by promoting one of them with a different name.
    # Simpler: save a valid preset YAML manually to vault path by promoting 'a'.
    # First save preset 'c' in workspace, then promote to vault.
    effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="c",
    )
    pr = effect_stack_promote(workspace_path=str(ws), name="c")
    assert pr["status"] == "success", pr
    # Now remove 'c' from workspace so it exists only in vault.
    (ws / "stacks" / "c.yaml").unlink()

    lst = effect_stack_list(workspace_path=str(ws), scope="all")
    assert lst["status"] == "success", lst
    presets = lst["data"]["presets"]
    names = sorted(p["name"] for p in presets)
    assert names == ["a", "b", "c"]
    scopes = {p["name"]: p["scope"] for p in presets}
    assert scopes["a"] == "workspace"
    assert scopes["b"] == "workspace"
    assert scopes["c"] == "vault"


def test_list_workspace_only(tmp_path, monkeypatch):
    ws, pf = _make_ws(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", lambda: vault)

    for name in ("a", "b"):
        effect_stack_preset(
            workspace_path=str(ws), project_file=pf,
            track=SRC[0], clip=SRC[1], name=name,
        )
    # Promote a vault-only preset
    effect_stack_preset(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], name="c",
    )
    effect_stack_promote(workspace_path=str(ws), name="c")
    (ws / "stacks" / "c.yaml").unlink()

    lst = effect_stack_list(workspace_path=str(ws), scope="workspace")
    assert lst["status"] == "success"
    names = sorted(p["name"] for p in lst["data"]["presets"])
    assert names == ["a", "b"]


def test_list_bad_scope(tmp_path):
    ws, _ = _make_ws(tmp_path)
    lst = effect_stack_list(workspace_path=str(ws), scope="nope")
    assert lst["status"] == "error"
    assert "scope" in lst["message"]
