# Prompt 07: optional `kdenlive --verify-file` validator backend (roadmap step 7, conditional)

Hand this whole file to the implementing model.

---

**Summary.** Kdenlive's development branch (master, after 26.08) has a
headless project check. It loads a `.kdenlive` file without a GUI, runs
`KdenliveDoc::checkConsistency()`, and then:

- prints `SUCCESS: Project file is valid: <path>` and exits 0, or
- prints `Verification failed: <reason>` and exits 1.

That is Kdenlive's own verdict on whether a file loads cleanly, which is
exactly what our structural validator approximates. This task adds it as an
**optional** extra backend for the `project_validate` tool and CLI. It is
used only when the installed Kdenlive supports it.

**The task is conditional.** Kdenlive **26.08.2**, the version installed on
this machine as of 2026-10-14, does **not** have the flag. If step 0 finds no
flag, stop: make no changes and report.

**Read `docs/prompts/00-README.md` first.** Prompt 06 should be merged; it
adds the 26.08 native fixtures used in the tests below.

## Step 0: gate (always do this, and stop if it fails)

```
kdenlive --version
kdenlive --help 2>&1 | grep -i -n verify
```

- **No `verify` line:** stop. Change nothing. Report:
  - the Kdenlive version;
  - "`--verify-file` not available; prompt 07 stays parked";
  - the date.

  That is a successful outcome for this prompt.
- **A line appears:** note the exact flag spelling and the help text, then
  continue. The roadmap calls the flag `--verify-file`. Use whatever spelling
  `--help` shows, and keep it in one constant.

## Step 1: learn the real behaviour before you write code

The strings and exit codes above come from the upstream merge request
description. Confirm them on this machine before relying on them.

1. Run the flag on a known-good native save. Try three environments:
   - plain;
   - `QT_QPA_PLATFORM=offscreen` (which `app/doctor.py` already uses for
     probes);
   - `xvfb-run -a`.

   Use the first environment that works. Fixtures to try:
   - `tests/fixtures/projects/real/empty_2604.kdenlive`;
   - a `tests/fixtures/kdenlive_references/*_2608_native.kdenlive` from
     prompt 06.
2. Run it on our output: every file in a freshly built check pack
   (`scripts/kdenlive_check_pack.py`).
3. Run it on deliberately broken copies, made in your scratch dir:
   - a timeline `<entry>` whose `kdenlive:id` matches no bin clip;
   - a `main_bin` entry pointing at a missing producer;
   - a truncated XML file;
   - a path that does not exist.
4. For each run, record:
   - the exit code;
   - stdout and stderr, separately;
   - the wall time;
   - whether the verdict text is one line or several.

   Put this table in the report. **The parser in step 2 must follow what you
   observed, not this prompt.**

If the flag exists but cannot run headless here (it hangs or needs a display
even under `xvfb-run`), stop and report. Do not build a backend you cannot
test.

## Step 2: the adapter

New module:
`workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/verify_cli.py`.
It sits in the adapter layer (see the layering rule in CLAUDE.md).

- **`VERIFY_FLAG = "--verify-file"`**, set to the spelling you observed.
- **`kdenlive_verify_available() -> bool`**
  - Return False if `shutil.which("kdenlive")` is None.
  - Otherwise run `kdenlive --help` with
    `timeout=CAPABILITY_TIMEOUT_SECONDS` (from `adapters/ffmpeg/runner.py`)
    and the environment from step 1, and check that the flag appears.
  - Cache the result for the process with `functools.lru_cache`.
  - Catch `(OSError, subprocess.TimeoutExpired)` and return False.
- **`verify_project_file(path: Path) -> ValidationReport | None`**
  - Return None when the backend is unavailable.
  - Run `kdenlive VERIFY_FLAG <path>` with
    `timeout=ANALYSIS_TIMEOUT_SECONDS`, `capture_output=True`, `text=True`,
    and the environment from step 1.
  - Map the outcome:

    | Outcome | Result |
    |---|---|
    | exit 0 and the success marker | an empty `ValidationReport` (summary "Kdenlive verification passed.") |
    | exit 1 and `Verification failed:` | one `ValidationItem` per failure message: severity `error`, category `kdenlive_verify`, message = Kdenlive's text verbatim, location = the file name |
    | any other exit code, or output you cannot parse | one `error` item quoting the last 20 lines of combined output. Never return a fake success. |
    | `subprocess.TimeoutExpired` | one `warning` item: "Kdenlive verification timed out after N s" |

  - `ValidationItem`, `ValidationReport` and `ValidationSeverity` live in
    `core/models/validation.py` and `core/models/enums.py`.
