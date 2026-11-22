"""Undo/redo, edit history and the atomic ``timeline_batch`` tool.

All four sit on the workspace journal in ``workspace/undo.py``: every
``.kdenlive`` write inside a workspace is recorded there, grouped per tool
call by ``tool_guard``, so no tool needs its own undo code.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    OPERATION_FAILED,
    bad_json_param,
    err,
    from_exception,
    invalid_input,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _validate_workspace_path,
)

# Tools a batch may not run: history/rollback tools would fight the batch's own
# rollback; job_* and render_* start long work the batch cannot take back.
_BATCH_DENY = {"timeline_batch", "project_undo", "project_redo", "snapshot_restore"}
_BATCH_DENY_PREFIXES = ("job_", "render_")
_BATCH_EXAMPLE = '[{"tool": "track_add", "args": {"track_type": "video"}}]'


def _latest(ws_root: Path) -> str | None:
    from workshop_video_brain.edit_mcp.server.tools_helpers._projects import latest_project
    found = latest_project((ws_root / "projects" / "working_copies").glob("*.kdenlive"))
    return str(found) if found else None


def _history_errors(exc: Exception, which: str) -> dict:
    from workshop_video_brain.workspace import undo as _undo
    if isinstance(exc, _undo.NothingToUndo):
        return invalid_input(
            f"Nothing to {which}",
            "project_history shows what can be undone and redone. "
            + ("A new edit after an undo clears the redo stack." if which == "redo"
               else "Only edits ForgeFrame made in this workspace are journaled."),
        )
    if isinstance(exc, _undo.UndoConflict):
        return invalid_input(str(exc), "Use snapshot_list and snapshot_restore to pick a version by hand.")
    if isinstance(exc, _undo.UndoBlocked):
        return invalid_input(str(exc), "Wait for the job (job_status) or cancel it (job_cancel), then retry.")
    return from_exception(exc)


def _step_tool(workspace_path: str, steps: int, which: str) -> dict:
    from workshop_video_brain.workspace import undo as _undo
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        return invalid_input(f"steps must be a whole number >= 1, got {steps!r}",
                             "Pass steps=1 to step back one edit.", param="steps", given=steps)
    try:
        ws_root = _validate_workspace_path(workspace_path)
        done = (_undo.undo if which == "undo" else _undo.redo)(ws_root, steps)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        return _history_errors(exc, which)
    key = "undone" if which == "undo" else "redone"
    return _ok({key: done, "latest_project": _latest(ws_root)})


@mcp.tool()
@tool_guard
def project_undo(workspace_path: str, steps: int = 1) -> dict:
    """Undo the last edit(s) ForgeFrame made to this workspace's projects.

    One step undoes one tool call (a whole ``timeline_batch`` is one step). A
    new version a tool wrote is moved to ``projects/undo/trash/`` (never
    deleted); an in-place edit is put back from its snapshot. Refused, with
    nothing changed, when a file was edited outside ForgeFrame since (e.g.
    saved in Kdenlive) or while a detached job is running.

    Args:
        workspace_path: Path to the workspace root.
        steps: How many edits to undo (default 1).

    Returns:
        ``undone`` (group, label, files per step) and ``latest_project``.
    """
    return _step_tool(workspace_path, steps, "undo")


@mcp.tool()
@tool_guard
def project_redo(workspace_path: str, steps: int = 1) -> dict:
    """Redo edit(s) undone with project_undo. A new edit clears the redo stack.

    Args:
        workspace_path: Path to the workspace root.
        steps: How many undone edits to redo (default 1).

    Returns:
        ``redone`` (group, label, files per step) and ``latest_project``.
    """
    return _step_tool(workspace_path, steps, "redo")


@mcp.tool()
@tool_guard
def project_history(workspace_path: str, limit: int = 20) -> dict:
    """List the edits project_undo and project_redo would step through, newest first.

    Args:
        workspace_path: Path to the workspace root.
        limit: Maximum entries per list (default 20).

    Returns:
        ``undo`` and ``redo`` lists (group, label, files, created_at).
    """
    from workshop_video_brain.workspace import undo as _undo
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return invalid_input(f"limit must be a whole number >= 1, got {limit!r}",
                             "Pass limit=20.", param="limit", given=limit)
    try:
        ws_root = _validate_workspace_path(workspace_path)
        return _ok(_undo.history(ws_root, limit))
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)


# ---------------------------------------------------------------------------
# timeline_batch
# ---------------------------------------------------------------------------

def _lookup_tool(name: str):
    """The registered FunctionTool for *name*, or None.

    Lookup only: the batch then calls ``tool.fn`` in its own thread. Going
    through ``mcp.call_tool`` would hop to FastMCP's threadpool, where the
    journal lock this thread holds would deadlock it.
    """
    coro_factory = lambda: mcp.get_tool(name)  # noqa: E731
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        result = coro_factory()
        return asyncio.run(result) if inspect.isawaitable(result) else result
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        def run():
            result = coro_factory()
            return asyncio.run(result) if inspect.isawaitable(result) else result
        return pool.submit(run).result()


def _plan(ws_root: Path, operations: str) -> tuple[list[dict] | None, dict | None]:
    """Validate every operation before anything runs. Returns (plan, error)."""
    try:
        items = json.loads(operations)
    except (TypeError, ValueError):
        return None, bad_json_param("operations", _BATCH_EXAMPLE, str(operations)[:200])
    if not isinstance(items, list) or not items:
        return None, invalid_input("operations must be a non-empty JSON array",
                                   f"Pass e.g. {_BATCH_EXAMPLE}", param="operations")
    plan = []
    for index, item in enumerate(items):
        where = f"operations[{index}]"
        if not isinstance(item, dict) or not isinstance(item.get("tool"), str):
            return None, invalid_input(f"{where} must be an object with a 'tool' name",
                                       f"Pass e.g. {_BATCH_EXAMPLE}", index=index)
        name = item["tool"]
        args = item.get("args", {})
        if not isinstance(args, dict):
            return None, invalid_input(f"{where}.args must be an object", f"Pass e.g. {_BATCH_EXAMPLE}",
                                       index=index, tool=name)
        if name in _BATCH_DENY or name.startswith(_BATCH_DENY_PREFIXES):
            return None, invalid_input(
                f"{where}: {name} cannot run inside a batch",
                "Undo/redo, snapshot_restore, job_* and render_* tools change or start work "
                "the batch's rollback cannot take back. Run them on their own.",
                index=index, tool=name,
            )
        tool = _lookup_tool(name)
        if tool is None:
            return None, invalid_input(f"{where}: unknown tool {name!r}",
                                       "Use a tool name exactly as registered (see forgeframe_capabilities).",
                                       index=index, tool=name)
        params = list(inspect.signature(tool.fn).parameters)
        if not params or params[0] != "workspace_path":
            return None, invalid_input(
                f"{where}: {name} does not take workspace_path first, so it is not a workspace edit",
                "Only workspace tools (workspace_path as the first parameter) can run in a batch.",
                index=index, tool=name,
            )
        given = args.get("workspace_path")
        if given is not None and Path(str(given)).resolve() != ws_root:
            return None, invalid_input(
                f"{where}: workspace_path {given!r} is not this batch's workspace",
                "A batch edits one workspace; drop workspace_path from args or make it match.",
                index=index, tool=name,
            )
        unknown = set(args) - set(params)
        if unknown and not any(p.kind is p.VAR_KEYWORD for p in inspect.signature(tool.fn).parameters.values()):
            return None, invalid_input(
                f"{where}: {name} has no parameter(s) {', '.join(sorted(unknown))}",
                f"{name} takes: {', '.join(params)}.", index=index, tool=name,
            )
        plan.append({"tool": name, "args": {**args, "workspace_path": str(ws_root)}, "_fn": tool.fn})
    return plan, None


@mcp.tool()
@tool_guard
def timeline_batch(workspace_path: str, operations: str, dry_run: bool = False) -> dict:
    """Run several workspace edits as one step: all of them, or none.

    Every operation is validated before any runs. They then run in order; if
    one fails, every file the batch wrote is put back (new versions go to
    ``projects/undo/trash/``) and the workspace is exactly as before. A
    successful batch is one ``project_undo`` step.

    Args:
        workspace_path: Path to the workspace root.
        operations: JSON array of ``{"tool": "<name>", "args": {...}}``; for
            example ``[{"tool": "track_add", "args": {"track_type": "video"}},
            {"tool": "clip_move", "args": {"from_index": 0, "to_index": 1}}]``.
            ``workspace_path`` is filled in for each operation.
        dry_run: Validate and return the plan without running anything.

    Returns:
        ``group``, ``count`` and each operation's ``results``; on failure an
        error with ``failed_at_index``, ``tool``, ``inner_error``,
        ``rolled_back`` and ``completed_before_failure``.
    """
    from workshop_video_brain.workspace import undo as _undo
    try:
        ws_root = _validate_workspace_path(workspace_path).resolve()
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    if not _undo.is_workspace(ws_root):
        return invalid_input(
            f"{ws_root} has no workspace.yaml, so its edits are not journaled and a failed batch could not be rolled back",
            "Point workspace_path at a ForgeFrame workspace (workspace_create makes one).",
            path=str(ws_root),
        )
    plan, problem = _plan(ws_root, operations)
    if problem is not None:
        return problem
    steps = [{"tool": p["tool"], "args": p["args"]} for p in plan]
    if dry_run:
        return _ok({"dry_run": True, "plan": steps, "count": len(steps)})

    # Held for the whole batch so no other writer interleaves; reentrant, so
    # the inner tools' own working_copies/journal locks pass straight through.
    with _undo.edit_lock(ws_root), _undo.edit_group("timeline_batch") as group:
        start = _undo.depth(ws_root)
        results = []
        for index, step in enumerate(plan):
            try:
                result = step["_fn"](**step["args"])
            except Exception as exc:  # noqa: BLE001 -- tool_guard normally catches; belt and braces
                result = from_exception(exc)
            if not isinstance(result, dict) or result.get("status") != "success":
                inner = result if isinstance(result, dict) else {"message": repr(result)}
                try:
                    _undo.rollback_to(ws_root, start)
                except Exception as exc:  # noqa: BLE001 -- must never report a fake success
                    left = _undo.files_above(ws_root, start)
                    payload = err(
                        f"timeline_batch failed at operation {index} ({step['tool']}) and the "
                        f"rollback also failed: {exc}",
                        error_type=OPERATION_FAILED,
                        suggestion="Use project_history and snapshot_list to put the files back by hand.",
                        failed_at_index=index, tool=step["tool"], inner_error=inner,
                        rolled_back=False, completed_before_failure=index,
                        files_left_modified=left,
                    )
                    return payload
                return err(
                    f"timeline_batch failed at operation {index} ({step['tool']}): "
                    f"{inner.get('message', 'failed')}. Nothing was changed: the batch was rolled back.",
                    error_type=inner.get("error_type") or OPERATION_FAILED,
                    suggestion=inner.get("suggestion") or "Fix that operation and rerun the batch.",
                    failed_at_index=index, tool=step["tool"], inner_error=inner,
                    rolled_back=True, completed_before_failure=index,
                )
            results.append({"tool": step["tool"], "result": result.get("data")})
    return _ok({"group": group, "results": results, "count": len(results)})
