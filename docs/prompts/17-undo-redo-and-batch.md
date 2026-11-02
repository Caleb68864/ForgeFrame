# Prompt 17: undo/redo journal + atomic `timeline_batch` with rollback (Phase 4, harvest item 1)

Hand this whole file to the implementing model.

---

Give ForgeFrame a workspace-level **undo/redo stack**, built on the existing
snapshot machinery, plus an atomic **`timeline_batch`** tool. The batch runs a
list of tool calls and, if any one fails, rolls the workspace back to exactly
where it started. The idea comes from `12bijaya/MCP_Server_Kdenlive`. That
repo has **no licence**, so reimplement the ideas described below and never
copy code from it. Our storage model is different from theirs anyway (files on
disk, not an in-memory project).

Read `docs/prompts/00-README.md` first.

## The harvested ideas (prose only)

- Every mutating tool pushes a checkpoint of the project state **before** it
  runs. A new edit clears the redo stack. Undo pushes the current state onto
  redo and restores the top undo checkpoint. Redo is the mirror. The stack is
  capped (they use 50).
- Atomic batch: record the undo-stack **depth** before the batch, run the
  operations in order, and on the first failure undo repeatedly until the
  depth returns to the recorded value. They roll back **by depth, not by
  counting successful operations**, because a failing mutating operation may
  already have pushed a checkpoint (or, for us, written a file). Counting
  successes would under-roll-back.
- The batch result reports `failed_at_index`, the failing tool and its error,
  `rolled_back: true`, and `completed_before_failure`.

## How ForgeFrame writes projects today (verified)

- Every `.kdenlive` write goes through
  `adapters/kdenlive/serializer.py::serialize_project` (around line 414). It
  calls `workspace/safe_write.atomic_write_bytes` (around line 63), which:
  - holds `locked_path(target)`, a reentrant thread lock plus an `flock`;
  - **snapshots an existing target** via `workspace/snapshot.create`, into
    `projects/snapshots/<timestamp-slug>/<file>` + `metadata.yaml`. It then
    discards the returned `SnapshotRecord`.
- There are two write styles:
  - **In place.** About 27 tool and pipeline modules overwrite
    `project_file`. Examples: `effect_add` (`tools/effects_catalog.py`,
    around line 39) and `apply_simple_effect`
    (`tools_helpers/_effects.py`). Many also call `create_snapshot` manually
    first.
  - **New version.** `serialize_versioned` (around line 931) creates
    `working_copies/<slug>_v{N+1}.kdenlive` under
    `locked_path(working_copies)`. "Latest" is the highest `_vN`
    (`tools_helpers/_projects.latest_project`). It is used by `clip_*` and
    `track_*` (`tools/clips_nle.py`) and the transitions.
- `workspace/snapshot.restore` (around line 87) writes through
  `atomic_write_bytes` too.
- Detached jobs (`workspace/jobs.py`) pin the project's sha256 at submit time
  and allow one active job per workspace (`ACTIVE` statuses).
- Tools run in FastMCP's threadpool (`anyio.to_thread`); contextvars
  propagate there.

## Design (implement exactly this)

### 1. Journal module `workspace/undo.py`

- Storage: `projects/undo/journal.json`, written with
  `safe_write.atomic_write_text`. Shape:
  `{"version": 1, "undo": [Entry...], "redo": [RedoEntry...]}`.
- An `Entry` has:
  - `id` (uuid4 hex), `group` (str), `label` (str);
  - `path`, relative to the workspace root;
  - `kind`: `"overwrite"` or `"create"`;
  - `before_snapshot_id` (overwrite only), `after_sha256`, `created_at`.
- A `RedoEntry` is the same plus either `redo_snapshot_id` (overwrite) or
  `trash_path` (create), and `restored_sha256`.
- The **workspace edit lock** is `locked_path(<ws>/projects/undo/journal.json)`.
  Every journal read-modify-write holds it.
  - Lock order everywhere: `working_copies` dir lock (if any) -> journal
    lock -> target lock.
  - Never take the journal lock while holding only a target lock.
- Cap: keep the newest 50 **groups**. Dropped entries' snapshots stay on
  disk; never delete snapshots.
- `current_group: ContextVar[str | None]` and
  `current_label: ContextVar[str]`, with a context manager
  `edit_group(label)`. It sets a new group id **only if none is set**, so
  nested tool calls inside a batch inherit the batch's group.
- Functions:
  - `record_write(root, path, kind, before_snapshot_id, after_bytes)`:
    appends an entry and clears `redo`.
  - `undo(root, steps=1)` and `redo(root, steps=1)`.
  - `history(root, limit=20)`.
  - `depth(root)`: the number of undo groups.
  - `rollback_to(root, depth)`.

### 2. Capture the snapshot id

