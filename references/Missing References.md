# Missing References -- Phase 3 Pipeline Completeness

## EBU R128 Loudness Standard (PDF)

- **Technology:** EBU R128
- **What was tried:** WebSearch for the PDF. Source URL: `https://tech.ebu.ch/docs/r/r128.pdf`
- **Why it failed:** PDF likely behind EBU member access or paywall
- **Impact:** Low. The key thresholds are already documented:
  - YouTube target: -14 LUFS integrated
  - Minimum acceptable: -24 LUFS
  - True peak max: -1 dBTP
  - These values are in the spec and in `references/ffmpeg-filters-qc.md`
- **Alternative:** The loudnorm filter documentation covers the EBU R128 implementation in FFmpeg

## Vimeo Compression Guidelines

- **Technology:** Vimeo upload encoding recommendations
- **What was tried:** WebFetch of `https://vimeo.com/help/compression` -- redirected to `https://help.vimeo.com/hc/en-us`
- **Why it failed:** Page structure changed; redirect to generic help center
- **Impact:** Low. The vimeo-hq profile uses ProRes 422 HQ (prores_ks profile 3) with AAC 320kbps audio, which is a well-established high-quality delivery format accepted by Vimeo.
- **Alternative:** Manually visit `https://help.vimeo.com` and search for "compression" or "upload guidelines"

## FFmpeg Wiki Pages (trac.ffmpeg.org)

- **Technology:** FFmpeg encoding guides (H.264, VFX/ProRes, Frame Rate)
- **What was tried:** WebFetch of `https://trac.ffmpeg.org/wiki/Encode/H.264`, `Encode/VFX`, `ChangingFrameRate`
- **Why it failed:** All blocked by Anubis access protection system
- **Impact:** None. Equivalent information was harvested from alternative sources (Academy Software Foundation ProRes guide, community tutorials, web search results)
- **Alternative:** These pages are accessible via regular browser; bookmark for future reference
