"""Unit tests for the effect catalog generator (Sub-Spec 2)."""
from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import io
import json
import logging
import pathlib
import shutil
import subprocess
import sys
import urllib.error
from unittest.mock import patch

import pytest

from workshop_video_brain.edit_mcp.pipelines import effect_catalog_gen as gen
from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import (
    DiffReport,
    EffectDef,
    ParamDef,
    ParamType,
    build_catalog,
    emit_python_module,
    fetch_upstream_effects,
)

FIXTURE_DIR = (
    pathlib.Path(__file__).parent / "fixtures" / "effect_xml"
)
BUILD_THREE = FIXTURE_DIR / "build_three"


def _load_module(path: pathlib.Path, name: str = "generated_catalog_under_test"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


# ---------------------------------------------------------------------------
# SS2-01: build_catalog signature
# ---------------------------------------------------------------------------
def test_build_catalog_signature():
    sig = inspect.signature(build_catalog)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["local_dir", "check_upstream"]
    assert sig.parameters["check_upstream"].default is True


# ---------------------------------------------------------------------------
# SS2-02: emit_python_module signature
# ---------------------------------------------------------------------------
def test_emit_python_module_signature():
    sig = inspect.signature(emit_python_module)
    names = [p.name for p in sig.parameters.values()]
    # `now` is an optional implementation detail; first 4 must match contract.
    assert names[:4] == ["effects", "output_path", "source_version", "diff_report"]
    assert sig.return_annotation in (None, type(None), "None")


# ---------------------------------------------------------------------------
# SS2-03: fetch_upstream_effects signature
# ---------------------------------------------------------------------------
def test_fetch_upstream_effects_signature():
    sig = inspect.signature(fetch_upstream_effects)
    required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert required == []
    assert "list" in str(sig.return_annotation)
    assert "None" in str(sig.return_annotation)


# ---------------------------------------------------------------------------
# SS2-04: DiffReport shape
# ---------------------------------------------------------------------------
def test_diffreport_shape():
    assert dataclasses.is_dataclass(DiffReport)
    fields = {f.name: f for f in dataclasses.fields(DiffReport)}
    assert set(fields) == {
        "local_count",
        "upstream_count",
        "upstream_only_ids",
        "local_only_ids",
        "upstream_check",
    }
    assert "int" in str(fields["local_count"].type)
    assert "None" in str(fields["upstream_count"].type)
    assert "tuple" in str(fields["upstream_only_ids"].type)
    assert "tuple" in str(fields["local_only_ids"].type)
    assert "Literal" in str(fields["upstream_check"].type) or "str" in str(
        fields["upstream_check"].type
    )

    # Frozen check
    report = DiffReport(
        local_count=0,
        upstream_count=None,
        upstream_only_ids=(),
        local_only_ids=(),
        upstream_check="skipped",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.local_count = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SS2-05: generated module exports
# ---------------------------------------------------------------------------
def test_generated_module_exports(tmp_path: pathlib.Path):
    effects, report = build_catalog(BUILD_THREE, check_upstream=False)
    out = tmp_path / "effect_catalog.py"
    emit_python_module(effects, out, "test-1.0", report)

    mod = _load_module(out, name="exports_test_module")
    assert isinstance(mod.CATALOG, dict) and len(mod.CATALOG) > 0
    assert callable(mod.find_by_name)
    assert callable(mod.find_by_service)
    assert isinstance(mod.__generated_at__, str)
    assert isinstance(mod.__source_version__, str)
    assert isinstance(mod.__local_count__, int)


# ---------------------------------------------------------------------------
# SS2-06: build_catalog against fixtures
# ---------------------------------------------------------------------------
def test_build_catalog_skip_upstream():
    effects, report = build_catalog(BUILD_THREE, check_upstream=False)
    assert len(effects) == 3
    assert isinstance(effects[0], EffectDef)
    assert report.upstream_check == "skipped"
    assert report.upstream_count is None
    assert report.local_count == 3


# ---------------------------------------------------------------------------
# SS2-07: emit round-trip
# ---------------------------------------------------------------------------
def test_emit_python_module_roundtrip(tmp_path: pathlib.Path):
    effects, report = build_catalog(BUILD_THREE, check_upstream=False)
    out = tmp_path / "rt.py"
    emit_python_module(effects, out, "test-1.0", report)
    mod = _load_module(out, name="roundtrip_module")

    assert set(mod.CATALOG.keys()) == {e.kdenlive_id for e in effects}
    for eff in effects:
        loaded = mod.CATALOG[eff.kdenlive_id]
        assert loaded.kdenlive_id == eff.kdenlive_id
        assert loaded.mlt_service == eff.mlt_service
        assert loaded.display_name == eff.display_name
        assert loaded.description == eff.description
        assert loaded.category == eff.category
        assert len(loaded.params) == len(eff.params)
        for lp, op in zip(loaded.params, eff.params):
            assert lp.name == op.name
            assert lp.display_name == op.display_name
            assert lp.type.value == op.type.value
            assert lp.default == op.default
            assert lp.min == op.min
            assert lp.max == op.max
            assert lp.decimals == op.decimals
            assert tuple(lp.values) == tuple(op.values)
            assert tuple(lp.value_labels) == tuple(op.value_labels)
            assert lp.keyframable == op.keyframable


# ---------------------------------------------------------------------------
# SS2-08: generated module docstring
# ---------------------------------------------------------------------------
def test_generated_docstring(tmp_path: pathlib.Path):
    effects, report = build_catalog(BUILD_THREE, check_upstream=False)
    out = tmp_path / "doc.py"
    emit_python_module(effects, out, "25.12.3", report)
    mod = _load_module(out, name="doc_module")
    assert mod.__doc__
    assert "regenerate" in mod.__doc__.lower()
    assert "25.12.3" in mod.__doc__
    assert (
        "scripts/generate_effect_catalog.py" in mod.__doc__
        or "workshop-video-brain catalog regenerate" in mod.__doc__
    )


# ---------------------------------------------------------------------------
# SS2-09: fetch_upstream_effects returns None on failure
# ---------------------------------------------------------------------------
def test_fetch_upstream_failure_network():
    with patch.object(gen.urllib.request, "urlopen", side_effect=OSError("down")):
        assert fetch_upstream_effects() is None


def test_fetch_upstream_failure_urlerror():
    with patch.object(
        gen.urllib.request, "urlopen", side_effect=urllib.error.URLError("x")
    ):
        assert fetch_upstream_effects() is None


def test_fetch_upstream_failure_httperror():
    err = urllib.error.HTTPError(
        url="u", code=404, msg="nf", hdrs=None, fp=io.BytesIO(b"")  # type: ignore[arg-type]
    )
    with patch.object(gen.urllib.request, "urlopen", side_effect=err):
        assert fetch_upstream_effects() is None


def test_fetch_upstream_success():
    fake_payload = json.dumps(
        [
            {"name": "foo.xml", "type": "file"},
            {"name": "bar.xml", "type": "file"},
            {"name": "README.md", "type": "file"},
        ]
    ).encode("utf-8")

    class _FakeResp:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch.object(
        gen.urllib.request, "urlopen", return_value=_FakeResp(fake_payload)
    ):
        result = fetch_upstream_effects()
    assert result == ["bar", "foo"]


# ---------------------------------------------------------------------------
# SS2-10: duplicate id warns + last-wins (simulated via mocked parse)
# ---------------------------------------------------------------------------
def test_duplicate_id_last_wins(tmp_path: pathlib.Path, caplog):
    # Two real files but force parse_effect_xml to return colliding ids.
    (tmp_path / "a.xml").write_text("<effect/>", encoding="utf-8")
    (tmp_path / "b.xml").write_text("<effect/>", encoding="utf-8")

    first = EffectDef(
        kdenlive_id="transform",
        mlt_service="first_svc",
        display_name="First",
        description="",
        category="video",
        params=(),
    )
    second = EffectDef(
        kdenlive_id="transform",
        mlt_service="second_svc",
        display_name="Second",
        description="",
        category="video",
        params=(),
    )
    # Sorted glob order is [a.xml, b.xml] -> second overrides first.
    with patch.object(gen, "parse_effect_xml", side_effect=[first, second]):
        with caplog.at_level(logging.WARNING, logger=gen._LOG.name):
            effects, _ = build_catalog(tmp_path, check_upstream=False)

    assert len(effects) == 1
    assert effects[0].mlt_service == "second_svc"
    dup_records = [r for r in caplog.records if "duplicate" in r.getMessage().lower()]
    assert dup_records, "expected duplicate warning"
    msg = dup_records[0].getMessage()
    assert "a.xml" in msg and "b.xml" in msg


# ---------------------------------------------------------------------------
# SS2-11: script runs against fixtures
# ---------------------------------------------------------------------------
def test_script_runs_against_fixtures(tmp_path: pathlib.Path):
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "generate_effect_catalog.py"
    assert script.exists()
    out = tmp_path / "out.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--no-upstream-check",
            "--output",
            str(out),
            "--source-dir",
            str(BUILD_THREE),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    mod = _load_module(out, name="script_fixture_module")
    assert len(mod.CATALOG) == 3


# ---------------------------------------------------------------------------
# SS2-12-ish: build_catalog skips unparseable
# ---------------------------------------------------------------------------
def test_build_catalog_skips_unparseable(tmp_path: pathlib.Path, caplog):
    shutil.copy(FIXTURE_DIR / "acompressor.xml", tmp_path / "acompressor.xml")
    shutil.copy(FIXTURE_DIR / "transform.xml", tmp_path / "transform.xml")
    (tmp_path / "broken.xml").write_text("<not-valid-xml", encoding="utf-8")
    (tmp_path / "unknown.xml").write_text(
        '<?xml version="1.0"?><effect tag="x" type="video">'
        '<parameter type="wat" name="p"/></effect>',
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger=gen._LOG.name):
        effects, report = build_catalog(tmp_path, check_upstream=False)
    assert {e.kdenlive_id for e in effects} == {"acompressor", "transform"}
    assert report.local_count == 2


# ---------------------------------------------------------------------------
# Emit idempotency
# ---------------------------------------------------------------------------
def test_emit_idempotent(tmp_path: pathlib.Path):
    import datetime

    effects, report = build_catalog(BUILD_THREE, check_upstream=False)
    fixed = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    emit_python_module(effects, a, "v1", report, now=fixed)
    emit_python_module(effects, b, "v1", report, now=fixed)
    assert a.read_bytes() == b.read_bytes()


# ---------------------------------------------------------------------------
# SS2-13: generated module __local_count__ metadata
# ---------------------------------------------------------------------------
def test_emit_local_count_metadata(tmp_path: pathlib.Path):
    effects, report = build_catalog(BUILD_THREE, check_upstream=False)
    out = tmp_path / "meta.py"
    emit_python_module(effects, out, "vX", report)
    mod = _load_module(out, name="meta_module")
    assert mod.__local_count__ == len(effects)
    assert mod.__source_version__ == "vX"
    assert len(mod.CATALOG) == mod.__local_count__


# ---------------------------------------------------------------------------
# SS2-14 (find helpers on generated module)
# ---------------------------------------------------------------------------
def test_find_by_name_and_service(tmp_path: pathlib.Path):
    effects, report = build_catalog(BUILD_THREE, check_upstream=False)
    out = tmp_path / "finders.py"
    emit_python_module(effects, out, "v1", report)
    mod = _load_module(out, name="finders_module")

    any_effect = next(iter(effects))
    found = mod.find_by_name(any_effect.kdenlive_id)
    assert found is not None
    assert found.kdenlive_id == any_effect.kdenlive_id

    found_svc = mod.find_by_service(any_effect.mlt_service)
    assert found_svc is not None
    assert found_svc.mlt_service == any_effect.mlt_service

    assert mod.find_by_name("does-not-exist-xyzzy") is None
    assert mod.find_by_service("no-such-service-xyzzy") is None
