# Kdenlive Test-Suite Coverage Audit

Source: [KDE/kdenlive-test-suite/projects](https://github.com/KDE/kdenlive-test-suite/tree/master/projects) (59 `.kdenlive` files).

This audit groups Kdenlive features by **family** (effect class, transition class, producer class) rather than per-file. The matrix was populated by sampling 24 representative files spanning every distinct shape in the suite (a single `avfilter-X.kdenlive` is structurally identical to every other `avfilter-Y.kdenlive` — one `avfilter.<name>` filter on one `avformat-novalidate` clip — so once the shape is verified, the rest extend by parameter only).

Coverage status legend: ✅ correct shape we already emit / ⚠️ implemented but wrong shape (opaque-at-root, broken in 25.x) / ❌ no current support.

---

## ❌ Gaps — no current support

| Family | Specific kdenlive_id values seen | Test files | Status | What we'd need |
|---|---|---|---|---|
| **Audio crossfade (clip mix)** | `mix` transition with `kdenlive:mixcut` between adjacent audio clips | [audio-mix](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/audio-mix.kdenlive), [mix-luma](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mix-luma.kdenlive), [mix-slide](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mix-slide.kdenlive) | ❌ | Per-cut `mix` transition w/ `kdenlive:mixcut=<frames>` (already-active track summer is different); add to SequenceTransition for adjacent same-track audio |
| **Color/exposure grading (avfilter family)** | `avfilter.eq`, `avfilter.colorbalance`, `avfilter.huesaturation`, `avfilter.exposure`, `avfilter.colorlevels`, `avfilter.colorcontrast`, `avfilter.colortemperature`, `avfilter.colorcorrect`, `avfilter.colorize`, `avfilter.curves`, `avfilter.histeq` | [avfilter-eq](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-eq.kdenlive), [avfilter-colorbalance](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-colorbalance.kdenlive), [avfilter-huesaturation](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-huesaturation.kdenlive) | ❌ | Generic `EntryFilter` shape: `mlt_service=avfilter.<name>` + `kdenlive_id=avfilter.<name>` + scalar params; add registry of supported avfilter ids and a single emitter |
| **3-way colour (lift/gamma/gain)** | `lift_gamma_gain` | [mlt-plus-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-plus-video-effects.kdenlive) | ❌ | EntryFilter w/ 9 scalar params (lift_r/g/b, gamma_r/g/b, gain_r/g/b); model + serializer entry |
| **Blur (avfilter)** | `avfilter.gblur`, `avfilter.boxblur`, `avfilter.bilateral`, `avfilter.dblur`, `avfilter.fftfilt`, `avfilter.fftdnoiz`, `box_blur` | [avfilter-gblur](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-gblur.kdenlive), [avfilter-boxblur](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-boxblur.kdenlive), [avfilter-fftdnoiz](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-fftdnoiz.kdenlive) | ❌ | Same generic avfilter EntryFilter as colour; one preset per kind |
| **Chroma / luma keying (native MLT)** | `chroma`, `chroma_hold`, `lumakey`, `avfilter.chromahold`, `avfilter.colorhold`, `avfilter.hsvhold` | [mlt-plus-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-plus-video-effects.kdenlive), [avfilter-chromahold](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-chromahold.kdenlive), [avfilter-hsvhold](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-hsvhold.kdenlive) | ❌ | EntryFilter w/ proper kdenlive_id (we have effect_chroma_key opaque-at-root, but native `chroma`/`lumakey` ids are simpler than what we wrap) |
| **Slide / wipe transition** | `affine` w/ `kdenlive_id=luma`, `resource=""`, `softness`, `reverse` | [mix-slide](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mix-slide.kdenlive) | ❌ | Add `affine`-shape branch in SequenceTransition; very close to current luma path but mlt_service differs |
| **Compositing blend modes (cairoblend)** | `frei0r.cairoblend` as transition w/ `blend_mode` param | [mix-luma](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mix-luma.kdenlive), [mix-slide](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mix-slide.kdenlive) | ❌ | Track-level transition variant; we already emit qtblend cross-track but cairoblend is the path for Photoshop-style blend modes |
| **Multi-sequence projects** | 5 sub-tractors w/ unique `kdenlive:uuid`, `kdenlive:sequenceproperties.*` per sequence, sub-sequence as a producer in another | [sequences](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/sequences.kdenlive) | ❌ | Serializer needs a list of sequences; main projectTractor wraps all; nested sequence consumed via `producer mlt_service=xml` |
| **Native fade-from/to-black (video)** | `brightness` w/ `kdenlive_id=fade_from_black` / `fade_to_black` | [audio-mix](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/audio-mix.kdenlive), [avfilter-fade](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-fade.kdenlive), [effect-zones](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/effect-zones.kdenlive) | ❌ | Per-clip EntryFilter mirror of audio fades but service=`brightness`, kdenlive_id=`fade_from_black`/`fade_to_black`, level keyframes 0→1 / 1→0 |
| **Subtitle sidecars** | `.srt` reference + `avfilter.subtitles` filter | (not in suite, prior survey) | ❌ | Sidecar emit + filter on dedicated subtitle track |
| **Geometry (mirror/flip/crop/rotate via MLT core)** | `mirror`, `crop`, `avfilter.hflip`, `avfilter.fieldorder`, `affine`/`affinerotate` (filter, not transition) | [mlt-core-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-core-video-effects.kdenlive), [mlt-plus-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-plus-video-effects.kdenlive), [avfilter-hflip](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-hflip.kdenlive) | ❌ | Trivial scalar EntryFilters; share avfilter generic emitter |
| **Stylise (charcoal/sepia/invert/threshold/strobe)** | `sepia`, `charcoal`, `invert`, `threshold`, `strobe`, `greyscale`, `gamma` | [mlt-core-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-core-video-effects.kdenlive), [mlt-plus-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-plus-video-effects.kdenlive), [effect-zones](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/effect-zones.kdenlive) | ❌ | One scalar EntryFilter each, shared infrastructure |
| **Drawing overlays** | `avfilter.drawbox`, `avfilter.drawgrid` | [avfilter-drawbox](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-drawbox.kdenlive), [avfilter-drawgrid](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-drawgrid.kdenlive) | ❌ | EntryFilter scalar params (x,y,w,h,colour,thickness); useful for branding/lower-thirds |
| **Dynamic text & timer** | `dynamictext`, `timer` (filter w/ tag-replaced text rendering) | [mlt-plus-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-plus-video-effects.kdenlive) | ❌ | EntryFilter w/ argument-template + font params; nice for project-aware overlays |
| **Typewriter title animation** | `kdenlivetitle` xmldata w/ `typewriter="1;8;1;0;0"` attribute on `<content>` | [typewriter-effect](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/typewriter-effect.kdenlive) | ❌ | Extend kdenlivetitle xmldata builder to accept typewriter tuple (mode;speed;variation;seed;sigma) |
| **Effect zones (in/out range on a filter)** | `kdenlive:zone_in` / `kdenlive:zone_out` props on `<filter>` to scope effect to a sub-range of a clip | [effect-zones](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/effect-zones.kdenlive) | ❌ | Optional in/out fields on EntryFilter model + serializer |
| **Image enhance / denoise (avfilter)** | `avfilter.cas`, `avfilter.deband`, `avfilter.grayworld`, `avfilter.colorchannelmixer`, `avfilter.colormatrix`, `avfilter.colorspace`, `avfilter.dilation`, `avfilter.erosion`, `avfilter.epx`, `avfilter.hqx`, `avfilter.chromanr` | [avfilter-cas](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-cas.kdenlive), [avfilter-grayworld](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-grayworld.kdenlive), [avfilter-deband](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-deband.kdenlive) | ❌ | Same generic avfilter emitter; ship as long-tail enum once core works |
| **Rotoscoping / shape mask** | `mask_start-rotoscoping`, `mask_apply`, `shape`, `obscure`, `pillar_echo`, `spot_remover` | [mlt-core-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-core-video-effects.kdenlive), [mlt-plus-video-effects](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mlt-plus-video-effects.kdenlive) | ❌ | Mask pair emits two filters; we have opaque mask_set/apply which need rewiring as proper EntryFilters |
| **Chromashift / FFT denoise / edge detect (artistic)** | `avfilter.chromashift`, `avfilter.fftdnoiz`, `avfilter.edgedetect`, `avfilter.fillborders` | [avfilter-chromashift](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-chromashift.kdenlive), [avfilter-edgedetect](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-edgedetect.kdenlive), [qtblend-freeze](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/qtblend-freeze.kdenlive) | ❌ | Long-tail; freebie once generic avfilter shape lands |
| **frei0r colour effects** | `frei0r.brightness`, `frei0r.colorize`, `frei0r.curves` | [qtblend-freeze](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/qtblend-freeze.kdenlive), [avfilter-curves](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/avfilter-curves.kdenlive) | ❌ | Note: these are different kdenlive_ids than the 16 frei0r tools we have at root; need EntryFilter shape, not document-level |
| **`kdenlive:mixcut` on luma transitions** | numeric prop on `mix` / `luma` / `affine` transitions | [audio-mix](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/audio-mix.kdenlive), [mix-luma](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mix-luma.kdenlive), [mix-slide](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mix-slide.kdenlive) | ❌ | Prior survey gap; small addition to SequenceTransition emitter |

---

## ⚠️ Wrong shape — implemented but broken in 25.x

| Family | Symptom | Fix |
|---|---|---|
| `track_mute` / `track_visibility` | Emits opaque XML at document root; 25.x ignores it | Move to per-track `<tractor>` properties (`hide`, `kdenlive:audio_track`) |
| Generic `effect_add` | Document-root `<effect>` element doesn't exist in MLT | Replace with EntryFilter intent into the clip's `<entry>` |
| 16 × `effect_frei0r_*` tools | Same opaque-root problem | Convert each to EntryFilter w/ `mlt_service=frei0r.<name>` + `kdenlive_id=frei0r.<name>` |
| `effect_grain` / `effect_oldfilm` / `effect_dust` / `effect_scratchlines` / `effect_tcolor` | Opaque-root | EntryFilter shape |
| `effect_chroma_key` / `effect_chroma_key_advanced` | Opaque-root + wrong kdenlive_id | Re-emit as `mlt_service=chroma` or `frei0r.bluescreen0r` EntryFilter |
| `mask_set` / `mask_apply` | Opaque-root | EntryFilter pair using `mask_start` + `mask_apply` ids |

---

## ✅ Correct shape today

| Family | Test files matching our shape |
|---|---|
| `qtblend` per-clip transform (Ken Burns / PIP / parallax) | [qtblend-rotate](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/qtblend-rotate.kdenlive), [qtblend-zoom](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/qtblend-zoom.kdenlive), [transform](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/transform.kdenlive) |
| `qtblend` cross-track transition | [qtblend-transition](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/qtblend-transition.kdenlive), [alpha](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/alpha.kdenlive) |
| `luma`/`dissolve` transition + `mix` always-active track summer | [mix-luma](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/mix-luma.kdenlive) |
| Audio fadein/fadeout (`volume` filter w/ `fadein`/`fadeout` kdenlive_id) | [audio-mix](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/audio-mix.kdenlive) |
| Per-track `audiolevel` + `panner` + `volume` filters | every file — universal |
| `avformat` + `avformat-novalidate` clips w/ bin twin | every file w/ media — universal |
| `color` / `qimage` / `kdenlivetitle` producers | [qtblend-freeze](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/qtblend-freeze.kdenlive), [typewriter-effect](https://github.com/KDE/kdenlive-test-suite/blob/master/projects/typewriter-effect.kdenlive) |
| `timewarp` clip-speed producer | (verified by our smoke test, not in suite) |

---

## Top-5 leverage picks

The five patterns that would unlock the most real-world video work for the least serializer surface:

1. **Generic avfilter EntryFilter emitter** — *medium*. One model class + one serializer branch unlocks ~30 files in the suite at once (eq, colorbalance, huesaturation, exposure, curves, gblur, boxblur, drawbox, edgedetect, chromahold, etc.). This is the single biggest leverage point because every avfilter has the same shape.
2. **Native fade-from-black / fade-to-black video filters** — *small*. Mirrors the audio-fade pattern we already have but with `mlt_service=brightness`, `kdenlive_id=fade_from_black|fade_to_black`. Used in almost every cut sequence.
3. **Audio crossfade (`mix` transition + `kdenlive:mixcut`)** — *small*. Closes the long-standing voiceover gap; SequenceTransition already emits transitions, just add the audio-mix branch with mixcut frames.
4. **Lift/gamma/gain 3-way colour grade** — *small*. One EntryFilter w/ 9 scalars; ships colour grading without needing the avfilter machinery first.
5. **Multi-sequence projects** — *large*. Requires serializer-wide refactor: list of sub-sequences, projectTractor wrapping multiple sub-tractors, nested-sequence consumed via `mlt_service=xml`, sequenceproperties keyed per UUID. Worth it because it unblocks chapter-style and pickup-cut workflows.

Items 1+2+3+4 together are roughly one focused work-week and would close the bulk of the practical gap; item 5 is its own project.
