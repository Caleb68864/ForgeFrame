# Prompt 14: MLT bindings worker + project load-check (expansion Phase 3)

Hand this whole file to the implementing model.

---

Add an **out-of-process MLT worker** that loads a `.kdenlive` file with the
real MLT engine (`import mlt7`) and reports what MLT actually built: profile,
tracks, playlists, and every clip's in, out and start. Then compare that with
our own parsed model (`KdenliveProject`) and surface the differences as a
**load-check** in `project_validate`. When the bindings are missing, fall back
to the `melt` CLI. Also add a doctor row, a `requires_mlt_bindings` test mark,
and an optional post-write check. Prompts 15 and 16 build on this worker, so
get the protocol right.

Read `docs/prompts/00-README.md` first.

## Background (verified on this machine, 2026-10-14)

- The bindings exist only for the **system** Python 3.14
  (`/usr/lib/python3.14/site-packages/mlt7.py` + `_mlt7.so`, MLT 7.42.0).
  - The project venv is uv CPython 3.12, so `import mlt7` there fails: either
    `ModuleNotFoundError`, or an ABI error (`PyImport_AddModuleRef`) if
    someone adds the 3.14 path.
  - They are not on PyPI, conda-forge is stuck at MLT 6.24, and there are
    none for Windows or macOS.
  - Ubuntu 24.04 `python3-mlt` (MLT 7.22) targets its system Python 3.12.
    That is the CI case.
  - Therefore the worker **always** runs as a separate process, never in-process.
- The bindings **segfault** on bad handles or on wrappers built from
  garbage-collected temporaries. A segfault must come back as a reported
  failure, never as a hang or a dead MCP server.
- MLT prints about 170 lines of noise to **stderr** on every init
  (`mlt_repository_register: Duplicate filter registration ...`, `failed to
  dlopen libmltrtaudio.so / libmltmovit.so`). Some C code may also write to
  fd 1, so the worker must protect its protocol channel (see below).
- `is_valid()` is **true even when a clip's media file is missing**. MLT only
  logs `[producer_xml] failed to load chain "<path>"` on stderr. Missing media
  is already covered by `adapters/render/media_check` through
  `validate_project`. Do not duplicate it; turn those stderr lines into
  warnings only.
- `frame.get_image(fmt, 0, 0)` returns an **empty** buffer. Always pass
  explicit width and height (prompt 15 needs this).

### Working API (tested against `tests/_testkit.sequence_project` output and `tests/fixtures/kdenlive_references/cross_dissolve_native.kdenlive`)

```python
import os, sys, json
proto = os.fdopen(os.dup(1), "w", buffering=1)  # private copy of real stdout
os.dup2(2, 1)                                    # C-level stdout now goes to stderr
import mlt7 as mlt                               # (try `import mlt` as fallback)
mlt.Factory.init()
INT_MAX = 2147483647
prof = mlt.Profile()                             # filled from the doc's <profile>
root = mlt.Producer(prof, "xml", path)           # keep `prof` and `root` alive!
mt = mlt.Multitrack(root.producer())             # bind every intermediate to a name
first = mt.track(0)
par = first.parent() if first.is_cut() else first
seq = mlt.Tractor(par) if par.is_valid() and par.type() == mlt.mlt_service_tractor_type \
      else mlt.Tractor(root.producer())
# prof.width(), prof.height(), prof.frame_rate_num(), prof.frame_rate_den()
# (prof.description() is stale -- do not use it)
for i in range(seq.count()):
    t = seq.track(i)                              # may be None / invalid
    # t.get("id"); t.get_length(); t.type()
    # black_track: type == producer (2), length == INT_MAX -> skip
    if t.type() == mlt.mlt_service_tractor_type:  # per-track tractor (E-shape)
        tt = mlt.Tractor(t)
        for j in range(tt.count()):
            pt = tt.track(j)
            if pt is None or not pt.is_valid() or pt.type() != mlt.mlt_service_playlist_type:
                continue
            pl = mlt.Playlist(pt)                 # pl.get("id") == XML playlist id
            for k in range(pl.count()):
                if pl.is_blank(k):
                    continue
                ci = pl.clip_info(k)
                # ci.start, ci.frame_in, ci.frame_out, ci.resource,
                # ci.producer.get("id")  == XML producer/chain id of the entry,
                # ci.producer.get("kdenlive:id"), ci.producer.get("mlt_service")
```

