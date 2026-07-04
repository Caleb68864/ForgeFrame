"""Proxy-wiring MCP tools -- §3 Medium "Proxy wiring".

``proxy_generate`` writes proxy files under ``media/proxies/`` but never wires
them into the project, so Kdenlive ignores them.  These tools close that gap:

- ``proxy_attach`` -- set ``resource``/``kdenlive:proxy``/``kdenlive:originalurl``
  on producers and enable the ``kdenlive:docproperties.*`` proxy settings so
  Kdenlive uses the generated proxies.  Snapshots the project first.
- ``proxy_detach`` -- revert producers to their originals.
- ``proxy_status`` -- read-only per-producer proxy report.

Because the saved-file ``resource`` points at the proxy (verified against KDE
source), full-res renders swap back to originals -- see
``pipelines/render_pipeline.run_render`` and the analysis at
``docs/research/2026-07-03-tutorial-effect-analysis/proxy-wiring.md``.

Auto-imported by ``server/bundles/__init__``; registers via ``@mcp.tool()``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    invalid_input,
    bad_json_param,
    corrupt_project,
    operation_failed,
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)
from workshop_video_brain.edit_mcp.pipelines import proxy_wiring as pw
from workshop_video_brain.workspace import create_snapshot


# ---------------------------------------------------------------------------
# Path helpers (mirrors server/bundles/subtitle_track.py)
# ---------------------------------------------------------------------------

def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _find_workspace_root(start: Path) -> Path | None:
    candidates = [start] if start.is_dir() else []
    candidates.extend(start.parents)
    for parent in candidates:
        if (parent / "workspace.yaml").exists():
            return parent
    return None


def _resolve_project(workspace_path: str, project_file: str) -> Path:
    ws = Path(workspace_path)
    if project_file:
        p = _resolve(project_file)
        if p.exists():
            return p
        candidate = ws / "projects" / "working_copies" / project_file
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Project file not found: {project_file}")
    working = ws / "projects" / "working_copies"
    files = sorted(working.glob("*.kdenlive")) if working.exists() else []
    if not files:
        raise FileNotFoundError(
            "No project_file given and no .kdenlive in projects/working_copies/"
        )
    return files[-1]


def _proxy_dir(ws: Path) -> Path:
    return ws / "media" / "proxies"


# ---------------------------------------------------------------------------
# proxy_attach
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def proxy_attach(
    workspace_path: str,
    project_file: str = "",
    source: str = "",
    proxy_path: str = "",
    all_clips: bool = False,
) -> dict:
    """Wire existing proxy files into a Kdenlive project so Kdenlive uses them.

    Sets each targeted producer's ``resource``/``kdenlive:proxy`` to the proxy
    file and ``kdenlive:originalurl`` to the original source, and enables the
    project ``kdenlive:docproperties`` proxy settings.  Snapshots first.  Full-res
    renders swap back to originals automatically.

    Args:
        workspace_path: Path to the workspace root directory.
        project_file: .kdenlive path (absolute, cwd-relative, or a bare filename
            under projects/working_copies/).  Empty = latest working copy.
        source: Restrict to the producer(s) whose original source matches this
            path.  Empty = every video producer.
        proxy_path: Explicit proxy file (only with a single-clip ``source``).
            Empty = match ``proxy_generate`` naming ``{stem}_proxy.mp4`` under
            ``media/proxies/``.
        all_clips: Operate over every video producer (default already does when
            ``source`` is empty; kept for explicit intent).

    Returns a success dict with per-producer attach/skip report.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).")
        ws = Path(workspace_path)
        if not ws.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).", path=workspace_path)

        project_path = _resolve_project(workspace_path, project_file)
        project = parse_project(project_path)

        _, report = pw.attach_proxies(
            project,
            _proxy_dir(ws),
            source=source,
            proxy_path=proxy_path,
            all_clips=all_clips,
        )

        if not report.attached:
            return err(
                "No proxies were wired: none of the clips had a matching proxy file. "
                f"missing_proxy_files={report.skipped_missing_proxy or 'none'}",
                suggestion="Run proxy_generate first to create proxies, or pass an explicit proxy_path.",
            )

        ws_root = _find_workspace_root(project_path) or ws
        create_snapshot(ws_root, project_path, description="before_proxy_attach")
        serialize_project(project, project_path)
        snap = create_snapshot(
            ws_root, project_path, description="after_proxy_attach"
        )

        return _ok(
            {
                "project_file": str(project_path),
                "attached": report.attached,
                "skipped_missing_proxy": report.skipped_missing_proxy,
                "enableproxy": project.docproperties.get("enableproxy", "0"),
                "proxyparams": project.docproperties.get("proxyparams", ""),
                "snapshot_id": snap.snapshot_id,
            }
        )
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")


