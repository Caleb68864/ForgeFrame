"""Catalog generator: parses Kdenlive effect XML into typed records.

Pure logic only -- no I/O against system paths, no file output, no MCP wiring.
Sub-spec 2 will use these primitives to build the on-disk catalog; sub-spec 3
will serialize them through the MCP layer.
"""
from __future__ import annotations

import dataclasses
import datetime
import enum
import json
import logging
import os
import pathlib
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Literal

logger = logging.getLogger(__name__)
_LOG = logger

UPSTREAM_API_URL = (
    "https://api.github.com/repos/KDE/kdenlive/contents/data/effects?ref=master"
)


class ParamType(str, enum.Enum):
    """Closed set of Kdenlive `<parameter type="...">` values."""

    CONSTANT = "constant"
    DOUBLE = "double"
    INTEGER = "integer"
    BOOL = "bool"
    SWITCH = "switch"
    COLOR = "color"
    KEYFRAME = "keyframe"
    ANIMATED = "animated"
    GEOMETRY = "geometry"
    LIST = "list"
    FIXED = "fixed"
    POSITION = "position"
    URL = "url"
    STRING = "string"
    READONLY = "readonly"
    HIDDEN = "hidden"


_KEYFRAMABLE_TYPES = frozenset(
    {ParamType.KEYFRAME, ParamType.ANIMATED, ParamType.GEOMETRY}
)


@dataclasses.dataclass(frozen=True, slots=True)
class ParamDef:
    name: str
    display_name: str
    type: ParamType
    default: str | None
    min: float | None
    max: float | None
    decimals: int | None
    values: tuple[str, ...]
    value_labels: tuple[str, ...]
    keyframable: bool


@dataclasses.dataclass(frozen=True, slots=True)
class EffectDef:
    kdenlive_id: str
    mlt_service: str
    display_name: str
    description: str
    category: str
    params: tuple[ParamDef, ...]


def _strip_ns(elem: ET.Element) -> None:
    """Recursively strip `{namespace}` prefixes from every tag in-place."""
    for e in elem.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]


def _pick_name(parent: ET.Element, fallback: str) -> str:
    """Choose the no-lang `<name>` if present; else first `<name>`; else fallback."""
    names = parent.findall("name")
    if not names:
        return fallback
    for n in names:
        if "lang" not in n.attrib:
            return (n.text or "").strip() or fallback
    return (names[0].text or "").strip() or fallback


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_param(element: ET.Element) -> ParamDef:
    """Parse one `<parameter>` element into a `ParamDef`.

    Raises `ValueError` if the `type` attribute is not in the `ParamType` enum.
    """
    raw_type = element.get("type", "")
    name = element.get("name", "")
    try:
        param_type = ParamType(raw_type)
    except ValueError as exc:
        raise ValueError(
            f"Unknown parameter type {raw_type!r} for parameter {name!r}"
        ) from exc

    display_name = _pick_name(element, fallback=name)
    default = element.get("default")
    pmin = _to_float(element.get("min"))
    pmax = _to_float(element.get("max"))
    decimals = _to_int(element.get("decimals"))

    values: tuple[str, ...] = ()
    value_labels: tuple[str, ...] = ()
    if param_type is ParamType.LIST:
        paramlist = element.get("paramlist", "")
        values = tuple(v for v in paramlist.split(";") if v != "") if paramlist else ()
        display_elem = element.find("paramlistdisplay")
        if display_elem is not None and display_elem.text:
            value_labels = tuple(s.strip() for s in display_elem.text.split(","))
        else:
            value_labels = values

    keyframable = element.get("keyframes") == "1" or param_type in _KEYFRAMABLE_TYPES

    return ParamDef(
        name=name,
        display_name=display_name,
        type=param_type,
        default=default,
        min=pmin,
        max=pmax,
        decimals=decimals,
        values=values,
        value_labels=value_labels,
        keyframable=keyframable,
    )


