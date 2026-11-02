# Reliability runtime validation (2026-11-02)

Prompt 08. Scratch workspace outside the repo, built from `tests/fixtures/media_generated/test_clip_1080p2997_5s.mp4` with a manual transcript, so no speech model ran. Linux, CPython 3.12, melt 7.42, Kdenlive 26.08.2.

| # | Entry point | Result | Notes |
| --- | --- | --- | --- |
| 1 | `wvb doctor`, `--json` | PASS | Features match the host. `tesseract: ready` with `ocr: unavailable` is expected: `pytesseract` is not installed. |
| 2 | `wvb capabilities --markdown` vs `docs/capabilities.md` | FAIL, fixed | Catalog was stale: `clips_detect_scenes` still said `scdet`. Regenerated. |
| 3 | `wvb project-status` before any run | PASS | `find -newer` lists nothing; no files created. |
| 4 | `wvb workflow --through review` | PASS | Job succeeded; all readiness true; assembled project, non-empty preview and `reports/workflow_review.md` exist. |
| 5 | Same command again | PASS | Job succeeded; every artifact mtime unchanged. |
| 6 | `project validate`; corrupt copy through `project_validate` and `guide_add` | PASS | Valid project: no issues. Truncated copy: both return `corrupt_project`, file hash unchanged. |
| 7 | `jobs submit render {"profile":"preview"}` | PASS | Succeeded and listed by `render status`. ffprobe: video + audio, 101 frames at 25 fps; the project is 101 frames. |
| 8 | Cancel a running render | PASS | 14-clip project, melt running. `cancelled` in 0.2 s, process group gone, no new mp4 in `renders/`, retry gave a new id. |
| 9 | `proxy` job | PASS | 2560x1440 clip: `proxied: 1`, `media/proxies/big_proxy.mp4`. Second run: `proxied: 0`. |
| 10 | Safe writes | PASS | Write into `projects/source/` raises `ProtectedPathError`. Two concurrent saves: both snapshot (delta 2), no errors, file re-parses. |
| 11 | MCP transport tests | PASS | Part of the full suite run; see the prompt 08 report. |

## Fixed

- `docs/capabilities.md` regenerated.
- Docstrings: `WorkspaceManager.create` default root is `media_root.parent / slug`; `guide_add` no longer claims guides are written only as legacy elements.

## Mutation check

Replacing `os.killpg(pid, signal.SIGTERM)` in `cancel_job` with a no-op makes `test_cancelling_a_running_render_kills_the_group_and_leaves_no_output` fail, so the active-cancel test does exercise the real signal.

## Open issues

- Detached jobs are POSIX only. Windows is out of scope.
- Progress is per stage, not per frame.
- Generated projects have not been opened in the Kdenlive GUI (prompt 06 Part A).
