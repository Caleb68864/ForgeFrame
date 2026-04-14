"""Generator for per-effect MCP wrapper modules.

Reads the catalog (``pipelines/effect_catalog.CATALOG``), selects effects
matching a simple heuristic, and emits one Python module per effect in
``pipelines/effect_wrappers/``. Each generated module defines a single
``effect_<kdenlive_id>`` function decorated with ``register_effect_wrapper``.

Regeneration is deterministic: effects are sorted by ``kdenlive_id`` and
param order is preserved from the catalog, so emitting twice yields byte
identical output.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from workshop_video_brain.edit_mcp.pipelines.effect_catalog import (
    EffectDef,
    ParamDef,
    ParamType,
)


# ---------------------------------------------------------------------------
# Selection heuristic
# ---------------------------------------------------------------------------

SELECTION_HEURISTIC_DOCSTRING = (
    "Wrappable effect selection heuristic:\n"
    "  - category == 'video'\n"
    "  - len(params) <= 8\n"
    "  - kdenlive_id matches ^[A-Za-z0-9_\\-]+$\n"
    "  - display_name is non-empty after strip\n"
    "  - Result sorted by kdenlive_id for deterministic output\n"
)

_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def select_wrappable_effects(
    catalog: dict[str, EffectDef],
) -> list[EffectDef]:
    """Return the subset of effects suitable for wrapper generation.

    See ``SELECTION_HEURISTIC_DOCSTRING`` for the exact filter rules.
    The returned list is sorted by ``kdenlive_id`` for deterministic output.
    """
    selected: list[EffectDef] = []
    for eff in catalog.values():
        if eff.category != "video":
            continue
        if len(eff.params) > 8:
            continue
        if not _ID_RE.match(eff.kdenlive_id):
            continue
        if not eff.display_name or not eff.display_name.strip():
            continue
        selected.append(eff)
    selected.sort(key=lambda e: e.kdenlive_id)
    return selected


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_ANIMATED_TYPES = {ParamType.KEYFRAME, ParamType.ANIMATED, ParamType.GEOMETRY}
_SKIP_TYPES = {ParamType.READONLY, ParamType.HIDDEN} | _ANIMATED_TYPES


def _py_identifier(name: str) -> str:
    """Turn a catalog param name like ``av.level_in`` into a Python identifier."""
    ident = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if ident and ident[0].isdigit():
        ident = "_" + ident
    return ident or "_param"


def _parse_bool(default: str | None) -> bool:
    if default is None:
        return False
    return default.strip() not in ("", "0", "false", "False")


def _render_default(p: ParamDef) -> tuple[str, str]:
    """Return (type_annotation, default_literal) for a param."""
    t = p.type
    d = p.default
    if t in (ParamType.INTEGER, ParamType.POSITION):
        try:
            return "int", repr(int(float(d))) if d is not None else "0"
        except (TypeError, ValueError):
            return "int", "0"
    if t in (ParamType.DOUBLE, ParamType.CONSTANT):
        try:
            return "float", repr(float(d)) if d is not None else "0.0"
        except (TypeError, ValueError):
            return "float", "0.0"
    if t in (ParamType.BOOL, ParamType.SWITCH):
        return "bool", repr(_parse_bool(d))
    if t == ParamType.LIST and p.values:
        values_literal = ", ".join(repr(v) for v in p.values)
        ann = f"Literal[{values_literal}]"
        default_literal = repr(d) if d is not None else repr(p.values[0])
        return ann, default_literal
    if t == ParamType.FIXED:
        # Best-effort: keep as string with catalog default.
        return "str", repr(d if d is not None else "")
    # COLOR, STRING, URL, LIST without values, unknown -> str
    return "str", repr(d if d is not None else "")


def _kwargs_for(effect: EffectDef) -> tuple[list[tuple[str, str, str, str]], bool]:
    """Return (kwargs, has_animated).

    Each kwarg tuple is (py_ident, mlt_name, type_annotation, default_literal).
    """
    kwargs: list[tuple[str, str, str, str]] = []
    has_animated = False
    for p in effect.params:
        if p.type in _ANIMATED_TYPES:
            has_animated = True
            continue
        if p.type in (ParamType.READONLY, ParamType.HIDDEN):
            continue
        ann, default_literal = _render_default(p)
        kwargs.append((_py_identifier(p.name), p.name, ann, default_literal))
    return kwargs, has_animated


def _escape_docstring(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def render_wrapper_module(effect_def: EffectDef) -> str:
    """Return Python source for a single wrapped effect module."""
    kwargs, has_animated = _kwargs_for(effect_def)
    func_name = f"effect_{_py_identifier(effect_def.kdenlive_id)}"

    # Detect whether Literal is needed
    needs_literal = any(k[2].startswith("Literal[") for k in kwargs)

    lines: list[str] = []
    lines.append(
        '"""GENERATED by effect_wrapper_gen. Do not edit by hand.\n'
        "\n"
        "Regenerate with:\n"
        "    uv run workshop-video-brain catalog regenerate-wrappers\n"
        "\n"
        f"Source effect: kdenlive_id={effect_def.kdenlive_id}, "
        f"mlt_service={effect_def.mlt_service}\n"
        '"""'
    )
    lines.append("from __future__ import annotations")
    lines.append("")
    if needs_literal:
        lines.append("from typing import Literal")
    lines.append("import xml.etree.ElementTree as ET")
    lines.append("")
    lines.append(
        "from workshop_video_brain.edit_mcp.server.tools_helpers import ("
    )
    lines.append("    _ok,")
    lines.append("    _err,")
    lines.append("    _require_workspace,")
    lines.append("    register_effect_wrapper,")
    lines.append(")")
    lines.append(
        "from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher"
    )
    lines.append(
        "from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import "
        "parse_project"
    )
    lines.append(
        "from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import "
        "serialize_project"
    )
    lines.append("from workshop_video_brain.workspace import create_snapshot")
    lines.append("")
    lines.append("")

    # Signature
    sig_lines = [f"def {func_name}("]
    sig_lines.append("    workspace_path: str,")
    sig_lines.append("    project_file: str,")
    sig_lines.append("    track: int,")
    sig_lines.append("    clip: int,")
    for py_ident, _mlt, ann, default in kwargs:
        sig_lines.append(f"    {py_ident}: {ann} = {default},")
    if has_animated:
        sig_lines.append('    keyframes: str = "",')
    sig_lines.append(") -> dict:")

    display = _escape_docstring(effect_def.display_name or effect_def.kdenlive_id)
    desc = _escape_docstring((effect_def.description or "").strip())
    doc_summary = f"{display}"
    if desc:
        doc_summary += f" -- {desc.splitlines()[0]}"

    # Param mapping dict literal (py_ident -> mlt name)
    param_map_items = ", ".join(
        f"{repr(mlt)}: {py_ident}" for py_ident, mlt, _a, _d in kwargs
    )
    param_map_literal = "{" + param_map_items + "}"

    body = f'''    """{doc_summary}."""
    try:
        ws_path, _ws = _require_workspace(workspace_path)
        project_path = ws_path / project_file
        if not project_path.exists():
            return _err(f"Project file not found: {{project_file}}")

        project = parse_project(project_path)

        # Build filter XML
        filt = ET.Element("filter")
        svc = ET.SubElement(filt, "property", {{"name": "mlt_service"}})
        svc.text = {repr(effect_def.mlt_service)}
        kid = ET.SubElement(filt, "property", {{"name": "kdenlive_id"}})
        kid.text = {repr(effect_def.kdenlive_id)}

        params: dict[str, object] = {param_map_literal}
        for _mlt_name, _value in params.items():
            if isinstance(_value, bool):
                _str_val = "1" if _value else "0"
            else:
                _str_val = str(_value)
            _prop = ET.SubElement(filt, "property", {{"name": _mlt_name}})
            _prop.text = _str_val

        if keyframes:
            _kf = ET.SubElement(filt, "property", {{"name": "keyframes"}})
            _kf.text = keyframes

        xml_string = ET.tostring(filt, encoding="unicode")

        # Determine insertion index (end of stack)
        existing = patcher.list_effects(project, (track, clip))
        insert_index = len(existing)

        create_snapshot(
            ws_path,
            project_path,
            description="before_effect_{effect_def.kdenlive_id}",
        )
        patcher.insert_effect_xml(project, (track, clip), xml_string, insert_index)
        snap = create_snapshot(
            ws_path,
            project_path,
            description="after_effect_{effect_def.kdenlive_id}",
        )
        serialize_project(project, project_path)

        return _ok({{
            "effect_index": insert_index,
            "snapshot_id": snap.snapshot_id,
        }})
    except (ValueError, FileNotFoundError, IndexError) as exc:
        return _err(str(exc))
'''

    sig_block = "\n".join(sig_lines)
    return _assemble_module(lines, sig_block, has_animated, body)


