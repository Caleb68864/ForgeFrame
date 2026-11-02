# Scene detection engines

`pipelines/scene_detect.scan_cuts` returns `(engine_used, [(cut_seconds, score)])` from either engine. The default stays `ffmpeg`. `engine="auto"` prefers PySceneDetect when the `scene-detect` extra is installed.

## What each one scores

| Engine | Knob | Score |
| --- | --- | --- |
| `ffmpeg` | `threshold`, 0..1 | ffmpeg's `scene` value, 0..1 |
| `pyscenedetect`, `content` | `detector_threshold`, default 27.0 | `content_val / 255` |
| `pyscenedetect`, `adaptive` | `detector_threshold`, default 3.0 | `adaptive_ratio / (4 * threshold)`, capped at 1 |
| `pyscenedetect`, `threshold` | `detector_threshold`, default 12 | `average_rgb / 255` |

Scores are relative to their engine and are not comparable across engines. The adaptive ratio is the last metric `AdaptiveDetector.get_metrics()` lists, not the first; the first is `content_val`.

## Measured cuts

Red for 2 s, then blue for 2 s, at 25 fps (2026-11-02, scenedetect 0.6.7.1, opencv 5.0.0):

| Engine / detector | Cut | Score |
| --- | --- | --- |
| ffmpeg | 2.0 s | 0.40 |
| content | 2.0 s | 0.158 |
| adaptive | 2.0 s | 1.0 |
| threshold | none | -- |

`threshold` finds fades through black, and red and blue both stay above its floor. It does find a white, black, white clip's boundary inside the black span.

## The opencv packaging trap

- `scenedetect` 0.7 depends on `opencv-python`, the GUI build that needs libGL, and has no headless extra. So the extra pins `scenedetect[opencv-headless]>=0.6.7,<0.7`.
- `rembg` (ai-mask) pulls `opencv-python-headless`, the same wheel. `motion-track` pulls `opencv-contrib-python-headless`.
- Every one of those wheels owns `cv2/`, and two in one venv overwrite each other's files. The headless and contrib pair at 5.0.0.93 was checked: `import cv2` works and the trackers are present. Mismatched versions are not guaranteed to.

## Limits

PySceneDetect decodes in-process, so unlike the ffmpeg engine it has no timeout. An unreadable file raises `SceneDetectError` and is never reported as zero cuts.

## Tools

- `clips_detect_scenes`, `research_detect_scenes` and visual-research candidates take `engine`, defaulting to `ffmpeg`.
- `media_split_scenes` writes one file per shot and defaults to `auto`.
- `guide_add_scene_cuts` puts a guide on the timeline frame of each cut, wherever the source is placed. A speed-changed placement is skipped, because its frames are not source frames.
