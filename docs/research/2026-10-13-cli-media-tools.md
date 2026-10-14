# CLI media production research

Research date: 2026-10-13. Discussion notes, not approved roadmap work. Goal: one MCP that coordinates media editing and production from ingest to delivery.

whisper.cpp is reference-only: no installation, build, model download, adapter, or integration was performed. Fintan is the user's app and is unavailable on this machine. The user also reports FFmpeg or C# audio editing functionality; individual features and implementation details remain unknown. Fintan was not accessed or searched for; no similarly named public project is assumed to be Fintan.

## Current capabilities and useful extensions

“Existing” below means present in inspected source, not newly verified in production. Candidate features are proposals inferred from tool capabilities and project gaps.

| Tool | Relationship to ForgeFrame | Existing use | Useful capability to discuss |
| --- | --- | --- | --- |
| FFmpeg / ffprobe | Existing backend | Probing, proxies, frames, scene/silence detection, audio processing, stabilization, exports, QC | Measured audio delivery, explicit stream mapping, subtitle packaging, reusable QC reports and automatic repair previews |
| MLT / melt | Existing backend | Timeline rendering and Kdenlive effects | Capability checks against installed services; preview and final parity; editable project plus rendered delivery |
| faster-whisper / openai-whisper | Existing backend | CPU int8 faster-whisper first, fallback engine, language selection, per-word timings/confidence, SRT/JSON | Backend-independent transcript corrections, source timing provenance, vocabulary prompts, speaker labels, VAD and alignment options |
| whisper.cpp | Reference only, deferred | None | Offline portability, hardware/model selection, quantization, progress, VAD, server interface, translation; compare Fintan before selecting any backend |
| PySceneDetect | Potential optional backend | Current scene detection is FFmpeg threshold plus uniform fallback | Adaptive cuts for camera movement, fades, scene statistics, scene contact sheets and reviewable cut suggestions |
| auto-editor | Workflow reference; optional backend only if needed | Silence segmentation and selects already exist | Explainable keep/remove proposals combining audio, motion and subtitle evidence; margins, minimum holds, preview and reversible timeline edits |
| OpenTimelineIO | Potential interchange backend | Kdenlive-specific project parser/serializer | Import/export editorial timelines and media references with a report of unsupported effects; rational time and relinking |
| libass | Existing via subtitle/effect path | ASS styling, subtitle sidecars, Kdenlive subtitle attachment, force-style generation | Caption QC, readable grouping, font availability, multilingual tracks, sidecar/soft subtitle/burn-in delivery choices |
| yt-dlp | Existing research dependency | Channel/single-video metadata with `download=False` | Optional URL ingest of user-selected sources, chapters/captions/metadata, resumable acquisition and duplicate archive |
| SoX | Existing effect catalog service; standalone CLI candidate | Kdenlive/MLT SoX effect definitions | Offline audio analysis/conversion only where FFmpeg lacks a needed operation; avoid duplicate basic adapters |
| Demucs | Reference only; specialist candidate | No source-separation integration found | Optional stems for music/voice cleanup; audition quality before applying, keep original audio and record model settings |
| WhisperX | Reference only; alignment candidate | Word timestamps already exist, separate forced alignment not found | Align corrected transcripts and investigate speaker attribution only if Fintan/current engine cannot cover the workflow |

## Official sources and practical limits

FFmpeg's official filter reference describes `loudnorm` for loudness normalization and `ebur128` for measurement. ForgeFrame already has `audio_normalize_two_pass` and a measured loudnorm pipeline, while the older `audio.py` normalization path remains single-pass. The opportunity is consistent use of measured normalization, post-process QC, and before/after audition across the existing cleanup workflow. FFmpeg documentation fetch failed during this research, so exact current filter options must be checked before implementation. [Official filter reference](https://ffmpeg.org/ffmpeg-filters.html#loudnorm), [official source](https://github.com/FFmpeg/FFmpeg/blob/master/doc/filters.texi).

MLT's CLI can compose and render media with profiles, consumers and filters. Reuse that existing foundation and query installed services rather than assume every effect is available. [MLT melt documentation](https://www.mltframework.org/docs/melt/).

