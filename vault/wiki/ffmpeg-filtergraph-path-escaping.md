# Paths inside an ffmpeg filtergraph must be escaped

Any filesystem path interpolated into an **ffmpeg filtergraph option value**
must go through `pipelines/_common.escape_filter_path`. A raw path is not
safe, and the failure is invisible on POSIX and fatal on Windows.

## The rule

    forward slashes  •  ":" → \\:  (two)  •  "'" → \\\'  (three)

```python
from workshop_video_brain.edit_mcp.pipelines._common import escape_filter_path

f"vidstabdetect=result={escape_filter_path(trf_path)}"
```

## Why it looks wrong (and why the obvious version fails)

A filtergraph description is unescaped **twice** before a filter sees its
argument — once by the graph parser splitting filters and options, once by
the filter's own option parser. Every intuition built on a single escaping
level is wrong here.

Established empirically against a real ffmpeg (`vidstabdetect result=`,
2-second `testsrc`, checking whether the `.trf` was actually written):

| Candidate | Result |
|---|---|
| `C:\Users\...` (raw native) | fail — value truncates at drive colon |
| `C\:\Users\...` (escape colon, one backslash) | fail |
| `C\:\\Users\\...` (double backslashes + escape colon) | fail |
| `C:/Users/...` (forward slashes, raw) | fail — truncates at colon |
| **`C\\:/Users/...`** (forward slashes, **two** backslashes) | **PASS** |

Two separate traps:

1. **Native `\` separators cannot survive.** The second pass consumes `\U`
   as an escape sequence, so `C:\Users` arrives as `C:Users`. Doubling them
   doesn't rescue it either — the two passes eat one backslash each.
   Convert to forward slashes, which Windows ffmpeg accepts fine.
2. **`:` needs two backslashes, `'` needs three.** One backslash on the
   colon is stripped by the first pass, leaving a bare `:` that the second
   pass reads as an option separator. The quote character is handled a pass
   earlier, so it needs one more level again — two and four both fail:

   | Apostrophe escaping | Result |
   |---|---|
   | `caleb's` | fail |
   | `caleb\'s` | fail |
   | `caleb\\'s` | fail |
   | **`caleb\\\'s`** | **PASS** |

Spaces need no escaping at all.

## Where it applies

Four call sites across three pipelines, all found by auditing for *any* path
interpolated into a filter string:

| Site | Option | Failure mode on Windows |
|---|---|---|
| `stabilize.build_detect_filter` | `vidstabdetect result=` | hard error |
| `stabilize.build_transform_filter` | `vidstabtransform input=` | hard error |
| `qc_scan.build_video_filter` | `metadata=print:file=` | **silent** |
| `scene_detect.build_select_filter` | `metadata=print:file=` | **silent** |

The two `metadata=print:file=` sites are the nastier pair. Both callers read
the stats file back behind an `if stats_file.exists()` guard, so a path that
never got written degrades into an *empty result* — `clips_qc_scan` reports
no quality issues, `detect_scenes` reports no scenes — rather than an error.
A tool that confidently returns "nothing wrong" is worse than one that
crashes.

## How this bit us — twice

The escaper originally existed as a private `_escape_ff` inside
`server/bundles/subtitle_track.py`, a **shell** module. `pipelines/stabilize.py`
could not import it without inverting the layering, so it interpolated the
`.trf` path raw into `vidstabdetect`'s `result=` and `vidstabtransform`'s
`input=`. `media_stabilize` was broken on every Windows workspace while
Linux CI stayed green.

The second lesson is sharper: **the private copy was itself wrong.** It used
the plausible single-level escaping (`\\` → `\\\\`, `:` → `\:`), so
`subtitles_burn_in` was *also* broken on Windows — the duplication had
hidden a shared defect behind an appearance of one correct implementation
and one missing one. Only running both filters against a real ffmpeg
surfaced it; the unit tests written against the plausible rule passed
happily and proved nothing.

Two takeaways worth generalising:

- A helper parked in a shell module cannot be reused by the pipeline layer
  the architecture points downward to. Promote domain primitives to
  `pipelines/_common.py` at the moment they appear — CLAUDE.md authoring
  checklist item 5.
- Escaping rules are **empirical**. Assert them against the real binary, not
  against a reading of the syntax. `tests/unit/test_common_filter_escape.py`
  pins the verified values; `scratchpad` probes generated them.
- A test that only asserts success proves little. Every case in
  `tests/integration/external/test_filter_path_escaping.py` was
  mutation-checked — the escaper was temporarily replaced with `str(path)`
  and all 15 positive cases confirmed to go red — and the file carries a
  standing negative control asserting the *old* escaping still fails. A
  plain path succeeds under any escaping at all, so without the awkward-path
  parametrisation and that control, the suite would be decorative.

## Related

- `/dev/null` has the same shape of defect — `Path("/dev/null")` renders as
  `\dev\null` on Windows. Use `os.devnull`.
- Kdenlive resource paths are a *different* rule: those use forward slashes
  (hard rule 6 in `CLAUDE.md`) but are not filtergraph-escaped.
