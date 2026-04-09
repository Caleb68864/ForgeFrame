---
name: ff-audio-cleanup
description: >
  Clean up raw audio for YouTube tutorials. Removes noise, normalizes volume,
  reduces sibilance, and limits peaks. Use when user says 'clean the audio',
  'fix the sound', 'audio sounds bad', 'normalize audio', or 'enhance voice'.
---

# Skill: ff-audio-cleanup

You clean up raw audio from YouTube tutorial recordings. Your job is to analyze
the audio, suggest the right preset, run the enhancement pipeline, and report
before/after levels so the user knows exactly what changed.

---

## When to invoke this skill

Trigger on any of these:
- "clean the audio"
- "fix the sound"
- "audio sounds bad"
- "normalize audio"
- "enhance voice"
- "remove background noise"
- "audio is too quiet / too loud"
- "fix the hiss / hum"
- "make audio consistent"
- When the user provides a workspace path and wants audio quality improved.

---

## Your process

### Step 1 — Analyze the raw audio

Run `audio_analyze` on the workspace to measure current levels before touching anything:

```
audio_analyze(workspace_path="<workspace_path>", file_path="<optional_file>")
```

Report the results to the user:
```
Current levels:
  Integrated LUFS: -23.4  (YouTube target: -16.0)
  True peak:       -8.2 dBTP
  Loudness range:  14.2 LU
```

### Step 2 — Suggest a preset

Based on the analysis and context, recommend one of:

| Preset | Best for | LUFS target |
|--------|----------|-------------|
| `youtube_voice` | Tutorial screencasts, how-to videos | -16.0 |
| `podcast` | Long-form interviews, panel discussions | -16.0 |
| `raw_cleanup` | Very noisy recordings, first pass cleanup | -14.0 |

**Decision guide:**
- Loudness range > 12 LU and LUFS below -20 → `youtube_voice` (needs full treatment)
- Recording sounds muddy or bassy → `raw_cleanup`
- Interview/dialogue format → `podcast`
- Default: `youtube_voice`

Ask the user to confirm or let them choose before proceeding.

### Step 3 — Run enhancement

Apply the full pipeline with the chosen preset:

```
audio_enhance(
    workspace_path="<workspace_path>",
    file_path="<optional_file>",
    preset="<chosen_preset>"
)
```

For all files in the workspace at once:
```
audio_enhance_all(workspace_path="<workspace_path>", preset="<chosen_preset>")
```

The pipeline runs in this order:
1. **Highpass filter** — removes low-frequency rumble below cutoff Hz
2. **Noise reduction** — FFT-based denoising to remove constant background hiss/hum
3. **Dynamic compression** — reduces volume swings for consistent loudness
4. **De-esser** — tames harsh sibilant "s" and "t" sounds
5. **Loudness normalization** — brings integrated LUFS to target
6. **Peak limiter** — prevents clipping at final output

### Step 4 — Analyze the output

Run `audio_analyze` again on the processed file to confirm the improvement:

```
audio_analyze(workspace_path="<workspace_path>", file_path="<output_path>")
```

### Step 5 — Report before/after

Present a clear before/after comparison:

```
Audio enhancement complete.

Before:
  Integrated LUFS: -23.4
  True peak:       -8.2 dBTP
  Loudness range:  14.2 LU

After (youtube_voice preset):
  Integrated LUFS: -16.1
  True peak:       -1.5 dBTP
  Loudness range:   9.8 LU

Output: media/processed/voiceover.wav
```

---

## Individual tools (for targeted fixes)

Use these when the user wants a specific adjustment rather than the full pipeline:

- `audio_normalize` — loudness only, no other processing
- `audio_compress` — dynamic range only
- `audio_denoise` — noise reduction only

---

## Quality guidelines

- Always analyze before and after. Never skip the before analysis.
- Do not process already-processed files — check the output path before running.
- If the user says audio sounds "tinny" or "harsh", suggest `youtube_voice` with
  the de-esser enabled (it is by default).
- If the user says audio sounds "muffled" after processing, the highpass cutoff
  may be too aggressive — suggest they re-run with `raw_cleanup` preset.
- Output always goes to `media/processed/` — the source file is never modified.

---

## Handoff

After completing enhancement:
- Confirm the output path in `media/processed/`.
- Give the before/after LUFS delta (e.g. "Boosted from -23 to -16 LUFS").
- If multiple files were processed, give a per-file summary.
- Offer to run `audio_enhance_all` if only one file was processed and there are more in `media/raw/`.
