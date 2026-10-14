# Reliability validation — 2026-10-13

Scope: roadmap priorities 1–6. Linux, Python 3.12.15. Includes the completed full run, focused follow-up checks, and unresolved transport coverage.

## Installed wheel checks

Both build roots passed offline wheel construction with the existing uv cache:

```sh
UV_CACHE_DIR=/tmp/forgeframe-uv-cache /tmp/forgeframe-uv/bin/uv build --wheel --out-dir /tmp/forgeframe-wheel-root --offline
# Same command from workshop-video-brain/, output /tmp/forgeframe-wheel-plugin.
```

Each wheel was installed with `uv pip install --no-deps --offline` into a separate throwaway virtual environment. An import probe ran from `/tmp`, asserted the package loaded from that environment's site-packages, and reused existing project dependencies without resolving or changing the project environment.

Both installed wheels exposed identical dependency metadata and four extras: `research`, `ai-mask`, `ai-mask-heavy`, `motion-track`. Both contained and loaded 7 Obsidian templates, 12 render profiles and 3 title styles. The `preview` profile loaded successfully. Both generated a capability catalog containing 220 tools including `job_submit`; packaged skill availability was explicitly false with zero skills, since skills are distributed through the plugin rather than the Python wheel.

This verifies wheel contents, metadata and selected runtime loaders. It is not a clean-machine installation of every optional dependency.

## MCP transport coverage

New `tests/integration/test_reliability_mcp_transport.py` uses a real FastMCP stdio client and server subprocess. It covers tool discovery, capability serialization, bounded offline doctor with empty model caches, invalid workspace/operation responses followed by a valid request, persisted lost-worker recovery, submission of a detached workflow that fails on absent footage, survival across MCP connections, terminal cancellation, retry with a new ID, and job listing.

No Whisper models are initialized or downloaded; no whisper.cpp installation or integration occurs. The cancellation case checks idempotent cancellation of terminal work; active subprocess-group cancellation requires separate coverage.

Transport results: blocked before handler execution. The first two scenarios reached their connection timeout; an independent 25-second probe reproduced the same FastMCP 3.4.4 client initialization timeout after the server logged successful startup. No tool call was reached, so this is not evidence of a job-handler failure. Remaining transport work was stopped at the user's request to finish promptly. The new tests are saved for follow-up.

## Full suite and remaining evidence

The coordinating agent ran the full suite with output in `/tmp/forgeframe-full-tests.log`; consult its final response for counts and any outstanding failures.

Automated XML checks and renders do not substitute for opening generated files in the supported Kdenlive desktop version. Windows detached-worker support remains outside the implemented POSIX backend. Model-heavy transcription and masking checks depend on installed/cached models and may be skipped rather than downloaded.
## Final suite result

The full run completed: **4,780 passed, 31 skipped, 2 failed** in 364.61 seconds.
The two failures were the known unsupported native-import expectations collected
before their tests were updated. The focused native-import file was rerun after
the update and passed all five cases (three supported real MLT roundtrips and
two explicit safe write refusals). No subsequent complete full-suite rerun was
performed. A real guided-workflow integration also passed, covering cached
transcription through MLT preview/review, resume, and changed-script invalidation.
Whisper.cpp was not installed or integrated. The new real MCP connection checks
remain unresolved: initialization timed out before tool handlers were reached;
their remaining run was stopped at the user's request.

