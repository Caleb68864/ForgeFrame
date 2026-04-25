# Golden fixture testing for Kdenlive XML

Test the serializer against a real Kdenlive-saved file committed as a fixture, instead of relying on launching Kdenlive in CI. Kdenlive's XML contract is too thick to specify in pure assertions, but a reference file plus structural diffs catches every regression.

## The fixture

`tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive` — saved by Kdenlive 25.08.3 / MLT 7.33.0 after a clean drag-and-drop of a single clip. Profile: `atsc_1080p_2997`. Treated as authoritative for the v25 document shape.

## Two complementary test layers

### 1. Structural assertions (`tests/unit/test_kdenlive_v25_shape.py`)

Builds a one-clip project model in Python, serializes, then asserts on structure:
- ≥ 4 tractors (per-track + sequence + project wrapper)
- Per-track tractors with audio internal filters
- Main sequence has UUID id and required `kdenlive:sequenceproperties.*`
- `main_bin` has `opensequences` and `activetimeline` matching the sequence UUID
- Project tractor wrapper carries `kdenlive:projectTractor=1`

Plus a sanity class `TestReferenceFixtureSatisfiesAssertions` that runs the **same assertions against the reference fixture**. If they pass on the fixture but fail on our output, the bug is in the serializer. If they fail on the fixture, the assertion is wrong.

### 2. End-to-end smoke (`tests/integration/test_v25_kdenlive_smoke.py`)

Mirrors the MCP flow without the FastMCP runtime:
- `_build_initial_project()` mirrors `project_create_working_copy`
- `_insert_clip()` mirrors `clip_insert` (parser → patcher → serializer)
- Writes to `tests/fixtures/media_generated/` for a fully reproducible loop
- Two side-effect tests drop `.kdenlive` files into the user's local Kdenlive test folder so a human can verify in the actual app

The smoke test exercises the same `parse_project` → `patch_project` → `serialize_versioned` path that `clip_insert` uses, so a parser regression breaks it loudly.

## Generating the test media

`tests/fixtures/media_generated/generate_test_clip.sh` produces a deterministic 5-second SMPTE color-bars + 1 kHz tone clip at 1920x1080 @ 30000/1001. Reproducible from any machine with ffmpeg.

## When to refresh the fixture

Refresh the reference if Kdenlive's XML schema changes between major versions (e.g. 25 → 26). To refresh:

1. Open Kdenlive at the new target version.
2. Build a one-clip project by drag-and-drop, save.
3. Replace `single_clip_kdenlive_native.kdenlive`.
4. Re-run `pytest tests/unit/test_kdenlive_v25_shape.py::TestReferenceFixtureSatisfiesAssertions` — anything that fails tells you what the new schema changed.
5. Update the serializer to match.

## Why this beats launching Kdenlive in tests

- Kdenlive in CI is fragile (X server, MLT runtime, codec licenses).
- The structural assertions reproduce in <1 second.
- A failing structural assertion points at the exact piece of XML to fix.
- A passing structural test plus a manual "open it in Kdenlive" round confirms reality. Kdenlive's error dialogs are precise enough that source-search recovers the next missing bit fast.

## Related

- [[kdenlive-25-document-shape]]
- [[kdenlive-bin-loader-source-pointers]]