def _assemble_module(
    header_lines: list[str],
    sig_block: str,
    has_kf_param: bool,
    body: str,
) -> str:
    out = "\n".join(header_lines) + "\n"
    out += "@register_effect_wrapper\n"
    out += sig_block + "\n"
    if not has_kf_param:
        out += '    keyframes = ""\n'
    # `body` is authored with 4-space leading indent on every line already.
    out += body
    if not out.endswith("\n"):
        out += "\n"
    return out


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------

def emit_wrappers_package(
    effects: Iterable[EffectDef],
    output_dir: Path,
    *,
    force: bool = False,
) -> None:
    """Write one module per effect + ``__init__.py`` into ``output_dir``.

    Refuses to overwrite a non-empty directory unless ``force=True``.
    Regeneration is byte-identical if the input catalog is unchanged.
    """
    effects = sorted(effects, key=lambda e: e.kdenlive_id)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Conflict detection: existing non-generated files block without --force
    existing = [p for p in output_dir.iterdir() if p.is_file()]
    if existing and not force:
        blockers = sorted(p.name for p in existing)
        raise FileExistsError(
            f"output_dir {output_dir} is not empty: {blockers}. "
            "Pass force=True to overwrite."
        )

    # Wipe any prior generated files (only if force). We clear *.py to
    # guarantee determinism (stale modules from a prior catalog must not
    # linger).
    if force:
        for p in existing:
            if p.suffix == ".py":
                p.unlink()

    func_names: list[str] = []
    seen_names: set[str] = set()

    for eff in effects:
        module_src = render_wrapper_module(eff)
        py_ident = _py_identifier(eff.kdenlive_id)
        func_name = f"effect_{py_ident}"
        if func_name in seen_names:
            raise RuntimeError(
                f"wrapper name collision: {func_name} "
                f"(kdenlive_id={eff.kdenlive_id})"
            )
        seen_names.add(func_name)
        func_names.append(func_name)
        (output_dir / f"{func_name}.py").write_text(module_src, encoding="utf-8")

    # Emit __init__.py
    func_names_sorted = sorted(func_names)
    init_lines = [
        '"""GENERATED package of per-effect MCP wrappers.',
        "",
        "Regenerate with:",
        "    uv run workshop-video-brain catalog regenerate-wrappers",
        '"""',
        "from __future__ import annotations",
        "",
    ]
    for fn in func_names_sorted:
        init_lines.append(f"from .{fn} import {fn}")
    init_lines.append("")
    init_lines.append("__all__ = [")
    for fn in func_names_sorted:
        init_lines.append(f"    {repr(fn)},")
    init_lines.append("]")
    init_lines.append("")
    (output_dir / "__init__.py").write_text(
        "\n".join(init_lines), encoding="utf-8"
    )
