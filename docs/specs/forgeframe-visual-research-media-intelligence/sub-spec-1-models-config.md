---
sub_spec_id: SS-01
phase: run
depends_on: []
dispatch: factory
wave: 1
---

# SS-01 — Domain models, ResearchConfig, and transcript extension

## Context
Foundation layer. Adds the `visual_research` Pydantic models + `ResearchConfig`, extends
`TranscriptSegment` additively, and adds availability helpers to `Config`. No behavior wired.
All models extend `core/models/_base.py::SerializableMixin` (see `transcript.py` for the pattern:
`model_config = {"use_enum_values": True}`, `Field(default_factory=...)`). Tests run from repo
root: `uv run pytest tests/ -q` (`pythonpath=["workshop-video-brain/src"]`).

## Implementation Steps (TDD)
1. **Write failing test** `tests/unit/test_visual_research_models.py`: import `ResearchQuery,
   ResearchRegion, FrameVisualMetrics, FrameCandidate, ResearchCapture, ResearchManifest,
   FrameEvaluation, SceneChange, ResearchConfig` from `workshop_video_brain.core.models`;
   assert `ResearchConfig()` constructs; assert a `ResearchManifest` with a nested `MediaAsset`,
   one region, one capture round-trips through `SerializableMixin` (serialize → deserialize equal);
   assert `TranscriptSegment(start_seconds=0, end_seconds=1, text="x")` still constructs and that
   `.tags == []` and `.metadata == {}` and `.segment_id`/`.speaker` default to `None`.
2. **Run to fail:** `uv run pytest tests/unit/test_visual_research_models.py -q` → ImportError.
3. **Implement** `workshop-video-brain/src/workshop_video_brain/core/models/visual_research.py`:
   define the 9 models per master-spec field lists; constrain `FrameCandidate.extraction_method`
   and `ResearchRegion.source_method` (Literal or validator); `ResearchConfig` nested groups
   (`windowing, candidate_generation, scene_detection, quality, deduplication, ocr, vision, export`)
   as sub-models with the design defaults.
4. **Extend** `core/models/transcript.py::TranscriptSegment` additively: `segment_id: str | None = None`,
   `speaker: str | None = None`, `tags: list[str] = Field(default_factory=list)`,
   `metadata: dict = Field(default_factory=dict)`. Do not reorder or change existing fields.
5. **Export** in `core/models/__init__.py`: add imports + `__all__` entries for all new models
   (follow the existing grouped-comment style).
6. **Config** `app/config.py`: add `tesseract_available: bool` to the `Config` dataclass and set it
   via `shutil.which("tesseract")` in `load_config()` (no warning required if absent).
7. **Run to pass:** `uv run pytest tests/unit/test_visual_research_models.py -q`.
8. **Commit:** `factory(SS-01): visual_research models, ResearchConfig, transcript extension [factory-managed]`

## Interface Contracts
- **Owner** of all `visual_research` models + `ResearchConfig` + `SceneChange` + `FrameVisualMetrics`.
  Consumed by SS-02..SS-11. Canonical field shapes are the master-spec `## Domain Models` list.
- **Requires:** `MediaAsset` (existing), `SerializableMixin` (existing), `TranscriptSegment` (extends).

## Verification Commands
- Build: `uv sync`
- Import smoke: `uv run python -c "from workshop_video_brain.core.models import ResearchManifest, FrameCandidate, ResearchConfig, SceneChange; ResearchConfig()"`
- Tests: `uv run pytest tests/unit/test_visual_research_models.py -q`
- Regression: `uv run pytest tests/ -q`

## Checks
Auto-generated from `[MECHANICAL]`/`[STRUCTURAL]` criteria. Each exits 0 on pass, 1 on fail.

| Criterion | Type | Command |
|-----------|------|---------|
| visual_research.py defines the 9 models | [STRUCTURAL] | `grep -Eq "class (ResearchQuery\|ResearchRegion\|FrameVisualMetrics\|FrameCandidate\|ResearchCapture\|ResearchManifest\|FrameEvaluation\|SceneChange\|ResearchConfig)" workshop-video-brain/src/workshop_video_brain/core/models/visual_research.py \|\| (echo "FAIL: models missing" && exit 1)` |
| TranscriptSegment gains optional metadata field | [STRUCTURAL] | `grep -q "metadata" workshop-video-brain/src/workshop_video_brain/core/models/transcript.py \|\| (echo "FAIL: TranscriptSegment.metadata missing" && exit 1)` |
| __init__ re-exports new models | [STRUCTURAL] | `grep -q "ResearchManifest" workshop-video-brain/src/workshop_video_brain/core/models/__init__.py \|\| (echo "FAIL: models not exported" && exit 1)` |
| Config gains tesseract_available | [STRUCTURAL] | `grep -q "tesseract_available" workshop-video-brain/src/workshop_video_brain/app/config.py \|\| (echo "FAIL: tesseract_available missing" && exit 1)` |
| import smoke constructs ResearchConfig | [MECHANICAL] | `uv run python -c "from workshop_video_brain.core.models import ResearchManifest, FrameCandidate, ResearchConfig, SceneChange; ResearchConfig()"` |
| unit tests pass | [MECHANICAL] | `uv run pytest tests/unit/test_visual_research_models.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: unit tests" && exit 1)` |
