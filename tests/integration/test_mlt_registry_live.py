"""The registry against this host's real MLT, through each engine."""
from __future__ import annotations

import pytest

from tests._testkit import call_tool, requires_melt, requires_mlt_bindings
from workshop_video_brain.edit_mcp.adapters.mlt import engine, registry as mlt_registry
from workshop_video_brain.edit_mcp.server.bundles.mlt_services import mlt_service_info, mlt_services


@pytest.fixture
def melt_only(monkeypatch):
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)


def _assert_core_services(registry) -> None:
    assert {"avfilter.eq", "box_blur"} <= registry.services["filters"]
    assert "timeremap" in registry.services["links"]


@requires_mlt_bindings
def test_bindings_engine():
    registry = mlt_registry.get_registry(refresh=True)
    assert registry.engine == "bindings"
    assert registry.mlt_version
    _assert_core_services(registry)


@requires_melt
def test_melt_engine(melt_only):
    registry = mlt_registry.get_registry(refresh=True)
    assert registry.engine == "melt"
    _assert_core_services(registry)
    mlt_registry.get_registry(refresh=True)


@requires_melt
@requires_mlt_bindings
def test_bindings_filters_are_a_superset_of_melts(monkeypatch):
    bindings = mlt_registry._from_bindings()
    melt = mlt_registry._from_melt()
    assert melt.services["filters"] <= bindings.services["filters"]


@requires_melt
def test_links_search_finds_timeremap():
    result = call_tool(mlt_services, kind="links", query="TIME")
    assert result["status"] == "success", result
    assert "timeremap" in [entry["name"] for entry in result["data"]["names"]]


@requires_melt
def test_denylisted_names_are_flagged():
    result = call_tool(mlt_services, kind="filters", query="avfilter.boxblur")
    flagged = {entry["name"]: entry["kdenlive_unsupported"] for entry in result["data"]["names"]}
    assert flagged.get("avfilter.boxblur", True) is True


def test_unknown_kind_is_invalid_input():
    assert call_tool(mlt_services, kind="nonsense")["error_type"] == "invalid_input"
    assert call_tool(mlt_service_info, "nonsense", "x")["error_type"] == "invalid_input"


@requires_melt
def test_service_info_returns_yaml_with_parameters():
    result = call_tool(mlt_service_info, "filters", "brightness")
    assert result["status"] == "success", result
    assert "parameters" in result["data"]["yaml"]


@requires_melt
def test_unknown_service_is_not_found_with_close_matches():
    result = call_tool(mlt_service_info, "filters", "brightnes")
    assert result["error_type"] == "not_found"
    assert "brightness" in result["suggestion"]
