---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: proxy wiring"
author: analysis agent
tags: [kdenlive-mcp, research, proxy, performance, rendering]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcripts:
  - "vault/Transcripts/Kdenlive Tutorials/2024 Kdenlive Tutorial - Best Proxy Settings for Performance and Quality.md"
---

# Proxy Editing → Producer/Doc Wiring → MCP Tool Surface Mapping

Drives **§3 Medium "Proxy wiring"**: `proxy_generate` creates proxy files under
`media/proxies/` but never tells the project to *use* them — nothing sets
`kdenlive:proxy` on producers, so Kdenlive ignores the generated files. This
analysis verifies *exactly how Kdenlive marks a proxied clip* against the KDE
source, then documents the build (`proxy_attach` / `proxy_detach` /
`proxy_status`) and the one genuinely load-bearing subtlety: **the saved-file
`resource` points at the proxy, so a headless `melt` render would silently
render low-res unless we swap resources back to originals first.**

Tutorial analysed: *Victoriano de Jesus*, "2024 Kdenlive Tutorial - Best Proxy
Settings for Performance and Quality" (`gXz-g0khrWs`, 10:11, Kdenlive **23.08.4**).

---

## How Kdenlive marks a proxied clip — VERDICT (verified against KDE source)

Confirmed from the KDE dev-docs file-format spec
([`dev-docs/fileformat.md`](https://github.com/KDE/kdenlive/blob/master/dev-docs/fileformat.md)),
[`src/bin/projectclip.cpp`](https://github.com/KDE/kdenlive/blob/master/src/bin/projectclip.cpp),
[`src/render/renderrequest.cpp`](https://github.com/KDE/kdenlive/blob/master/src/render/renderrequest.cpp),
[`src/ui/configproxy_ui.ui`](https://github.com/KDE/kdenlive/blob/master/src/ui/configproxy_ui.ui),
[`data/encodingprofiles.rc`](https://github.com/KDE/kdenlive/blob/master/data/encodingprofiles.rc),
and cross-checked against a real proxied project
([keszybz/sd-boot-video](https://github.com/keszybz/sd-boot-video/blob/main/sd-boot.kdenlive))
and TheDiveO's format autopsy
([Inside Kdenlive Projects: Proxy Clips](https://thediveo-e.blogspot.com/2016/09/inside-kdenlive-projects-proxy-clips.html),
author of `kdenlive-project-analyzer`). Proxy state is **three linked pieces**:
per-producer properties, document-level settings, and a render-time swap.

### 1. Bin producer properties — VERIFIED keys

For a clip with an *active* proxy, the bin `<producer>` carries all three:

| property | value when proxied | notes |
|---|---|---|
| `resource` | the **PROXY** file path | MLT's only source-of-truth; MLT has no proxy concept |
| `kdenlive:proxy` | the **PROXY** file path | Kdenlive-only. Sentinel `"-"` = "no proxy for this clip" |
| `kdenlive:originalurl` | the **ORIGINAL** source path | Kdenlive-only; used to restore/render originals |

`dev-docs/fileformat.md` verbatim:
- `kdenlive:originalurl` — "Stores the clip's original url. Useful to retrieve
  original url when a clip was proxied."
- `kdenlive:proxy` — "Stores the url for the proxy clip, or `\"-\"` if no proxy
  should be used for this clip."

`projectclip.cpp`: setting a proxy does `setProducerProperty("kdenlive:originalurl", url())`;
clearing it (`"-"`/empty) does `setProducerProperty("resource", getProducerProperty("kdenlive:originalurl"))`.
So **when proxy is active, `resource` == proxy path**, and the original lives
*only* in `kdenlive:originalurl`.

### 2. Document-level settings — `kdenlive:docproperties.*` on `main_bin`

Exact key strings (prefix `kdenlive:docproperties.`), verified against
`configproxy_ui.ui` + real project files:

| key | example | meaning |
|---|---|---|
| `enableproxy` | `1` | project proxy master switch |
| `generateproxy` | `1` | auto-generate video proxies |
| `proxyparams` | ffmpeg arg string (below) | encode args for proxy generation |
| `proxyextension` | `mp4` (Kdenlive default `mkv`/`mov`) | proxy container extension |
| `proxyminsize` | `1000` | min video width (px) to auto-proxy |
| `proxyresize` | `640` | target proxy width (px) |
| `proxyimageminsize` | `2000` | min image width to image-proxy |
| `proxyimagesize` | `800` | target image-proxy width |
| `generateimageproxy` | `0` | auto-generate image proxies |
| `enableexternalproxy` | `0` | use camera-provided proxies |

`%width` in `proxyparams` is Kdenlive's placeholder substituted from
`proxyresize`. Kdenlive's current x264 default (`encodingprofiles.rc`):
`-vf scale=%width:-2 -vsync 1 -c:v libx264 -g 1 -bf 0 -vb 0 -crf 20 -preset veryfast -c:a aac -ab 128k`.

**We emit params matching OUR generator** (`adapters/ffmpeg/proxy.py`, which
encodes 720p x264 CRF 23) so the doc settings describe the files we actually
produce: `proxyparams = -vf scale=-2:720 -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k`,
`proxyextension = mp4`, `proxyresize = 720`.

### 3. Render-time swap — the CRITICAL behaviour

**Yes: the on-disk `resource` points at the proxy at edit time.** A headless
`melt project.kdenlive -consumer null/avformat` reads `resource` and would render
the **low-res proxy**. MLT does *not* understand any `kdenlive:*` property, so it
will never honour `kdenlive:originalurl` on its own.

Kdenlive never renders the saved file directly. `renderrequest.cpp`
`RenderRequest::process()`:

```cpp
if (!m_proxyRendering && project->useProxy()) {
    KdenliveDoc::useOriginals(doc);   // resets every producer resource ← kdenlive:originalurl
    modified = true;
}
```

`m_proxyRendering` is the render dialog's "Use Proxy Clips" checkbox
(`renderwidget.cpp`). Unticked (normal full-res render) → `useOriginals` swaps
every proxied producer's `resource` back to its `kdenlive:originalurl` in a
temporary scene-list before invoking melt. `useOriginals` became a static helper
in Kdenlive 23.08.0. Official docs concur:
[Proxy Clips](https://kdenlive.org/en/project/kdenlive-proxy-clips/) — "proxy
clips will be replaced with the originals for the full resolution when
rendering."

**Consequence for this tool → implemented `use_originals()`:** for every producer
where `kdenlive:proxy not in ("", "-")`, set `resource = kdenlive:originalurl`
before feeding melt a full-res render. `pipelines/proxy_wiring.use_originals`
reproduces Kdenlive's `useOriginals`, and `run_render` (the real melt path, via
`adapters/render/executor`) renders a swapped originals-copy for every mode
except the explicit `"proxy"` mode. Fast proxy-preview stays available on demand;
final/standard renders can **never** silently use proxies.

---

## Tutorial's recommended settings

Vic's "best balance" recommendations (23.08.4 GUI):
- **Enable proxies** for videos larger than **1000 px** width (`proxyminsize=1000`,
  the default) — 4K footage was the trigger in the demo.
- **Encoding profile: x264 (CPU)** for portability — NVENC/AMF/QSV/VAAPI are
  hardware-specific and NVENC's quality was visibly grainier. (Our generator is
  x264, matching this recommendation.)
- **Proxy size 640 px** default; bump toward **960 px** for
  color-critical/ProRes work (quality vs performance trade-off).
- **ProRes custom profile** (`.mov`) when the proxy must track the original
  closely for grading; heavier to encode but near-lossless preview.
- Additionally drop **timeline preview resolution to 540p** — a *preview* knob,
  not a project/producer property, so out of scope for file wiring.

Takeaway that shaped defaults: proxies are a GUI **editing-performance** feature;
the delivered render must always come from originals. That is exactly why our
render path force-swaps to originals.

---

## Capability mapping

| Step | MCP tool | Status (before → after) | Notes |
|---|---|---|---|
| Generate proxy files | `proxy_generate(workspace_path)` | existed | writes `media/proxies/{stem}_proxy.mp4`; never wired into project |
| **Wire existing proxies into the project** | `proxy_attach(workspace_path, project_file, source="", proxy_path="", all_clips=False)` | **missing → BUILT** | sets `resource`=proxy, `kdenlive:proxy`, `kdenlive:originalurl` per producer + `enableproxy`/`proxyparams`/… docproperties; snapshots first; default auto-wires every producer that has a matching `media/proxies/{stem}_proxy.mp4` |
| **Revert producers to originals** | `proxy_detach(workspace_path, project_file, source="", all_clips=False)` | **missing → BUILT** | `resource`←`kdenlive:originalurl`, `kdenlive:proxy="-"`; clears `enableproxy` when none remain |
| **Report proxy state** | `proxy_status(workspace_path, project_file)` | **missing → BUILT** | read-only; per-producer original vs proxy vs missing-proxy-file |
| Full-res render safety | `use_originals` in `run_render` | **new invariant** | non-`proxy` renders swap `resource`←original; melt never renders a proxy silently |

---

## Built artifacts (this work)

- **Model** `core/models/kdenlive.py`: `KdenliveProject.docproperties: dict[str,str]`
  (suffix-keyed `kdenlive:docproperties.*` bag for non-managed doc settings, incl.
  proxy). Producer-level `kdenlive:proxy` / `kdenlive:originalurl` already
  round-trip through the existing `Producer.properties` dict (they are not in
  `_MANAGED_PROPS`).
- **Serializer** `adapters/kdenlive/serializer.py`: emits `project.docproperties`
  onto the `main_bin` playlist after the serializer-managed docproperties.
- **Parser** `adapters/kdenlive/parser.py`: reads `kdenlive:docproperties.*` off
  `main_bin` into `docproperties`, excluding the serializer-regenerated keys
  (version/profile/uuid/guides/subtitlesList/activeSubtitleIndex), so proxy
  settings round-trip and managed keys never duplicate.
- **Pipeline** `pipelines/proxy_wiring.py` (pure): `default_proxy_path`,
  `is_proxied`, `proxyable_producers`, `attach_proxies`, `detach_proxies`,
  `proxy_status`, `use_originals`, `originals_render_copy`, `PROXY_PARAMS`.
- **Render** `pipelines/render_pipeline.py`: `run_render` renders an
  originals-swapped copy for every mode except `"proxy"`.
- **Bundle** `server/bundles/proxy_wiring.py`: `proxy_attach`, `proxy_detach`,
  `proxy_status` (auto-discovered; snapshot-before/after; `{"status":...}`).

### Round-trip / render honesty

- Producer `kdenlive:proxy`/`kdenlive:originalurl` and the doc-level proxy
  settings **round-trip** through parser→serializer→parser losslessly.
- The wired project **melt-accepts** (`melt file.kdenlive -consumer null`).
- A real proxy generated by the existing machinery for a `testsrc` clip is
  reported by `proxy_status` and wired by `proxy_attach` (external oracle test).
- `run_render` swaps to originals → a proxied project renders at full
  resolution, verified by resource inspection + the `use_originals` unit test.

---

## Raw summary

- **Verified keys:** producer `resource`(=proxy when active), `kdenlive:proxy`
  (proxy path; `"-"` sentinel = none), `kdenlive:originalurl` (original);
  doc `kdenlive:docproperties.{enableproxy,generateproxy,proxyparams,proxyextension,proxyminsize,proxyresize,proxyimageminsize,proxyimagesize,generateimageproxy,enableexternalproxy}`.
- **Render answer:** saved `resource` = PROXY at edit time; headless melt must
  render ORIGINALS → we swap `resource`←`kdenlive:originalurl` (Kdenlive's
  `KdenliveDoc::useOriginals`) for all non-`proxy` renders.
- **Built tools:** `proxy_attach`, `proxy_detach`, `proxy_status`.
- **Not-modelled:** image proxies, external/camera proxies, per-hardware encode
  profiles (NVENC/AMF/QSV/VAAPI), timeline preview-resolution knob.
</content>
</invoke>