# ---------------------------------------------------------------------------
# proxy_detach
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def proxy_detach(
    workspace_path: str,
    project_file: str = "",
    source: str = "",
    all_clips: bool = False,
) -> dict:
    """Revert producers to their original sources (undo ``proxy_attach``).

    Args:
        workspace_path: Path to the workspace root directory.
        project_file: .kdenlive path or empty for the latest working copy.
        source: Restrict to producer(s) matching this original source.  Empty =
            every proxied producer.
        all_clips: Kept for explicit intent (default already detaches all).

    Returns a success dict with the per-producer detach report.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).")
        ws = Path(workspace_path)
        if not ws.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).", path=workspace_path)

        project_path = _resolve_project(workspace_path, project_file)
        project = parse_project(project_path)

        _, report = pw.detach_proxies(project, source=source, all_clips=all_clips)

        if not report.detached:
            return err("No proxied producers to detach; this project has no proxies wired.", suggestion="This is only meaningful after proxies have been attached with the proxy wiring step.")

        ws_root = _find_workspace_root(project_path) or ws
        create_snapshot(ws_root, project_path, description="before_proxy_detach")
        serialize_project(project, project_path)
        snap = create_snapshot(
            ws_root, project_path, description="after_proxy_detach"
        )

        return _ok(
            {
                "project_file": str(project_path),
                "detached": report.detached,
                "unchanged": report.unchanged,
                "enableproxy": project.docproperties.get("enableproxy", "0"),
                "snapshot_id": snap.snapshot_id,
            }
        )
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")


# ---------------------------------------------------------------------------
# proxy_status
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def proxy_status(workspace_path: str, project_file: str = "") -> dict:
    """Report per-producer proxy state (read-only).

    For each video producer: its original source, its wired proxy (if any),
    whether a proxy is active, and whether the proxy file exists on disk.

    Args:
        workspace_path: Path to the workspace root directory.
        project_file: .kdenlive path or empty for the latest working copy.

    Returns a success dict with the per-producer report and a summary.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).")
        ws = Path(workspace_path)
        if not ws.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", suggestion="Pass an existing workspace directory (the folder that holds workspace.yaml).", path=workspace_path)

        project_path = _resolve_project(workspace_path, project_file)
        project = parse_project(project_path)

        rows = pw.proxy_status(project, _proxy_dir(ws))
        producers = [
            {
                "producer_id": r.producer_id,
                "original": r.original,
                "proxy": r.proxy,
                "proxied": r.proxied,
                "proxy_file_exists": r.proxy_file_exists,
                "missing_proxy_file": r.proxied and not r.proxy_file_exists,
            }
            for r in rows
        ]
        proxied = sum(1 for r in rows if r.proxied)
        missing = sum(1 for r in rows if r.proxied and not r.proxy_file_exists)

        return _ok(
            {
                "project_file": str(project_path),
                "enableproxy": project.docproperties.get("enableproxy", "0"),
                "producers": producers,
                "proxied_count": proxied,
                "missing_proxy_count": missing,
                "total_video_producers": len(rows),
            }
        )
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
