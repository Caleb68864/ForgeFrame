"""Effect-wrapper registration + the shared per-effect application body.

Home of ``register_effect_wrapper`` (the ``@mcp.tool()`` + traceability
decorator generated wrappers apply), the module-level ``__wrapped_effects__``
registry it appends to, the shared ``apply_simple_effect`` body every generated
wrapper delegates to, and the effect-catalog lookup by mlt_service.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.server.tools_helpers._responses import _ok, _err
from workshop_video_brain.edit_mcp.server.tools_helpers._workspace import (
    _require_workspace,
)


# ---------------------------------------------------------------------------
# Effect wrapper registration
# ---------------------------------------------------------------------------

__wrapped_effects__: list[str] = []


def register_effect_wrapper(fn):
    """Decorator combining `@mcp.tool()` + module-level export tracking.

    Generated effect wrapper modules apply this decorator so each wrapper
    function both registers with the FastMCP singleton and appears in the
    `__wrapped_effects__` list for traceability/testing.
    """
    from workshop_video_brain.server import mcp
    __wrapped_effects__.append(fn.__name__)
    return mcp.tool()(fn)


def apply_simple_effect(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    *,
    mlt_service: str,
    kdenlive_id: str,
    params: dict[str, object],
    keyframes: str = "",
) -> dict:
    """Shared body for the generated per-effect wrapper modules.

    Parses the project, builds a ``<filter>`` from ``mlt_service`` /
    ``kdenlive_id`` / ``params`` (bools -> "1"/"0", everything else ``str()``),
    snapshots before + after, inserts the effect at the end of the clip's stack,
    and serializes in place. Returns ``_ok({effect_index, snapshot_id})`` or an
    error dict. Extracted from ``effect_wrapper_gen`` so all wrappers share one
    implementation (previously inlined ~40x, byte-for-byte).
    """
    import xml.etree.ElementTree as ET

    from workshop_video_brain.edit_mcp.server.errors import err
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
        project_path = ws_path / project_file
        if not project_path.exists():
            return err(
                f"Project file not found: {project_file}",
                suggestion="Pass the path to an existing .kdenlive working copy; it resolves under the workspace root unless absolute. Run project_create_working_copy to make one.",
            )

        project = parse_project(project_path)

        filt = ET.Element("filter")
        svc = ET.SubElement(filt, "property", {"name": "mlt_service"})
        svc.text = mlt_service
        kid = ET.SubElement(filt, "property", {"name": "kdenlive_id"})
        kid.text = kdenlive_id

        for _mlt_name, _value in params.items():
            if isinstance(_value, bool):
                _str_val = "1" if _value else "0"
            else:
                _str_val = str(_value)
            _prop = ET.SubElement(filt, "property", {"name": _mlt_name})
            _prop.text = _str_val

        if keyframes:
            _kf = ET.SubElement(filt, "property", {"name": "keyframes"})
            _kf.text = keyframes

        xml_string = ET.tostring(filt, encoding="unicode")

        # Determine insertion index (end of stack)
        existing = patcher.list_effects(project, (track, clip))
        insert_index = len(existing)

        create_snapshot(
            ws_path,
            project_path,
            description=f"before_effect_{kdenlive_id}",
        )
        patcher.insert_effect_xml(project, (track, clip), xml_string, insert_index)
        snap = create_snapshot(
            ws_path,
            project_path,
            description=f"after_effect_{kdenlive_id}",
        )
        serialize_project(project, project_path)

        return _ok({
            "effect_index": insert_index,
            "snapshot_id": snap.snapshot_id,
        })
    except (ValueError, FileNotFoundError, IndexError) as exc:
        return _err(str(exc))


def _lookup_catalog_by_service(mlt_service: str):
    """Return (kdenlive_id, EffectDef) for a given mlt_service, else (None, None)."""
    try:
        from workshop_video_brain.edit_mcp.pipelines import effect_catalog as _catalog
    except ModuleNotFoundError:
        return None, None
    for kid, eff in _catalog.CATALOG.items():
        if eff.mlt_service == mlt_service:
            return kid, eff
    return None, None