- **Do not** call this from `serialize_project` or any write path. Loading
  Kdenlive takes seconds; it is a validation-time check only.

## Step 3: wire it into the validate entry points

1. **MCP tool** `project_validate`
   (`edit_mcp/server/tools/timeline_project.py`, around line 223):
   - Add `backend: str = "auto"`. Accepted values:
     - `"model"`: today's behaviour;
     - `"kdenlive"`: also run the Kdenlive check, and return
       `invalid_input` with a clear suggestion if it is unavailable;
     - `"auto"`: run the Kdenlive check if it is available.
   - Merge the items into the existing `issues` list.
   - Add `"backends_run": [...]` and `"kdenlive_verify_available": bool` to
     the payload.
   - Reject any other value with `invalid_input`.
2. **CLI** `wvb project validate` (`app/cli.py`, around line 680): add a
   `--backend [auto|model|kdenlive]` option with the same semantics, and print
   the Kdenlive items.
3. **Doctor** (`app/doctor.py`):
   - Add `'kdenlive'` to the binaries probed (`--version` works headless).
   - Add the feature `'kdenlive_verify': kdenlive_verify_available()`.
   - Add the suggestion: "Kdenlive with --verify-file (newer than 26.08)
     enables project_validate backend=kdenlive."
   - Update `tests/unit/test_discovery_commands.py` if it pins the key set.
4. The tool signature changed, so regenerate `docs/capabilities.md` (the
   generator is in `app/capabilities.py`; see 00-README).

## Step 4: test mark

In `tests/_testkit.py`, add `requires_kdenlive_verify`. Put it next to
`requires_kdenlive` if prompt 01 added that mark.

- Evaluate it lazily, through `kdenlive_verify_available()`, so importing
  `_testkit` never spawns Kdenlive on hosts without it.
- Skip reason: "kdenlive --verify-file not available".

## Step 5: tests (all required)

- **`tests/unit/test_kdenlive_verify_cli.py`.** No binary needed; monkeypatch
  `subprocess.run` and `shutil.which`. Cover:
  - available;
  - unavailable (no binary; flag not in help);
  - success;
  - a failure with one message;
  - a failure with several messages, if step 1 showed that format;
  - an unknown exit code;
  - a timeout.

  Also assert that every `subprocess.run` call passes `timeout=`.
  `tests/unit/test_subprocess_timeouts.py` checks this statically as well.
- **Tool and CLI unit tests.** Cover:
  - `backend="model"` never calls the adapter;
  - `"auto"` without Kdenlive runs the model checks only;
  - `"kdenlive"` without Kdenlive returns `invalid_input`;
  - a bad backend value returns `invalid_input`.
- **`tests/integration/external/test_kdenlive_verify.py`.** Mark it
  `requires_kdenlive_verify`.
  - The native fixtures pass.
  - Every freshly built check-pack project passes. This is the real
    acceptance test: Kdenlive itself accepts what we write.
  - The broken copies from step 1 fail, with Kdenlive's message in
    `issues`.
- Do not add Kdenlive to CI. The external test self-skips.
- Run the unit suite, the full suite and ruff, as in 00-README.

## Acceptance criteria

- If the gate fails: no file changes, and a report saying so.
- If it passes:
  - `project_validate(backend="auto")` on a check-pack workspace returns
    `backends_run` containing `kdenlive` and no issues;
  - a broken file returns Kdenlive's verbatim message;
  - doctor shows `kdenlive_verify: true`;
  - all tests pass, with no new skips on this machine.

## Do NOT

- Do not run Kdenlive inside `serialize_project`, the patcher, or any tool that
  writes.
- Do not make Kdenlive a required dependency, and do not fail when it is
  missing.
- Do not parse Kdenlive's output with patterns you did not observe in step 1.
- Do not change `validate_project` or `validate_serialized_xml` semantics. The
  new backend adds items; it never removes model items.
- Do not edit `__init__.py` files or the patcher F401 block.

## When done

1. Roadmap step 7: either "Done <date>" with a summary, or "Checked <date>:
   Kdenlive X lacks the flag".
2. `vault/wiki/kdenlive-verify-file.md` (only if implemented): what the
   flag does, its exact output and exit codes, the headless environment
   needed, and how ForgeFrame uses it.
3. In CLAUDE.md "When Kdenlive rejects a file", add a step 0: "run
   `project_validate backend=kdenlive` (or `kdenlive --verify-file <file>`)
   for Kdenlive's own verdict". Only add it if implemented. Mirror the change
   into AGENTS.md (prompt 06 made those sections identical).
4. Report, using the 00-README format. Also include:
   - the gate output;
   - the step 1 behaviour table;
   - the check-pack verification results.
