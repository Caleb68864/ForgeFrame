# Prompt 08: runtime validation of the Reliability and Guided Workflow work

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not repeated here.

## Summary

Commit `c561ccb` added six features: unified render, serialized-XML
validation, persistent jobs, safe writes, doctor/capabilities, and the guided
workflow. `docs/plans/2026-04-08-feature-roadmap.md` (section "Reliability and
Guided Workflow", around lines 124-188) still marks most of them
"implemented, runtime validation pending". It also still says "No tests were
added or run", which is out of date: that commit added about 15 test files.

Your job is to exercise every user entry point **for real** on a synthetic
workspace, record the results in a testing note, fix small bugs you find,
add integration tests for the gaps listed below, and then rewrite the
roadmap's follow-up text. This is a validation task, not a feature task.

## Ground truth (checked 2026-10-14; re-check, do not trust blindly)

CLI entry points (`wvb` = `uv run --project /home/caleb/Projects/ForgeFrame wvb`):

| Feature | CLI | Source | MCP tool(s) |
|---|---|---|---|
| Jobs | `wvb jobs submit WS {render,proxy,transcribe,workflow} --parameters '{json}'`, `wvb jobs list WS`, `status WS ID`, `cancel WS ID`, `retry WS ID` | `app/jobs_cli.py`, logic in `workspace/jobs.py` | `job_submit`, `job_status`, `job_list`, `job_cancel`, `job_retry` (`edit_mcp/server/tools/jobs.py`) |
| Doctor | `wvb doctor [--json]` | `app/discovery_cli.py`, `app/doctor.py` | `forgeframe_doctor` (`tools/discovery.py`) |
| Capabilities | `wvb capabilities [--markdown]` | `app/capabilities.py` | `forgeframe_capabilities` |
| Status | `wvb project-status WS` | `app/workflow_cli.py` -> `pipelines/guided_workflow.project_status` | `project_status` (`tools/guided_workflow.py`) |
| Workflow | `wvb workflow WS --through {footage..review} [--project-file P]` (submits a **detached job**) | same | `workflow_start` |
| Render | `wvb render preview WS`, `wvb render status WS` | `app/cli.py` ~748 -> `pipelines/render_pipeline.run_render` | `render_preview`, `render_final_tool`, `render_status` (`tools/render.py`) |
| XML validation | runs inside `serialize_project` (`adapters/kdenlive/serializer.py` ~885-920, `validator.validate_serialized_xml`) | `wvb project validate WS` | `project_validate` |
| Safe writes | `workspace/safe_write.py` (`locked_path`, `atomic_write_*`), `core/utils/paths.assert_not_protected` | -- | every writer |

Already covered by tests (all 10 passed on 2026-10-14 in about 30 s):
`tests/integration/test_reliability_mcp_transport.py` (real stdio MCP; the
"initialization timeout" in `docs/testing/2026-10-13-reliability-validation.md`
no longer reproduces), `test_persistent_job_lifecycle.py`,
`test_guided_workflow_smoke.py` and `test_unified_render_smoke.py`. Unit tests
include `test_persistent_jobs.py`, `test_safe_writes.py`,
`test_discovery_commands.py`, `test_guided_workflow.py` and
`test_serialized_xml_validation.py`.

**Known gaps (no test exercises them):**
1. None of the CLI commands `wvb jobs ...`, `wvb workflow`, `wvb project-status` is tested.
2. Cancelling an **actively running** job, so the worker process group is
   killed and partial output removed. The 10-13 note says so explicitly; the
   unit test only monkeypatches `os.killpg`.
3. A real `render` job through the jobs system (melt), registered in the render registry.
4. A real `proxy` job on media that actually needs a proxy.
5. `wvb doctor --json` / `forgeframe_doctor` key shape on this host.

## Steps

### 1. Baseline

Run the four integration files above plus the six unit files. Record the
counts. Then run the full suite once (see the shared rules) and record the
baseline.

### 2. Build a synthetic workspace (scratch, outside the repo)

Use a scratch dir such as `/tmp/wvb-validate`. Do not use the repo. Copy the
recipe in `tests/integration/test_guided_workflow_smoke.py`:
- `WorkspaceManager.create('Sanding tutorial', <scratch>, workspace_root=<scratch>/ws)`;
- copy `tests/fixtures/media_generated/test_clip_1080p2997_5s.mp4` to `ws/media/raw/sanding.mp4`;
- write `ws/transcripts/sanding_transcript.json` (a manual `Transcript`, so no Whisper runs);
- write `ws/reports/script.json` with one step.

Put the setup in a throwaway Python file in the scratchpad and run it with
`uv run --project /home/caleb/Projects/ForgeFrame python <file>`. Keep the
file; you will reuse it in step 4.

### 3. Exercise every entry point and record results

For each row below, run the command, capture the output (trim it), and write
PASS/FAIL plus notes into the new note
`docs/testing/2026-10-14-reliability-runtime-validation.md`. Use the style of
`docs/testing/2026-10-13-reliability-validation.md`.

1. `wvb doctor` and `wvb doctor --json`. Is every `features` key consistent
   with the host? Note: `tesseract: ready` but `ocr: unavailable` is expected
   when `pytesseract` is not installed. Say so in the note rather than fixing it.
2. `wvb capabilities --markdown` vs `docs/capabilities.md`. Diff them. A
   difference means the catalog is stale; regenerate it.
3. `wvb project-status WS` before anything has run. It must create no files.
   Compare `find WS -newer <marker>` before and after.
4. `wvb workflow WS --through review`. It prints a job. Poll
   `wvb jobs status WS <id>` until it is terminal (at most about 120 s). Then
   check:
   - `wvb project-status WS`: all readiness true;
   - a `.kdenlive` file in `projects/working_copies/`;
   - a non-empty preview render;
   - a review file.
5. Run `wvb workflow WS --through review` again. It must resume: no stage
   re-runs and the artifacts' mtimes are unchanged.
6. `wvb project validate WS` on the produced project. Then run a corrupt copy
   (truncate the XML) through `project_validate` and through a mutating tool,
   e.g. `guide_add`. Both must return a `corrupt_project` error. The original
   file must be unchanged (compare hashes).
7. `wvb jobs submit WS render --parameters '{"profile":"preview"}'`, then
   poll it. Check:
   - status `succeeded`;
   - `wvb render status WS` lists the output;
   - ffprobe of the output shows a video stream and a duration within 1 frame
     of the project length.
8. Active cancel:
   - Submit a render job of a **longer** project. Build one by inserting the
     5 s clip 12 times with `clip_insert`, or render with a slow profile.
   - Cancel it while `status == running`.
   - Within 15 s, `status` must be `cancelled`.
   - The process group must be gone: `ps -eo pgid= | grep <pid>`.
   - No partial output may remain in `renders/`.
   - `wvb jobs retry` must give a new job id.
9. Proxy job. Put a clip that needs a proxy into `media/raw/`.
   `adapters/ffmpeg/proxy.py` `ProxyPolicy` triggers a proxy above 1920x1080,
   for HEVC/ProRes, or above 50 Mb/s. A 1 s 2560x1440 `make_test_clip` is the
   cheapest trigger. Submit `proxy` and expect
   `proxied >= 1` with a file in `media/proxies/`. Run it again and expect
   `proxied == 0` (the fresh check).
10. Safe writes:
    - Writing a project into `projects/source/` must raise `ProtectedPathError`.
    - Two concurrent `serialize_project` calls on the same file, via threads,
      must both snapshot. `test_safe_writes.py` covers this in a unit test;
      repeat it once on the real workspace and record the result.
11. MCP parity: run the existing `test_reliability_mcp_transport.py` again and
    record the result.

### 4. Fix small bugs, list large ones

- **Small** means at most about 30 lines in one module, with an obvious fix.
  Fix it and add a regression test. Examples: wrong key names, a missing
  `timeout=`, a wrong error constructor, a stale docstring that misleads.
- Anything bigger goes in the report and in the testing note under
  "Open issues". Do not fix it.
- Already noticed (verify each, then fix or list it):
  - `WorkspaceManager.create` docstring says the workspace defaults to
    `media_root / slug`, but the code uses `media_root.parent / slug`
    (`workspace/manager.py` ~33-39). Fix the docstring only.
  - `bundles/guides.py` `guide_add` docstring says the serializer writes only
    legacy `<guide>` elements. The serializer now also writes
    `kdenlive:sequenceproperties.guides` (`serializer.py` ~740-750). Correct
    the docstring.

### 5. Add the missing integration tests

Create `tests/integration/test_reliability_cli.py`. Use
`click.testing.CliRunner` against `workshop_video_brain.app.cli.main` (see
`tests/unit/test_discovery_commands.py` for the pattern) and real detached
workers. Mark it `requires_ffmpeg_ffprobe`, plus `requires_melt` where it
renders, and skip on non-POSIX.

Cover:
- `jobs submit` with bad `--parameters` (non-JSON, non-object, unknown key)
  gives a non-zero exit and a clear message;
- `project-status` creates no files;
- `workflow --through footage` on an empty workspace fails with the
  "Copy recordings" message, and `jobs retry` gives a new id;
- `workflow --through review` succeeds end to end on the step-2 workspace
  (move the step-2 setup into a fixture);
- active cancellation of a running render job, as in step 3 item 8. Bound
  every poll loop, and in a `finally` cancel anything still active so a
  failure never leaks a worker;
- a real render job and its registry entry.

Keep total runtime under about 60 s. If active cancel turns out to be
nondeterministic, mark only that test `render_retry` and say so in the report.

### 6. Update the docs

- `docs/plans/2026-04-08-feature-roadmap.md`, items 1-6. Replace
  "implemented, runtime validation pending" with "implemented, validated
  2026-10-14" plus a short note for anything partial (e.g. Windows detached
  jobs unsupported, frame-level progress not implemented). Leave item 2's
  Kdenlive compatibility note alone. That belongs to the Kdenlive 26.08
  section.
