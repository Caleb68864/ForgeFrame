---
name: ff-reaction-gif
description: "Turn a specific movie line or moment into a short captioned reaction GIF, working from subtitles, contact sheets and shot-cut times. Use when the user asks for a reaction GIF, a GIF of a line or scene, or a captioned movie clip."
---

# ff-reaction-gif

Make a 2-3 s captioned reaction GIF of a movie line, from evidence, never from
guessed timestamps. Three steps, each an MCP tool and a `wvb gif` command:

| Step | MCP tool | CLI |
|---|---|---|
| Find the line | `gif_find_line(source, text, context=4, picture_offset=3.0, work_dir="")` | `wvb gif find SOURCE "TEXT"` |
| Fetch the scene | `gif_fetch_scene(source, start, end, out_dir="", contact_sheet=True, fine_sheet_at="", waveform_at="")` | `wvb gif scene URL MM:SS MM:SS [-o DIR] [--fine-sheet T] [--waveform T]` |
| Render | `gif_render(clip_path, start, end, caption="", output_path="", gallery_dir="", width=480, fps=15)` | `wvb gif render DIR/clip.mp4 START END "CAPTION" [-o out.gif]` |

All CLI commands take `--json`.

## Evidence-first rules

- **Never guess a timestamp.** Every time you pass on comes from a subtitle
  cue, a contact-sheet label, a shot-cut time or a waveform.
- **Lines repeat.** ("I've got it!" is said 4 times in King Solomon's Mines
  (1985).) `gif_find_line` returns every match with the 4 cues before it.
  Use the context; if the user described the scene, fetch 2-3 candidates and
  compare their contact sheets before asking which one. Do not silently pick
  the first match.
- **Subtitles run ~3 s ahead of the picture.** The `suggested_window` already
  applies that offset; use it as the ~30 s download window.
- **Look at the images.** Read the contact sheet (and fine sheet) before
  choosing GIF times, and read the check strip before delivering.
- **Stop before a cutaway** by ending ~0.04 s before the cut:
  `gif_fetch_scene` returns `end_before_cuts` for exactly that.

## Steps

1. **Find a clean source.** Tubi first (free, no DRM, yt-dlp downloads it
   directly, 480p max, includes subtitles). If Tubi search misses the title,
   find the movie URL from a cast page:
   `curl -sL -A "Mozilla/5.0" https://tubitv.com/person/<id>/<name> | grep -oE '/movies/[0-9]+/[a-z0-9-]+'`.
   YouTube fallback:
   `yt-dlp --flat-playlist --print "%(id)s | %(duration_string)s | %(title)s" "ytsearch15:<movie> <line>"`.
   Skip clips filmed off a TV with a phone. `yt-dlp -F <url>` lists qualities.

2. **Find the line.** `gif_find_line(url, "I've got it")` downloads subtitles
   only (English, manual or auto) and returns `matches`, each with `cue`,
   `context`, `picture_time` and `suggested_window` (`start_mmss`/`end_mmss`).
   A local `.srt` path works too. No match: try a shorter or differently
   worded fragment; auto-subs mishear.

3. **Fetch the scene.** `gif_fetch_scene(url, "20:15", "20:45")` downloads
   just that window (<=720p) to `clip.mp4` and returns `scene_cuts`,
   `end_before_cuts` and a 2 fps `contact_sheet` (each frame labelled with its
   time in the clip). For frame-exact work add `fine_sheet_at="15"` (6 fps
   over 3 s). To find where the line is spoken, `waveform_at="14"` (6 s;
   speech is short bursts, explosions are solid blocks). Pass the local
   `clip.mp4` as `source` to re-examine without downloading again.

4. **Render.** Times are seconds within `clip.mp4`. Start just before the
   action so it loops cleanly; 2-3 s works best.
   `gif_render(clip, "15.5", "17.52", "I'VE GOT IT!")`. 15 fps, 480 px,
   lanczos, white Liberation Sans Bold with a black outline at the bottom,
   size from width (size ~ w/10, border ~ size/12, margin ~ size/3),
   two-pass palette with bayer dither (~1.1 MB/s). Apostrophes are safe: the
   caption goes through a text file.

5. **Verify, then deliver.** Read `check_strip` (10 frames from the finished
   GIF): the caption fits and no frame from the next shot got in. Act on any
   `warnings` (a caption too wide for the GIF). Report `size_mb`,
   `duration`, `fps` and `width`, and the GIF path.

## Output

The GIF goes to the **GIF gallery**: `$WVB_GIF_GALLERY`, else
`~/Pictures/Reaction GIFs`, as `<caption-slug>.gif`, with
`<name>.check.png` beside it. Override with `output_path` / `-o` or
`gallery_dir` / `--gallery`. Subtitles and scene clips go to
`<gallery>/_work/` unless `work_dir` / `out_dir` is given.

## Reference result

King Solomon's Mines (1985), Tubi, "I'VE GOT IT!": clip 20:15-20:45, GIF
from 15.5-17.52 s in the clip; Quatermain only, ending on the frame before
the cutaway. About 10 minutes total, mostly finding the scene.
