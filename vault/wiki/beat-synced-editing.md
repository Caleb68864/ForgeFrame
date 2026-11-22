# Beat-synced editing

Prompt 23, 2026-11-22. Tools `beat_cut`, `beat_zoom`, `beat_flash` (`server/bundles/beat_sync.py`); maths `pipelines/beat_sync.py`; zoom train `pipelines/camera_moves.zoom_punch_train`. Input: `reports/beat_grid.json` from `music_beat_grid` (beats in seconds of the music file).

## Beat to timeline frame

A beat at `b` seconds of the music file sits at timeline frame `music_start + round(b * fps) - music_in`, where `music_start` is the music clip's timeline start and `music_in` its source in-point; beats outside the clip's used `[in, out]` range are skipped and counted. The music clip is found on an audio track by its file (the grid's `source`), or named with `music_track` + `music_clip_index`, or replaced by `music_offset_seconds` (music starts there from its beginning: `round((offset + b) * fps)`).

## Variety

Cutting on every beat looks robotic. `intensity` sets the stride: subtle = every 4th beat, medium = every 2nd, aggressive = every beat. There is no downbeat detection, so a bar is every 4th beat from `phase`; bar beats are always kept. `every_n` overrides the stride.

## Cuts

`beat_cut` keeps clip order and the first clip's start; each following cut moves to the next selected beat at least `min_clip_seconds` on. Only out-points change (`TrimClip`), on the video clip and its linked audio entry, then producer lengths are raised to cover the new out-points (rule 14). A clip without enough source stops short (`off_beat`); with no beat left, clips keep their length; nothing is dropped or reordered.

## Pulses: one filter per clip

Zooms and flashes merge every beat on a clip into one keyframe track (`merge_pulses`): rest, rise to the peak at the beat, decay back; the next beat's attack truncates the previous decay, and keyframes stay inside the clip.

## Brightness, not opacity

A flash is a `brightness` filter with keyframed `level` (1 at rest, `1 + strength` at the beat). An opacity spike, as another project did it, dips the clip towards the black background: it reads as a dark flicker, not a flash. Measured on a mid-grey clip: luma 235 on the beat vs 126 six frames later.