def parse_effect_xml(path: pathlib.Path) -> EffectDef:
    """Parse a Kdenlive effect XML file into a single `EffectDef`.

    Raises `ValueError` if the root tag is not `<effect>` or if any contained
    `<parameter>` has an unknown `type` value (the file name is appended to the
    error message for diagnostic context).
    """
    tree = ET.parse(path)
    root = tree.getroot()
    _strip_ns(root)

    if root.tag != "effect":
        raise ValueError(f"Not a Kdenlive effect XML: {path}")

    kdenlive_id = path.stem
    mlt_service = root.get("tag", "")
    category = root.get("type", "custom")
    display_name = _pick_name(root, fallback=kdenlive_id)

    description_elem = root.find("description")
    description = (
        description_elem.text or "" if description_elem is not None else ""
    )

    params: list[ParamDef] = []
    for p in root.findall("parameter"):
        try:
            params.append(parse_param(p))
        except ValueError as exc:
            raise ValueError(f"{exc} in file {path.name}") from exc

    return EffectDef(
        kdenlive_id=kdenlive_id,
        mlt_service=mlt_service,
        display_name=display_name,
        description=description,
        category=category,
        params=tuple(params),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class DiffReport:
    """Summary of the local-vs-upstream effect catalog cross-check."""

    local_count: int
    upstream_count: int | None
    upstream_only_ids: tuple[str, ...]
    local_only_ids: tuple[str, ...]
    upstream_check: Literal["ok", "skipped", "failed"]


def fetch_upstream_effects() -> list[str] | None:
    """Fetch upstream Kdenlive effect XML filenames from the KDE GitHub mirror.

    Returns a sorted list of filename stems (without `.xml`). Returns ``None``
    on any network/parse failure -- does not raise.
    """
    try:
        with urllib.request.urlopen(UPSTREAM_API_URL, timeout=10) as resp:
            payload = resp.read()
        entries = json.loads(payload)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        _LOG.warning("upstream fetch failed: %s", exc)
        return None
    except json.JSONDecodeError as exc:
        _LOG.warning("upstream fetch: invalid JSON: %s", exc)
        return None

    if not isinstance(entries, list):
        _LOG.warning("upstream fetch: unexpected payload shape")
        return None

    stems: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name.endswith(".xml"):
            stems.append(name[:-4])
    return sorted(stems)


def build_catalog(
    local_dir: pathlib.Path, check_upstream: bool = True
) -> tuple[list[EffectDef], DiffReport]:
    """Parse every `*.xml` in ``local_dir`` into ``EffectDef`` records.

    Unparseable XML files are logged and skipped (``ET.ParseError`` or
    ``ValueError`` from unknown parameter types). Duplicate ``kdenlive_id``
    collisions yield a warning naming both source paths; last-write wins.

    If ``check_upstream`` is True, fetches the upstream Kdenlive effect list and
    records set differences in the returned ``DiffReport``. On network failure
    the cross-check is marked ``failed`` (not ``skipped``) with empty diff
    lists.
    """
    local_dir = pathlib.Path(local_dir)
    xml_files = sorted(p for p in local_dir.glob("*.xml") if p.is_file())

    effects_by_id: dict[str, EffectDef] = {}
    source_paths: dict[str, pathlib.Path] = {}

    for path in xml_files:
        try:
            effect = parse_effect_xml(path)
        except (ET.ParseError, ValueError) as exc:
            _LOG.warning("skipping unparseable effect XML %s: %s", path, exc)
            continue
        if effect.kdenlive_id in effects_by_id:
            _LOG.warning(
                "duplicate kdenlive_id %r: %s overrides %s (last-wins)",
                effect.kdenlive_id,
                path,
                source_paths[effect.kdenlive_id],
            )
        effects_by_id[effect.kdenlive_id] = effect
        source_paths[effect.kdenlive_id] = path

    effects = sorted(effects_by_id.values(), key=lambda e: e.kdenlive_id)
    local_count = len(effects)
    local_ids = {e.kdenlive_id for e in effects}

    if not check_upstream:
        return effects, DiffReport(
            local_count=local_count,
            upstream_count=None,
            upstream_only_ids=(),
            local_only_ids=(),
            upstream_check="skipped",
        )

    upstream = fetch_upstream_effects()
    if upstream is None:
        return effects, DiffReport(
            local_count=local_count,
            upstream_count=None,
            upstream_only_ids=(),
            local_only_ids=(),
            upstream_check="failed",
        )

    upstream_set = set(upstream)
    return effects, DiffReport(
        local_count=local_count,
        upstream_count=len(upstream_set),
        upstream_only_ids=tuple(sorted(upstream_set - local_ids)),
        local_only_ids=tuple(sorted(local_ids - upstream_set)),
        upstream_check="ok",
    )


def _detect_source_version() -> str:
    """Best-effort detection of the installed Kdenlive version."""
    for cmd, parser in (
        (["pacman", "-Q", "kdenlive"], _parse_pacman_version),
        (["dpkg", "-s", "kdenlive"], _parse_dpkg_version),
    ):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5, check=False
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        version = parser(result.stdout)
        if version:
            return version
    return "unknown"


def _parse_pacman_version(stdout: str) -> str | None:
    # Format: "kdenlive 25.12.3-1"
    parts = stdout.strip().split()
    if len(parts) >= 2:
        return parts[1].split("-", 1)[0]
    return None


def _parse_dpkg_version(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("Version:"):
            raw = line.split(":", 1)[1].strip()
            # strip epoch (N:) and debian revision (-N)
            if ":" in raw:
                raw = raw.split(":", 1)[1]
            return raw.split("-", 1)[0]
    return None


def _render_param(param: ParamDef) -> str:
    return (
        "ParamDef("
        f"name={param.name!r}, "
        f"display_name={param.display_name!r}, "
        f"type=ParamType.{param.type.name}, "
        f"default={param.default!r}, "
        f"min={param.min!r}, "
        f"max={param.max!r}, "
        f"decimals={param.decimals!r}, "
        f"values={_render_tuple_of_str(param.values)}, "
        f"value_labels={_render_tuple_of_str(param.value_labels)}, "
        f"keyframable={param.keyframable!r}"
        ")"
    )


def _render_tuple_of_str(items: tuple[str, ...]) -> str:
    if not items:
        return "()"
    inner = ", ".join(repr(i) for i in items)
    if len(items) == 1:
        return f"({inner},)"
    return f"({inner})"


def _render_effect(effect: EffectDef) -> str:
    if not effect.params:
        params_block = "params=(),"
    else:
        lines = [f"            {_render_param(p)}," for p in effect.params]
        params_block = "params=(\n" + "\n".join(lines) + "\n        ),"
    return (
        f'    {effect.kdenlive_id!r}: EffectDef(\n'
        f"        kdenlive_id={effect.kdenlive_id!r},\n"
        f"        mlt_service={effect.mlt_service!r},\n"
        f"        display_name={effect.display_name!r},\n"
        f"        description={effect.description!r},\n"
        f"        category={effect.category!r},\n"
        f"        {params_block}\n"
        f"    ),"
    )


def _render_diff(report: DiffReport) -> str:
    return (
        "{"
        f'"local_count": {report.local_count!r}, '
        f'"upstream_count": {report.upstream_count!r}, '
        f'"upstream_only_ids": {report.upstream_only_ids!r}, '
        f'"local_only_ids": {report.local_only_ids!r}, '
        f'"upstream_check": {report.upstream_check!r}'
        "}"
    )


def emit_python_module(
    effects: list[EffectDef],
    output_path: pathlib.Path,
    source_version: str,
    diff_report: DiffReport,
    now: datetime.datetime | None = None,
) -> None:
    """Write a self-contained, importable Python module serialising ``effects``.

    The generated module re-declares ``ParamType``, ``ParamDef``, and
    ``EffectDef`` so it does not depend on this generator module at runtime.
    Output is sorted by ``kdenlive_id`` for byte-identical idempotency (given
    the same ``now``).
    """
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sorted_effects = sorted(effects, key=lambda e: e.kdenlive_id)

    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    generated_at = now.isoformat()

    param_type_members = ",\n    ".join(
        f'{m.name} = "{m.value}"' for m in ParamType
    )

    header = f'''"""GENERATED FILE -- do not edit by hand.

Regenerate with:
    python scripts/generate_effect_catalog.py
    # or
    uv run workshop-video-brain catalog regenerate

Source: Kdenlive {source_version} effects at /usr/share/kdenlive/effects/
"""
from __future__ import annotations

import dataclasses
import enum


class ParamType(str, enum.Enum):
    """Closed set of Kdenlive `<parameter type="...">` values."""

    {param_type_members}


@dataclasses.dataclass(frozen=True, slots=True)
class ParamDef:
    name: str
    display_name: str
    type: ParamType
    default: str | None
    min: float | None
    max: float | None
    decimals: int | None
    values: tuple[str, ...]
    value_labels: tuple[str, ...]
    keyframable: bool


@dataclasses.dataclass(frozen=True, slots=True)
class EffectDef:
    kdenlive_id: str
    mlt_service: str
    display_name: str
    description: str
    category: str
    params: tuple[ParamDef, ...]


__generated_at__ = {generated_at!r}
__source_version__ = {source_version!r}
__local_count__ = {len(sorted_effects)}
__upstream_diff__ = {_render_diff(diff_report)}


'''

    body_lines = ["CATALOG: dict[str, EffectDef] = {"]
    for eff in sorted_effects:
        body_lines.append(_render_effect(eff))
    body_lines.append("}")

    footer = '''


def find_by_name(name: str) -> EffectDef | None:
    """Look up an effect by its Kdenlive id (filename stem)."""
    return CATALOG.get(name)


def find_by_service(mlt_service: str) -> EffectDef | None:
    """Look up the first effect whose `mlt_service` (tag) matches."""
    for eff in CATALOG.values():
        if eff.mlt_service == mlt_service:
            return eff
    return None
'''

    content = header + "\n".join(body_lines) + footer
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, output_path)
