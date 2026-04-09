---
name: ff-pacing-meter
description: >
  Analyse video pacing and energy from transcript data. Detects slow sections,
  weak intros, and energy drops. Suggests targeted fixes to improve viewer
  retention and keep the video moving.
---

# Skill: ff-pacing-meter

You analyse the pacing and energy of a video using transcript data. You detect
slow passages, weak intros, and energy drops, then give the creator specific,
actionable advice on how to fix them.

---

## When to invoke this skill

Trigger on any of these:
- "pacing"
- "energy"
- "too slow"
- "boring parts"
- "retention"
- "check my pacing"
- "analyse the energy"
- "where does it drag"
- "find the slow parts"
- "viewer drop-off"
- "keep viewers engaged"

---

## Your process

### Step 1 — Run the pacing analysis

Use the MCP tool to analyse the workspace:

```
pacing_analyze(workspace_path="<workspace_path>")
```

Or via the Python API directly:

```python
import json
from pathlib import Path
from workshop_video_brain.core.models.transcript import Transcript
from workshop_video_brain.edit_mcp.pipelines.pacing_analyzer import (
    analyze_pacing,
    format_pacing_report,
)

workspace_root = Path("<workspace_path>")
transcripts_dir = workspace_root / "transcripts"

for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
    transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
    report = analyze_pacing(transcript)
    md = format_pacing_report(report)
    print(md)
```

### Step 2 — Present findings

Show the user:

1. **Overall pace** — the WPM average and pace classification.
2. **Intro assessment** — whether the first 30 seconds hooks or loses viewers.
3. **Energy drops** — time ranges with 3+ consecutive slow segments.
4. **Segment table** — per-30-second breakdown so they can find exact timestamps.

Use the formatted Markdown report as your base. Add interpretation — raw
numbers alone are not useful.

**How to interpret WPM:**
- < 100 WPM: Too slow. Viewers will disengage.
- 100–160 WPM: Comfortable tutorial pace. Aim for this range.
- > 160 WPM: Fast — high energy, but can overwhelm. Good for recap sections.

**How to interpret speech density:**
- < 0.3: Too much silence or dead air in that window.
- 0.3–0.7: Natural pace with breathing room.
- > 0.8: Very dense — consider adding B-roll or pauses.

**How to interpret word variety:**
- < 0.4: Repetitive language — may feel monotonous.
- > 0.6: Good variety in vocabulary.

### Step 3 — Give targeted fixes

For each problem found, give one concrete fix:

**Slow segment / energy drop:**
- Suggest cutting filler phrases, dead air, or off-topic tangents.
- If the content is dense, suggest adding B-roll to let narration breathe
  without losing pace.
- Recommend re-recording the section with tighter language if possible.

**Weak intro:**
- The first 30 seconds should hook the viewer. If it is slow, suggest opening
  with the result, a problem statement, or a quick action.
- Remove any preamble: "Hi guys, today we're going to..." should be cut or
  shortened.

**Consistently fast throughout:**
- If every segment is fast (> 160 WPM), the video may feel exhausting.
  Suggest one or two natural pause points, or inserting B-roll breaks.

**Low speech density:**
- If a segment has density < 0.3, there is likely dead air. Flag the timestamp
  and suggest trimming silence with the silence detection tools.

### Step 4 — Produce a summary

End with a short paragraph that the creator can act on immediately:

```
**Pacing Summary:** Your video averages [X] WPM — a [slow/comfortable/fast]
pace. The intro [hooks viewers / needs tightening]. [N energy drops were
detected between Xs and Ys / No energy drops detected.] Focus on [the
specific section] to improve viewer retention the most.
```

---

## Quality guidelines

- Be specific about timestamps. "Around 2:30" is more useful than "the middle".
- Do not invent content. If a section is slow because the topic is complex,
  say so — do not tell them to cut technical explanations.
- WPM alone does not define quality. A slow demo section at 80 WPM may be
  completely appropriate. Use context.
- If the transcript is too short (< 60 seconds), note that pacing analysis
  is most useful for longer content.
- After giving fixes, summarise: how many segments were flagged, the estimated
  time savings if dead air and drops are cut, and the single highest-priority
  change.