- Add a keyword `on_snapshot: Callable[[SnapshotRecord], None] | None = None`
  to `atomic_write_bytes`. Call it with the record that `create(...)`
  returns (around line 100). The default behaviour is unchanged.
- In `serialize_project`, after `atomic_write_bytes`:
  - if the workspace root has `workspace.yaml`, call `undo.record_write(...)`;
  - `kind` is `"overwrite"` when the target existed before the write
    (check before writing), else `"create"`.
  - Hold the journal lock around the write **and** the record, so the two
    are one atomic step.
  - Writes outside a workspace (tests in `tmp_path`) are not journaled.
- `snapshot.restore` should also journal (as `"overwrite"`, label
  `snapshot_restore:<id>`) so a restore is undoable.

### 3. Group every tool call

- In `edit_mcp/server/errors.py::tool_guard` (around line 499), wrap the
  call in `with undo.edit_group(fn.__name__):`.
- A tool that writes twice is then undone as one unit. Import lazily inside
  the wrapper; `errors.py` is imported very early.

### 4. Undo and redo semantics

Pop the **whole last group**, and preflight every entry before touching
anything.

- **Undo an overwrite.**
  - Preflight: `sha256(path) == after_sha256`. Otherwise raise
    `UndoConflict`, naming the file: "changed outside ForgeFrame (e.g.
    saved in Kdenlive) since that edit; use snapshot_list/snapshot_restore
    instead".
  - Apply: read the bytes from
    `projects/snapshots/<before_snapshot_id>/<filename>`, then
    `atomic_write_bytes(path, bytes, workspace_root=root, on_snapshot=<capture redo_snapshot_id>)`.
- **Undo a create.**
  - Preflight: same sha check.
  - Apply: `os.replace(path, projects/undo/trash/<entry id>__<name>)`. Never
    delete. "Latest" then falls back to the previous `_vN`.
- **Redo** mirrors both:
  - overwrite: preflight `sha256(path) == restored_sha256`, then write the
    redo snapshot's bytes;
  - create: preflight that `path` does not exist, then `os.replace` it back.
- Undo and redo must write through `atomic_write_bytes` directly, never
  `serialize_project`, so they do not journal themselves as new edits.
- Refuse undo and redo while the workspace has an active detached job:
  `jobs.list_jobs(root, reconcile=False)` with status in `jobs.ACTIVE`.
  Explain why: a render pinned the file's sha.
- `_next_version` will reuse a version number after an undone create. That
  is fine, because a new edit clears `redo`.

### 5. Tools

New module `edit_mcp/server/tools/history.py`. Every tool has
`workspace_path` first, and `@mcp.tool()` then `@tool_guard`.

- `project_undo(workspace_path, steps: int = 1)` returns
  `{"undone": [{"group", "label", "files": [...]}], "latest_project"}`.
  - `steps < 1` gives `invalid_input`.
  - An empty stack gives `invalid_input("Nothing to undo", ...)`.
  - `UndoConflict` gives `invalid_input` with the conflict message.
- `project_redo(workspace_path, steps: int = 1)` mirrors it.
- `project_history(workspace_path, limit: int = 20)` lists undo and redo
  groups: label, time, and files.
- `timeline_batch(workspace_path, operations: str, dry_run: bool = False)`.
  - `operations` is a JSON array (repo convention: JSON strings, so bad input
    gives `bad_json_param`).
  - Each item is `{"tool": "<name>", "args": {...}}`.
  - Validate every item before running anything:
    - the tool exists;
    - it is not on the denylist: `timeline_batch`, `project_undo`,
      `project_redo`, `snapshot_restore`, and any name starting with `job_`
      or `render_`;
    - its signature's first parameter is `workspace_path`;
    - `args` is a dict;
    - `args["workspace_path"]`, if present, resolves to the same workspace.
      Inject it when absent.
  - `dry_run=True` stops after validation and returns the resolved plan.
  - Execution: hold the journal lock (reentrant) for the whole batch, so no
    other writer interleaves. Then:
    1. Record `start = undo.depth(root)`.
    2. Inside `edit_group("timeline_batch")`, call each tool's underlying
       function **directly in this thread**: `tool.fn(**args)`.
    3. Treat a result whose `status != "success"` as a failure.
    4. On failure: `undo.rollback_to(root, start)`. It undoes groups until
       the depth returns to `start`, then drops the redo entries the
       rollback created, because a rollback is not redoable.
    5. Return `err(..., error_type=<inner error_type or "operation_failed">, failed_at_index=i, tool=name, inner_error=<inner payload>, rolled_back=True, completed_before_failure=i)`.
  - On success: `_ok({"group": ..., "results": [...], "count": n})`. One
    `project_undo` reverts the entire batch, because all inner writes share
    the batch group.
  - **Resolve tools without going through MCP dispatch.** Do NOT use
    `await mcp.call_tool(...)`: it re-enters FastMCP's threadpool, and the
    journal lock held by this thread would deadlock the other thread.
    - Get the `FunctionTool` with `asyncio.run(mcp.get_tool(name))`. In
      fastmcp 3.4.4 `get_tool` is a coroutine; the threadpool thread has no
      running loop, so `asyncio.run` is fine there.
    - If a loop *is* running (`asyncio.get_running_loop()` succeeds), run the
      lookup in a one-off `concurrent.futures.ThreadPoolExecutor(1)`.
    - Only the **lookup** happens off-thread. The call `tool.fn(**args)`
      always runs in the batch thread.
    - The tool name equals the function name; there are no custom
      `name=` registrations.
  - If the rollback itself raises `UndoConflict` (it should be impossible
    under the lock), return `operation_failed` with `rolled_back=False` and
    list the files left modified. Never report a fake success.