whisper.cpp documents local CPU/GPU execution, quantized models and VAD. Its README labels word timestamps and tinydiarize speaker segmentation experimental. Speaker turns are not a guarantee of stable named speakers. The server example exposes transcription, language detection, English translation, prompts and model loading. Use these as a Fintan review checklist, not an integration commitment. [whisper.cpp README](https://github.com/ggml-org/whisper.cpp), [server example](https://github.com/ggml-org/whisper.cpp/tree/master/examples/server).

PySceneDetect offers content, adaptive and threshold detectors, CSV scene lists, sample images and splitting. Adaptive detection compares nearby frame scores and can reduce false cuts from camera motion. Stream-copy splitting sacrifices exact cut accuracy. Candidate: keep boundaries and diagnostic thumbnails as derived annotations before touching the timeline. [CLI guide](https://www.scenedetect.com/cli/), [current CLI reference](https://www.scenedetect.com/docs/latest/cli.html).

auto-editor analyzes audio, motion and subtitles; its action system maps detected regions to edits. Its v3 format represents layered timelines, but is only partially stable across feature releases. Candidate: adopt reviewable edit rules and reason codes; assess interchange loss before adding another timeline format. [Project site](https://auto-editor.com/), [actions](https://auto-editor.com/docs/actions), [v3 specification](https://auto-editor.com/docs/v3).

OpenTimelineIO exchanges editorial timing and structure rather than rendered media. Adapter support varies, so effects/transitions need an explicit compatibility report and round-trip fixtures. Candidate: Kdenlive remains the native output while OTIO offers handoff and import. [Official repository](https://github.com/AcademySoftwareFoundation/OpenTimelineIO), [architecture](https://opentimelineio.readthedocs.io/en/v0.16.0/tutorials/architecture.html).

libass renders ASS/SSA styled subtitles. ForgeFrame already has an ASS/libass path, making caption authoring, timing checks and delivery packaging more useful than adding a second renderer. [Official repository](https://github.com/libass/libass).

yt-dlp supports format selection, caption retrieval, metadata and a download archive that skips already recorded IDs. Existing ForgeFrame usage is metadata research, not media downloading. Candidate ingest should retain source URLs, selections, chapters and file provenance. [Official repository and options](https://github.com/yt-dlp/yt-dlp).

SoX provides audio transformations and analysis. Demucs performs music source separation, but the original repository is archived; maintenance and model suitability need review before adoption. Voice isolation quality must be auditioned on the user's material. [SoX repository](https://github.com/chirlu/sox), [Demucs repository](https://github.com/adefossez/demucs).

WhisperX combines ASR with alignment and diarization, with additional model/dependency requirements. Treat corrected-word alignment and speaker attribution as separate capabilities; compare them to Fintan before choosing an implementation. [Official repository](https://github.com/m-bain/whisperX).

## Proposed discussion order

1. **Finish a production through-line:** ingest → catalog → transcript/scene analysis → proposed selects → editable assembly → audio/captions → QC → multiple deliverables → archive. Every stage should share jobs, source IDs, versions and reports.
2. **Learn from Fintan first:** use the checklist below in a later discussion, then request implementation details only for selected features. Record which features can be reused, imported or kept external.
3. **Strengthen audio and captions:** measured loudness and peaks, intelligibility previews, corrected transcripts, caption readability/timing and delivery variants. These improve existing capabilities without requiring a new STT backend.
4. **Improve suggested edits:** adaptive scenes and configurable silence/motion rules with explicit reasons and review thumbnails. Preserve source timestamps; apply edits only after a reviewable proposal.
5. **Add handoff and acquisition selectively:** OTIO interchange and URL ingest if these solve the user's actual workflows; defer specialist separation until samples show a need.

A useful MCP interface exposes actions like “prepare footage,” “propose a rough cut,” “clean dialogue,” “make captions,” and “validate delivery.” Tools should return artifacts, rationale, capabilities and job IDs. Backend selection belongs behind those actions and remains visible when it affects quality, resources or output compatibility.

## Fintan comparison checklist for a later discussion

These are capabilities to ask about, not claims that Fintan implements them.

| Area | Useful details to compare |
| --- | --- |
| Transcription | Engines/models, CPU/GPU selection, language and translation, vocabulary prompts, VAD, confidence, word timing, alignment, speaker attribution, import/export |
| Audio editing | Trim/split/join, fades/crossfades, noise reduction, EQ, compression, de-essing, loudness and peak measurement, normalization, channel mapping, sample-rate conversion, before/after audition |
| FFmpeg processing | Stream mapping, filtergraph construction, probing, progress parsing, timeouts, cancellation, temporary outputs, output verification, capability detection |
| Pipeline modularity | Separate analysis from transformations, reusable presets, typed operation descriptions, provenance, immutable originals, caching, batch queues, retry/recovery |
| C# interoperability | Whether selected functionality is available through a CLI, local API, portable library or file exchange; deployment/runtime requirements; stable job and error contracts |
| User corrections | How edits to words, speakers and timing are saved, source-time links retained, and captions/timeline decisions regenerated |

## Questions before roadmap approval

- Which productions should lead: workshop tutorials, interviews/podcasts, short social clips, or mixed footage?
- Which transcription and audio capabilities from the Fintan checklist should lead? After selecting them, request their implementation details when Fintan is available.
- Which handoff applications and final delivery formats matter first?
- Should importing online media be part of first-class ingest, or remain a separate research workflow?