- Service type constants: producer=2, tractor=3, playlist=4,
  multitrack=5, filter=6, transition=7, link=10, chain=11.
- A track can also be a plain playlist (legacy flat MLT). Handle
  `t.type() == playlist` by treating `t` itself as the playlist.
- `ci.resource` is resolved against the document `root`, so a `color`
  producer shows up as `<root>/0xff0000ff`. Never stat resources of non-file
  services.

## Steps

### 1. `edit_mcp/adapters/mlt/_worker.py` (stdlib + mlt only)

- It runs under a foreign interpreter with `-I`, so `sys.path` has no repo
  code and no script directory. It must import **nothing** from
  `workshop_video_brain`.
- Keep the syntax compatible with Python 3.10.
- Protocol:
  - Read **one** JSON request line from stdin:
    `{"protocol": 1, "op": "...", "args": {...}}`.
  - Write newline-delimited JSON to the private `proto` handle:
    - zero or more `{"event": "progress", ...}` lines (prompt 15 uses them);
    - then exactly one final line, either `{"ok": true, "result": {...}}` or
      `{"ok": false, "error": {"type": "...", "message": "..."}}`.
  - Exit 0 after the final line. Catch exceptions inside the worker and
    report them as `ok: false`.
- Ops for this prompt:
  - `ping` returns `{"protocol": 1, "mlt_version": mlt.mlt_version_get_string(), "python": sys.version.split()[0], "module": "mlt7"}`.
  - `inspect` (args `{"path"}`) returns the walker output above as JSON:
    profile, `sequence_id`, and tracks with their playlists and clips.
- Bind every MLT object to a local name for the whole op (segfault rule).
- Put a dispatch dict `OPS = {"ping": ..., "inspect": ...}` at the bottom.
  Prompts 15 and 16 add ops to it.

### 2. `edit_mcp/adapters/mlt/engine.py`

Also create `adapters/mlt/__init__.py`. It is a new package, so it may have a
docstring only.

- Exceptions:
  - `MltUnavailable(RuntimeError)`;
  - `MltWorkerError(RuntimeError)`, with the stderr tail attached;
  - `MltWorkerCrashed(MltWorkerError)`, when the return code is negative,
    meaning a signal. Name the signal with `signal.Signals(-rc).name`.
- `find_mlt_python(refresh=False) -> MltInterpreter | None`. `MltInterpreter`
  is a dataclass with `path`, `mlt_version` and `python_version`.
  - If `WVB_MLT_PYTHON` is set, try **only** that interpreter. Explicit
    config must never silently fall back.
  - Otherwise try `sys.executable`, then `/usr/bin/python3`. Skip missing
    paths and dedupe by `os.path.realpath`.
  - Probe each candidate with the `ping` op, using
    `CAPABILITY_TIMEOUT_SECONDS` from `adapters/ffmpeg/runner.py`.
  - Cache the result in a module global guarded by a `threading.Lock`.
    `refresh=True` re-probes.
  - Reject a ping whose `protocol` differs.
- `run_worker(op, args, *, timeout, on_event=None) -> dict`.
  - Command: `[interp.path, "-I", str(Path(__file__).with_name("_worker.py"))]`.
  - Pass the environment through: `DISPLAY` matters, because MLT 7.22's Qt
    module needs X11 and `QT_QPA_PLATFORM=offscreen` does not satisfy it.
  - One-shot ops use `subprocess.run(..., input=json, capture_output=True, text=True, timeout=timeout)`.
  - Parse the stdout lines. Call `on_event` for each `event` line. Return
    `result` from the final line.
  - Raise `MltWorkerError` on `ok: false`, a non-zero exit, or no final line.
  - Strip the MLT noise from the stderr tail you attach: drop lines starting
    with `mlt_repository_register: Duplicate`, and the dlopen pair.
  - `TimeoutExpired` propagates; `tool_guard` already classifies it.