## Tests (all required)

Put them in `tests/unit/test_undo_journal.py` and
`tests/unit/test_timeline_batch.py`.

- Build a real workspace in `tmp_path`: `WorkspaceManager.create(...)`, or
  `create_workspace_structure` plus a manifest. Copy the pattern from
  `tests/unit/test_snapshot.py`.
- Serialize `sequence_project()` with `serialize_versioned`. Use hermetic
  versioned tools from `tools/clips_nle.py`: `track_add`, `clip_remove`,
  `clip_move`. Use `call_tool` from `tests/_testkit.py`.
- Cover:
  1. `track_add` creates v2, then `project_undo`: v2 is gone from
     `working_copies`, it is in `projects/undo/trash/`, and the latest is v1.
     `project_redo` brings v2 back byte-identical.
  2. An in-place write (`effect_add` with `brightness` on the latest file),
     then undo: the bytes equal the pre-edit bytes. Redo restores the
     post-edit bytes.
  3. A new edit after an undo clears redo (`project_redo` returns
     `invalid_input`).
  4. Edit the file by hand after a tool write. Undo returns a conflict
     error, and nothing changes on disk.
  5. `timeline_batch` of `[track_add, clip_remove(clip_index=99)]` fails at
     index 1. Check: `rolled_back` is true; the latest project is
     byte-identical to before; `undo.depth` equals the start depth; redo is
     empty.
  6. A successful batch of `[track_add, track_add]`: one `project_undo`
     returns to the pre-batch latest.
  7. Batch validation: an unknown tool, a denylisted tool, a foreign
     `workspace_path`, and bad JSON. Each fails **before** any write.
     `dry_run` returns the plan.
  8. An active job (insert a fake `running` record through the jobs SQLite
     helpers, with `_worker_alive` patched to True) blocks `project_undo`.
  9. Two threads calling `track_add` concurrently on the same workspace end
     with two journal groups and two distinct new versions, and no lost
     journal entry.
  10. Journal cap: 55 groups leaves 50.

## Acceptance criteria

- Every existing tool becomes undoable with no per-tool edits, through
  `serialize_project` + `tool_guard`.
- A failed batch leaves the working copies directory listing and the latest
  file's bytes exactly as before. Intermediate versions are in trash, not
  deleted.
- The full suite is green. Existing snapshot tests still pass. The journal
  adds no entry for writes outside a workspace.

## Do NOT

- Do not copy code or text from the harvest repo. Reimplement from this
  description.
- Do not delete any snapshot, working copy or trash file.
- Do not keep the undo stack only in memory. It must survive an MCP server
  restart.
- Do not call tools through `mcp.call_tool` inside the batch.
- Do not journal writes made by undo or redo themselves.
- Do not add a per-tool decorator to the 200+ tools. The choke points above
  cover them.
- Do not import harvest habits listed at the bottom of the expansion plan.

## When done

1. `docs/plans/2026-10-13-media-mcp-expansion.md`, Phase 4 item 1: mark it
   done. `docs/decisions.md`: add a dated entry on undo-by-journal (moving
   creates to trash versus writing new versions).
2. Add a vault note, `vault/wiki/forgeframe-undo-journal.md`. Cover:
   - group semantics;
   - the sha conflict rule;
   - lock order;
   - why rollback is by depth;
   - why the batch must not use `mcp.call_tool`.
3. Document `project_undo`, `project_redo`, `project_history` and
   `timeline_batch` (with a JSON example) in
   `docs/video-editing-guide/07-your-first-edit.md`.
4. Regenerate `docs/capabilities.md` (command in prompt 14 "When done").
5. Report per 00-README. Include the result of test 9 (concurrency), and any
   tool you found that writes a `.kdenlive` **without** `serialize_project`.
   Find them with:
   `grep -rn "\.kdenlive" workshop-video-brain/src | grep -E "write_(text|bytes)|open\("`.
