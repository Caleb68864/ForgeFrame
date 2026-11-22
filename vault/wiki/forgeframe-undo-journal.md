# ForgeFrame undo journal

`workspace/undo.py`, tools in `edit_mcp/server/tools/history.py`. Added 2026-11-21 (prompt 17).

## What is recorded

Every `.kdenlive` write `serialize_project` makes inside a workspace (a directory with `workspace.yaml`), and every `snapshot.restore`, appends an entry to `projects/undo/journal.json`:

- `overwrite`: the file existed; `atomic_write_bytes` snapshotted it and passed the record to `on_snapshot`, so the entry keeps `before_snapshot_id`.
- `create`: a new file (a `_vN` working copy).

Both keep `after_sha256`, the hash of the bytes written. Writes outside a workspace are not journaled. Undo and redo write through `atomic_write_bytes` directly, so they never journal themselves.

## Groups

`tool_guard` wraps every tool call in `undo.edit_group(<tool name>)`. A group id is set only if none is set, so every write in one call -- and every call inside a `timeline_batch` -- shares one group, and undo/redo move whole groups. The stack keeps the newest 50 groups; dropped entries' snapshots stay on disk.

## The sha conflict rule

An entry is undone only if the file's current sha256 equals `after_sha256` (redo: equals `restored_sha256`, or the file is absent for a create). Anything else means the file changed outside ForgeFrame -- typically saved in Kdenlive -- and undo raises `UndoConflict` before touching anything. Every entry of the group is preflighted first, simulating the contents so a group that wrote one file twice checks each step against what the previous step would leave.

## Lock order

`working_copies` directory lock -> journal lock -> target lock, everywhere. `serialize_versioned` holds the first when `serialize_project` takes the second; `undo.edit_lock` takes the first two for undo, redo and the whole of `timeline_batch`. Never take the journal lock while holding only a target lock.

## Why a batch rolls back by depth

`timeline_batch` records `undo.depth()` before it starts and, on the first failure, undoes until the depth is back. Counting successful operations would under-roll-back: a failing operation may already have written (and journaled) a file before it returned its error. The rollback then drops the redo entries it created, since a rollback is not redoable.

## Why the batch must not use `mcp.call_tool`

`mcp.call_tool` dispatches the tool to FastMCP's threadpool. The batch thread holds the (reentrant, per-thread) journal and working_copies locks for the whole batch, so a tool running on another thread would block on them forever. The batch looks the tool up with `mcp.get_tool` and calls `tool.fn(**args)` in its own thread.

## Active jobs

Undo/redo refuse while a detached job with a live worker is `queued`/`running`/`cancelling`: the job pinned the project's sha256 when it was submitted. The worker's liveness is checked because `list_jobs(reconcile=False)` would otherwise let a crashed worker's record block undo for ever.