- `load_check(project_path, model, engine="auto") -> LoadCheckResult`.
  - `LoadCheckResult` is a dataclass with `engine` (`"bindings"`, `"melt"` or
    `"skipped"`), `items: list[ValidationItem]` and `reason: str`.
  - The comparison logic lives in a pure function
    `compare_inspection(inspection: dict, model: KdenliveProject) -> list[ValidationItem]`
    so unit tests can feed it canned JSON.
- **Melt fallback** (no bindings, `shutil.which("melt")` present):
  - Command: `melt <project> out=0 -consumer null: terminate_on_pause=1`.
    The `out=0` bounds it to one frame.
  - Timeout: a local `_LOAD_TIMEOUT_SECONDS = 120`.
  - Each stderr line matching `failed to load` becomes a `warning`.
  - A non-zero exit becomes an `error`.
  - The fallback cannot compare structure. Say so in `reason`.
- Neither engine available: return `engine="skipped"` with one `info` item.

### 3. Comparison rules (`compare_inspection`)

Every item uses `category="load_check"`.

- **Profile.** Width and height must match exactly, and
  `abs(num/den - model.profile.fps) < 1e-3`. A mismatch is an `error`.
- **Playlists.** Match each model playlist (`model.playlists`) by `id`
  against the playlists found inside the MLT tracks.
  - A model playlist that is absent in MLT, but has entries, is an `error`.
  - An MLT playlist missing from the model is fine when it is empty or its id
    ends in `_kdpair`. Otherwise it is a `warning`.
- **Clips.** Compare the model's non-blank entries in order
  (`producer_id != ""`) with the MLT clips of that playlist.
  - A different count is an `error`.
  - For each pair, compare `in`, `out`, and the **timeline start**. Compute
    the model start as the sum of `out_point - in_point + 1` over all
    preceding entries, blanks included. Any difference is an `error` that
    names the playlist, the clip index and both values.
  - A different `producer_id` (MLT `ci.producer.get("id")`) is a `warning`.
- **Sequence.** MLT reported no sequence tracks at all: `error`.
- **Crash.** If the worker crashes (`MltWorkerCrashed`), return an `error`
  item: "MLT crashed while loading this project (SIGSEGV) -- the file
  probably references something MLT cannot build". Do not let it propagate.

### 4. Wire into `project_validate`

`edit_mcp/server/tools/timeline_project.py`, around line 223.

- Add the parameter `load_check: bool = True`.
- After `validate_project(...)` (around line 255), when `load_check` is true,
  call `engine.load_check(latest, project)`. Append its items to the report
  and recompute the summary the same way `validate_project` builds it.
  Factor that summary builder into a small helper in `validator.py` instead
  of copying it.
- Add `"load_check": {"engine": ..., "reason": ...}` to the `_ok` payload.

### 5. Optional post-write check

At the end of `serialize_project` (`adapters/kdenlive/serializer.py`, around
line 920, after `atomic_write_bytes`):

- When the env var `WVB_LOAD_CHECK_ON_WRITE=1` is set, run
  `load_check(output_path, project)` and `logger.warning` each error or
  warning item.
- It must **never raise**: the write already succeeded. Catch everything,
  including `TimeoutExpired`, and log it.
- Default: off.

### 6. Inspection tool (plan item 5, small)

Add `edit_mcp/server/bundles/mlt_inspect.py` with a tool
`project_mlt_inspect(workspace_path: str, project_file: str = "")`.

- It returns the raw `inspect` JSON for parser debugging.
- Without bindings it returns `missing_dependency(...)`, with the hint
  "install your distro's python3-mlt / mlt python bindings, or set
  WVB_MLT_PYTHON".

### 7. Doctor row (`app/doctor.py`)

- Add `'mlt_bindings': {'available', 'python', 'mlt_version', 'error'}`,
  using `find_mlt_python(refresh=True)`.
- Add `features['mlt_bindings']`.
- `tests/unit/test_discovery_commands.py::test_doctor_absent_binaries_models_and_engines`
  asserts that every feature is False and forbids `subprocess.run`. Add one
  `monkeypatch.setattr(<engine module>, "find_mlt_python", lambda **k: None)`
  line there. Keep its assertions.

### 8. Test mark (`tests/_testkit.py`)

Add `HAVE_MLT_BINDINGS` and `requires_mlt_bindings`.