- Replace the paragraph "Validation performed: static source review ... No
  tests were added or run" with 3-6 lines: what was run, the counts, the new
  test file, and a link to the new testing note.
- Add a dated addendum to the end of
  `docs/testing/2026-10-13-reliability-validation.md`: the MCP transport
  tests now pass (2026-10-14).

## Acceptance criteria

- The testing note exists, has one row per item in step 3, and every row is PASS or FAIL with notes.
- `tests/integration/test_reliability_cli.py` exists and passes. Active cancel is covered by a real worker, not a monkeypatch.
- The roadmap no longer says "runtime validation pending" or "No tests were added or run".
- Every bug fix has a regression test. Larger issues are listed, not fixed.
- The full suite has no new failures. ruff is clean on the touched files.

## Do NOT

- Do not touch the serializer's XML shape, `validator.py` rules or render command construction beyond a listed small fix.
- Do not download Whisper/rembg models or run the `transcribe` job against a real model. Use manual transcripts.
- Do not run the scratch workspace inside the repo or inside `tests/fixtures/`.
- Do not make the jobs system work on Windows. Note it as a limitation.
- Do not leave detached workers running. Check `ps` at the end.

## When done

- Update the roadmap and testing notes as in step 6. If you changed tools or docstrings, regenerate `docs/capabilities.md` with `wvb capabilities --markdown`.
- Report in the shared format. Also include the step-3 table (item, result, one-line note) and the list of open issues.
