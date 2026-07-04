# External Kdenlive examples survey

Goal: identify Kdenlive 24.x/25.x XML patterns used in real projects that our serializer does not yet emit. Inputs are the official KDE test suite (authoritative, used by upstream CI) plus the upstream `dev-docs/fileformat.md`. Per-file fetches via raw GitHub; no files downloaded locally.

## Source 1 -- KDE Kdenlive Test Suite (index)

URL: https://github.com/KDE/kdenlive-test-suite/tree/master/projects

59 `.kdenlive` files maintained by upstream. Most saved with **24.11.70** or **25.03.90**. Categories we don't cover yet: `audio-mix`, `mix-luma`, `mix-slide`, `qtblend-freeze`, `sequences`, `mlt-core-video-effects`, `mlt-plus-video-effects`, `transform`, `effect-zones`, plus 35 `avfilter-*` per-effect fixtures (one per ffmpeg filter).

## Source 2 -- audio-mix.kdenlive (24.11.70)

URL: https://raw.githubusercontent.com/KDE/kdenlive-test-suite/master/projects/audio-mix.kdenlive

Audio fades use a `<filter>` with `mlt_service=volume` plus `kdenlive_id=fadein` / `fadeout` and `gain`/`end` ramping (e.g. `gain=0`, `end=1`). Audio crossfade is a `<transition mlt_service="mix" kdenlive_id="mix">` between adjacent audio clips on stacked tracks -- distinct from the `always_active=1, sum=1` track-level mix transition. We currently emit neither.

## Source 3 -- mix-luma.kdenlive (21.12.3)

URL: https://raw.githubusercontent.com/KDE/kdenlive-test-suite/master/projects/mix-luma.kdenlive

Same-track "mix" cuts use `kdenlive:mixcut=12` on the luma transition -- a property our cross-dissolve docs omit. Also introduces `<transition mlt_service="frei0r.cairoblend">` for blend modes.

## Source 4 -- mix-slide.kdenlive

URL: https://raw.githubusercontent.com/KDE/kdenlive-test-suite/master/projects/mix-slide.kdenlive

Slide transitions are `mlt_service=affine` + `kdenlive_id=luma`, animated through a percent-based `rect` keyframe string (`-100% 0% 100% 100% 100%;...`). Same template covers wipes/page-peel by swapping the `resource` luma file.

## Source 5 -- qtblend-freeze.kdenlive (25.03.90)

URL: https://raw.githubusercontent.com/KDE/kdenlive-test-suite/master/projects/qtblend-freeze.kdenlive

Freeze frames are not a special service: a single static `rect` keyframe on `qtblend` with no ramp, paired with normal `qimage` extraction. Confirms our Ken Burns pattern generalizes.

## Source 6 -- mlt-core-video-effects.kdenlive (24.11.70)

URL: https://raw.githubusercontent.com/KDE/kdenlive-test-suite/master/projects/mlt-core-video-effects.kdenlive

Real-world `kdenlive_id`s: `box_blur`, `brightness`, `crop`, `gamma`, `greyscale`, `mirror`, `obscure`, `pillar_echo`, `mask_start-rotoscoping`, `mask_apply`. All keyframed parameters use the same `00:00:00.000=value;...` syntax as our qtblend `rect` (e.g. `hradius=00:00:00.000=0;00:00:00.400=150`).

## Source 7 -- mlt-plus-video-effects.kdenlive (24.11.70)

URL: https://raw.githubusercontent.com/KDE/kdenlive-test-suite/master/projects/mlt-plus-video-effects.kdenlive

Adds `affine`, `affinerotate`, `charcoal`, `chroma`, `chroma_hold`, `dynamictext`, `invert`, `lift_gamma_gain` (3-way colour grading), `lumakey`, `sepia`, `shape` (alpha-mask shapes), `spot_remover`, `strobe`, `threshold`, `timer`. `chroma`/`chroma_hold` are the chroma-key path; `lumakey` is the luma-key path.

## Source 8 -- sequences.kdenlive (24.01.95)

URL: https://raw.githubusercontent.com/KDE/kdenlive-test-suite/master/projects/sequences.kdenlive

Multi-sequence projects: each sequence is its own UUID-id'd tractor with `kdenlive:clipname` and `kdenlive:duration`. Guides/markers are JSON arrays in `kdenlive:sequenceproperties.guides` and `kdenlive:markers` -- markers live on the producer, guides on the sequence. Groups are JSON in `kdenlive:sequenceproperties.groups` (`AVSplit` etc.).

## Source 9 -- upstream fileformat.md

URL: https://github.com/KDE/kdenlive/blob/master/dev-docs/fileformat.md

Subtitles: separate `<project>.kdenlive.srt` sidecar referenced by an `<filter mlt_service="avfilter.subtitles">` with `internal_added=237`, `av.filename`, and `kdenlive:locked`. Confirms `kdenlive:zone_in`/`zone_out`, `kdenlive:audio_max1`, and `kdenlive:folder.x.y` clip-bin hierarchy.

## Priority backlog

1. Audio fade in/out filters (`volume` + `fadein`/`fadeout`) -- everywhere.
2. Audio crossfade transition (`mix` between stacked audio clips) -- everywhere.
3. `kdenlive:mixcut` on luma transitions -- needed for same-track mix UX.
4. Subtitle sidecar `.srt` + `avfilter.subtitles` filter -- in every captioned project.
5. Guides/markers JSON in `sequenceproperties.guides` and `markers`.
6. Multi-sequence projects (multiple tractors, per-sequence properties).
7. Slide/wipe transitions via `affine` + percent `rect` keyframes.
8. Generic keyframed effect parameters (blur, brightness ramps) using the same `time=value;` syntax.
9. Chroma/luma key (`chroma`, `chroma_hold`, `lumakey`) and shape masks.
10. 3-way colour grading via `lift_gamma_gain`; `frei0r.cairoblend` blend modes.
