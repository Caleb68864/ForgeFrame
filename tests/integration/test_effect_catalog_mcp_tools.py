"""Integration tests for effect catalog MCP tools (sub-spec 3)."""
from __future__ import annotations

import inspect

import pytest

from workshop_video_brain.edit_mcp.server import tools as tools_module
from workshop_video_brain.edit_mcp.server.tools import (
    effect_info,
    effect_list_common,
)


class TestEffectInfoRegistered:
    # SS3-01 / SS3-05
    def test_effect_info_is_callable(self):
        assert callable(tools_module.effect_info)

    def test_effect_list_common_is_callable(self):
        assert callable(tools_module.effect_list_common)


class TestEffectInfoShape:
    # SS3-02, SS3-06
    def test_effect_info_by_kdenlive_id(self):
        result = effect_info("acompressor")
        assert result["status"] == "success"
        data = result["data"]
        assert data["kdenlive_id"] == "acompressor"
        assert data["mlt_service"] == "avfilter.acompressor"
        assert data["category"] == "audio"
        assert "display_name" in data
        assert "description" in data
        assert isinstance(data["params"], list)
        assert len(data["params"]) > 0
        p = data["params"][0]
        for key in (
            "name",
            "display_name",
            "type",
            "default",
            "min",
            "max",
            "decimals",
            "values",
            "value_labels",
            "keyframable",
        ):
            assert key in p

    # SS3-07
    def test_effect_info_by_mlt_service(self):
        by_id = effect_info("acompressor")
        by_service = effect_info("avfilter.acompressor")
        assert by_service["status"] == "success"
        assert by_service["data"]["kdenlive_id"] == by_id["data"]["kdenlive_id"]

    # SS3-08
    def test_effect_info_not_found(self):
        result = effect_info("nonexistent_effect")
        assert result == {
            "status": "error",
            "message": "Effect not found: nonexistent_effect. Try `effect_list_common` for the registry.",
        }

    # SS3-09
    def test_effect_info_empty_string(self):
        assert effect_info("") == {
            "status": "error",
            "message": "Effect name cannot be empty.",
        }

    def test_effect_info_whitespace_only(self):
        assert effect_info("   ")["status"] == "error"

    def test_effect_info_param_serialization(self):
        # find an effect that has a LIST param (values/value_labels populated)
        result = effect_info("acompressor")
        params = result["data"]["params"]
        # av.link is a LIST param
        link = next(p for p in params if p["name"] == "av.link")
        assert link["type"] == "list"  # enum value string, not enum instance
        assert isinstance(link["values"], list)
        assert isinstance(link["value_labels"], list)
        assert link["values"] == ["0", "1"]
        assert isinstance(link["keyframable"], bool)


class TestEffectListCommon:
    # SS3-03
    def test_signature_unchanged(self):
        sig = inspect.signature(effect_list_common)
        assert len(sig.parameters) == 0

    # SS3-10
    def test_returns_full_catalog(self):
        result = effect_list_common()
        assert result["status"] == "success"
        effects = result["data"]["effects"]
        assert isinstance(effects, list)
        assert len(effects) > 300

    def test_entry_shape(self):
        result = effect_list_common()
        for entry in result["data"]["effects"][:5]:
            assert set(entry.keys()) == {
                "kdenlive_id",
                "mlt_service",
                "display_name",
                "category",
                "short_description",
            }

    # SS3-11
    def test_short_description_truncation(self):
        result = effect_list_common()
        # The real catalog has effects with descriptions; find any that were truncated
        for entry in result["data"]["effects"]:
            desc = entry["short_description"]
            if desc.endswith("..."):
                assert len(desc) <= 83
                return
        # If none were long enough, synthesize one via monkeypatched catalog
        # (not strictly necessary -- just verify invariant: all <= 83 or no "...")
        for entry in result["data"]["effects"]:
            desc = entry["short_description"]
            if desc.endswith("..."):
                assert len(desc) <= 83

    def test_short_description_synthetic_truncation(self, monkeypatch):
        from workshop_video_brain.edit_mcp.pipelines import effect_catalog as _catalog

        long_desc = "x" * 200
        fake = _catalog.EffectDef(
            kdenlive_id="fake",
            mlt_service="fake.service",
            display_name="Fake",
            description=long_desc,
            category="video",
            params=(),
        )
        monkeypatch.setattr(_catalog, "CATALOG", {"fake": fake})
        result = effect_list_common()
        entry = result["data"]["effects"][0]
        assert entry["short_description"].endswith("...")
        assert len(entry["short_description"]) == 83