- **Do not** use `importlib.util.find_spec("mlt7")`. That checks the venv,
  where the bindings never are; the shared rule in 00-README does not apply
  here.
- Compute it with
  `engine.find_mlt_python() is not None`, wrapped in `try/except Exception: False`.
- Put the mark next to `requires_melt`.

### 9. CI (`.github/workflows/tests.yml`, `full` job only)

- Add `python3-mlt` to the `apt-get install` line.
- Set `env: WVB_MLT_PYTHON: /usr/bin/python3` on the pytest step.
- Leave the `unit` job unchanged: no bindings there, and the tests skip.
- Ubuntu's module name is expected to be `mlt7`. If CI shows otherwise, the
  worker's `import mlt` fallback covers it. Report what you could not verify.

## Tests (all required)

- `tests/unit/test_mlt_engine.py` runs without MLT, so it works in the CI
  `unit` job. Give `run_worker` and `find_mlt_python` test-only keyword
  overrides, `_interpreter=` (default: the discovered one) and
  `_worker_path=` (default: the real `_worker.py`). Pass `sys.executable`
  plus a **fake worker** script written to `tmp_path`. Cover:
  - a canned ping and inspect;
  - a script that does `os.kill(os.getpid(), signal.SIGSEGV)`, which must
    raise `MltWorkerCrashed`;
  - a script that sleeps, which must raise `TimeoutExpired` (use a 1 s
    timeout);
  - a script that prints garbage, which must raise `MltWorkerError`;
  - `WVB_MLT_PYTHON` pointing at a nonexistent file, which must make
    `find_mlt_python()` return None with no fallback.
- `tests/unit/test_load_check_compare.py`: feed `compare_inspection` canned
  dicts and check profile mismatch, missing playlist, in/out/start mismatch,
  `_kdpair` ignored, and producer-id warning.
- `tests/integration/test_mlt_load_check.py` with `requires_mlt_bindings`:
  - Serialize `sequence_project()` and `two_track_project()` (testkit) to
    tmp. The load-check must report **zero** error items.
  - Edit the written XML (change one `<entry ... out="24">` to `out="20"`)
    and re-check with the *original* model. Expect exactly one in/out error.
  - Run the native fixture `cross_dissolve_native.kdenlive` through
    `inspect`. Expect 4 non-black tracks and clip starts 197 and 0.
- Melt-fallback test (`requires_melt`): with `find_mlt_python` patched to
  None, a valid project gives `engine == "melt"` and no errors.
- Run unit, full suite and ruff exactly as 00-README says.

## Acceptance criteria

- `project_validate` on a fresh testkit project returns
  `load_check.engine == "bindings"` on this machine, with no load-check errors.
- Killing the worker with SIGSEGV yields a validation error item, not an
  exception and not a hang.
- `wvb doctor` prints an `mlt_bindings: ready` line on this machine.
- The full suite is green, both with and without `WVB_MLT_PYTHON=/nonexistent`.

## Do NOT

- Do not `import mlt7` anywhere inside the venv process, and do not add
  system site-packages to `sys.path`.
- Do not keep a long-lived worker process or pool. One process per request
  isolates crashes.
- Do not let the load-check modify or rewrite the project.
- Do not make `serialize_project` fail because of a load-check.
- Do not duplicate the media-existence check.
- Do not change the serializer's XML output in this task.

## When done

1. `docs/plans/2026-10-13-media-mcp-expansion.md`, Phase 3: mark the worker,
   load-check, doctor row, mark and CI items done (with the date).
2. Add a vault note, `vault/wiki/mlt-python-bindings-worker.md`: why the
   worker is out of process, the stdout dup trick, the stderr noise, the
   segfault rules, the Multitrack -> cut -> parent walk, and
   `is_valid()`-lies-about-missing-media.
3. Mention `load_check` and `project_mlt_inspect` in
   `docs/video-editing-guide/17-troubleshooting.md`.
4. Regenerate `docs/capabilities.md`:
   `uv run --project /home/caleb/Projects/ForgeFrame wvb capabilities --markdown > /home/caleb/Projects/ForgeFrame/docs/capabilities.md`.
5. Report per 00-README. Include the load-check result for every file in
   `tests/fixtures/kdenlive_references/`. The ones that reference
   `C:/Users/...` media will show load warnings; list them.
