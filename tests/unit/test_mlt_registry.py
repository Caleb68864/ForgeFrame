"""The service registry's rules, against a fake; needs no MLT."""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.adapters.mlt import engine, registry as mlt_registry
from workshop_video_brain.edit_mcp.adapters.mlt.registry import (
    ServiceRegistry,
    UnregisteredServiceError,
    check_service,
    parse_melt_query,
    use_registry,
)

FAKE = ServiceRegistry("melt", "7.42.0", {
    "filters": frozenset({"avfilter.gblur", "avfilter.crop", "avfilter.eq", "affine"}),
    "transitions": frozenset({"affine", "luma"}),
    "producers": frozenset(),
    "consumers": frozenset(),
    "links": frozenset({"timeremap"}),
})


def test_known_service_is_ok():
    assert check_service("filters", "avfilter.eq", registry=FAKE) == "ok"


def test_unknown_service_suggests_close_matches():
    with pytest.raises(UnregisteredServiceError) as raised:
        check_service("filters", "avfilter.gblurr", registry=FAKE)
    assert raised.value.suggestions[0] == "avfilter.gblur"
    assert raised.value.substitute is None
    assert "Did you mean: avfilter.gblur" in str(raised.value)


def test_checks_are_kind_aware():
    assert check_service("links", "timeremap", registry=FAKE) == "ok"
    with pytest.raises(UnregisteredServiceError):
        check_service("filters", "timeremap", registry=FAKE)
    assert check_service("transitions", "affine", registry=FAKE) == "ok"
    assert check_service("filters", "affine", registry=FAKE) == "ok"


def test_denylist_applies_even_when_mlt_has_the_service():
    with pytest.raises(UnregisteredServiceError) as raised:
        check_service("filters", "avfilter.crop", registry=FAKE)
    assert raised.value.substitute == "crop"
    assert "Kdenlive drops" in str(raised.value)


def test_denylist_applies_even_when_the_host_check_is_skipped():
    with pytest.raises(UnregisteredServiceError):
        check_service("filters", "avfilter.boxblur", registry=FAKE, check_host=False)
    assert check_service("filters", "not.real", registry=FAKE, check_host=False) == "skipped"


def test_no_registry_fails_open(monkeypatch):
    monkeypatch.setattr(mlt_registry, "get_registry", lambda refresh=False: None)
    assert check_service("filters", "whatever") == "unchecked"


def test_parse_melt_query_skips_the_yaml_header():
    stdout = "---\nfilters:\n  - avfilter.eq\n  - box_blur\n...\n"
    assert parse_melt_query(stdout) == ["avfilter.eq", "box_blur"]


def test_use_registry_restores_the_previous_one():
    with use_registry(FAKE):
        assert mlt_registry.get_registry() is FAKE
        assert mlt_registry.loaded_registry() is FAKE
    assert mlt_registry.loaded_registry() is not FAKE


def test_miss_is_remembered_so_a_host_without_mlt_does_not_respawn(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: calls.append("bindings"))
    monkeypatch.setattr(mlt_registry.shutil, "which", lambda _name: calls.append("melt"))
    monkeypatch.setattr(mlt_registry, "_cached", None)
    monkeypatch.setattr(mlt_registry, "_failed_at", None)
    assert mlt_registry.get_registry() is None
    made = len(calls)
    assert mlt_registry.get_registry() is None
    assert len(calls) == made
    assert mlt_registry.get_registry(refresh=True) is None
    assert len(calls) > made
