---
name: ff-capture-prep
description: "Generate a pre-shoot capture checklist from a shot plan: camera settings, audio, lighting, sync, and optimized shot order. Use when preparing to film."
---

# ff-capture-prep

Generate a capture prep checklist for an upcoming video shoot.

## When to Use

Use this skill when the user:
- Is about to start filming and wants a pre-shoot checklist
- Asks for camera settings, audio setup, or lighting recommendations
- Wants to optimize their shooting order to minimize setup changes
- Says "capture prep", "shoot prep", "pre-shoot", or "filming checklist"

## Steps

1. **Find the workspace.** Ask the user for the workspace path if not already known.

2. **Load the shot plan.** Check for `reports/shot_plan.json` in the workspace:
   ```python
   import json
   from pathlib import Path
   shot_plan_path = Path(workspace_root) / "reports" / "shot_plan.json"
   if shot_plan_path.exists():
       shot_plan = json.loads(shot_plan_path.read_text())
   ```
   If no shot plan exists, generate a generic checklist using an empty plan dict:
   ```python
   shot_plan = {"title": "Generic Shoot", "a_roll": [], "overhead": [], "closeups": [], "measurements": [], "inserts": [], "glamour": [], "pickups": []}
   ```

3. **Ask about target settings** (or use defaults):
   - Resolution: default `"1920x1080"`, ask if shooting 4K (`"3840x2160"`)
   - Frame rate: default `30`, ask if they prefer 24 or 60

4. **Generate the checklist:**
   ```python
   from workshop_video_brain.production_brain.skills.capture_prep import generate_capture_checklist
   checklist_md = generate_capture_checklist(shot_plan, target_resolution, target_fps)
   ```

5. **Present the checklist** with additional personalized notes:
   - If the user mentioned specific gear, add notes about that gear
   - If the workspace has previous shoots, mention lessons from those
   - Highlight any must-have shots they might miss
   - If shooting conditions are mentioned (outdoor, low light), adjust lighting notes

## Output Format

Present the markdown checklist directly. Add a brief intro like:

> Here is your capture prep checklist for **{title}**. I have optimized the shot order to minimize setup changes.

Then the full checklist markdown, followed by any personalized notes.

## After the shoot: what ingest will do (set expectations now)

Capture prep should tell the creator what happens the moment the footage lands,
so they shoot with that pipeline in mind. Once files are in `media/raw/`:

1. `media_ingest` — one call runs the whole ingest brain: scan assets, generate
   proxies, transcribe, and detect silences. Everything below hangs off this.
2. `proxy_attach` — wire the generated proxies into the working copy so Kdenlive
   edits smoothly against lightweight files (revert with `proxy_detach` before
   final render). Mention this if they're shooting 4K/high-bitrate — it's why
   editing stays responsive.
3. `clips_detect_scenes` — split a long continuous recording into shot boundaries
   (via `scdet`), and `media_segment_at_silence` — split a long take into
   per-take files at detected silences. Tell the creator: **leave a beat of
   silence between takes** so this segmentation works cleanly.
4. `media_stabilize` — two-pass FFmpeg vidstab for any handheld/shaky shot.
   Flag on the checklist which shots are handheld so they're candidates.

This is a pre-shoot skill, so you don't run these — you set the expectation and
optimize the shoot for them (silence between takes, note handheld shots, flag
high-bitrate sources for proxying).

---

## Example

User: "I'm about to film the dovetail tutorial, can you get me a checklist?"

Response: Load the shot plan from the workspace, generate the checklist at 1080p/30fps, present it with notes about the specific shots in the plan.

---

## Failure contract

Every ForgeFrame tool returns a structured error dict carrying `error_type` +
a plain `suggestion` (never a traceback). Read `suggestion` first; the full
taxonomy is in the vault's [[MCP Error Catalog]].
