#!/usr/bin/env python3
"""Download YouTube playlist transcripts into an Obsidian vault as notes.

Fetches English subtitles (manual preferred, auto-generated fallback) for every
video in a playlist, cleans the rolling-caption VTT into readable paragraphs
with coarse ``[mm:ss]`` markers, and writes one frontmattered markdown note per
video plus a wikilink index note.

Usage:
    uv run python scripts/download_playlist_transcripts.py \
        "https://www.youtube.com/playlist?list=..." \
        --dest "~/Documents/Notes/Video Production/Research/Kdenlive Tutorials" \
        --playlist-tag kdenlive-tutorials

Notes:
    * yt-dlp's ``--print`` implies ``--simulate``, which silently skips subtitle
      file writes — metadata and subtitle download are therefore separate calls.
    * Videos with no subtitles at all are reported and skipped, not fatal.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

MARKER_INTERVAL_SECONDS = 45.0

_TIMESTAMP_LINE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s+-->"
)
_INLINE_TAG = re.compile(r"<[^>]+>")
_ILLEGAL_FILENAME = re.compile(r'[<>:"/\\|?*#^\[\]]')


@dataclass
class VideoMeta:
    video_id: str
    title: str
    channel: str = ""
    upload_date: str = ""
    duration: str = ""

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def _run_yt_dlp(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["yt-dlp", "--no-update", *args],
        capture_output=True,
        text=True,
    )


def list_playlist_videos(playlist_url: str) -> list[VideoMeta]:
    """Enumerate a playlist without downloading anything."""
    result = _run_yt_dlp(
        ["--flat-playlist", "--print", "%(id)s\t%(title)s", playlist_url]
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp playlist enumeration failed: {result.stderr.strip()}")
    videos = []
    for line in result.stdout.splitlines():
        if "\t" in line:
            vid, title = line.split("\t", 1)
            videos.append(VideoMeta(video_id=vid.strip(), title=title.strip()))
    return videos


def fetch_metadata(meta: VideoMeta) -> VideoMeta:
    """Fill in channel/date/duration (separate call: --print implies --simulate)."""
    result = _run_yt_dlp(["-j", "--skip-download", meta.url])
    if result.returncode == 0:
        try:
            info = json.loads(result.stdout)
            meta.channel = info.get("channel") or info.get("uploader") or ""
            raw_date = info.get("upload_date") or ""
            if len(raw_date) == 8:
                meta.upload_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            meta.duration = info.get("duration_string") or ""
        except json.JSONDecodeError:
            pass
    return meta


def download_vtt(meta: VideoMeta, workdir: Path) -> Path | None:
    """Download the best English VTT for a video; return its path or None."""
    template = str(workdir / f"{meta.video_id}.%(ext)s")
    result = _run_yt_dlp(
        [
            "--skip-download",
            "--no-simulate",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "en.*",
            "--sub-format",
            "vtt",
            "--sleep-requests",
            "1",
            "-o",
            template,
            meta.url,
        ]
    )
    if result.returncode != 0:
        print(f"  warning: subtitle fetch failed for {meta.video_id}: "
              f"{result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown'}",
              file=sys.stderr)
    candidates = sorted(workdir.glob(f"{meta.video_id}.*.vtt"))
    if not candidates:
        return None
    # Prefer plain "en" (manual subs) over "en-orig"/auto variants.
    for cand in candidates:
        if cand.name == f"{meta.video_id}.en.vtt":
            return cand
    return candidates[0]


def _cue_start_seconds(line: str) -> float | None:
    match = _TIMESTAMP_LINE.match(line.strip())
    if not match:
        return None
    hours, minutes, seconds, millis = (int(g) for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def clean_vtt(vtt_text: str) -> str:
    """Convert rolling-caption VTT into readable text with [mm:ss] markers."""
    lines_out: list[str] = []
    previous_line = ""
    next_marker = 0.0
    current_start: float | None = None

    for raw in vtt_text.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        start = _cue_start_seconds(line)
        if start is not None:
            current_start = start
            continue
        text = _INLINE_TAG.sub("", line).strip()
        if not text or text == previous_line:
            continue
        if current_start is not None and current_start >= next_marker:
            minutes, secs = divmod(int(current_start), 60)
            lines_out.append(f"\n[{minutes:02d}:{secs:02d}]")
            next_marker = current_start + MARKER_INTERVAL_SECONDS
        lines_out.append(text)
        previous_line = text

    paragraphs = " ".join(lines_out).replace(" \n", "\n").strip()
    return paragraphs


def sanitize_filename(title: str) -> str:
    name = _ILLEGAL_FILENAME.sub("-", title)
    name = re.sub(r"\s+", " ", name).strip(" -.")
    return name or "Untitled"


def build_note(meta: VideoMeta, transcript: str, playlist_tag: str) -> str:
    return (
        "---\n"
        f'title: "{meta.title}"\n'
        f"video_id: {meta.video_id}\n"
        f"url: {meta.url}\n"
        f"channel: {meta.channel}\n"
        f"playlist: {playlist_tag}\n"
        f"uploaded: {meta.upload_date}\n"
        f"duration: {meta.duration}\n"
        "type: reference\n"
        "tags: [kdenlive, tutorial, transcript]\n"
        "---\n"
        f"# {meta.title}\n\n"
        "## Transcript\n\n"
        f"{transcript}\n"
    )


def build_index(title: str, note_names: list[str]) -> str:
    links = "\n".join(f"- [[{name}]]" for name in note_names)
    return f"# {title}\n\n{links}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("playlist_url", help="YouTube playlist (or single video) URL")
    parser.add_argument("--dest", required=True, help="Vault folder to write notes into")
    parser.add_argument("--playlist-tag", default="playlist", help="frontmatter playlist tag")
    parser.add_argument("--index-title", default=None,
                        help="Index note title (default: destination folder name)")
    args = parser.parse_args()

    dest = Path(args.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    index_title = args.index_title or dest.name

    videos = list_playlist_videos(args.playlist_url)
    if not videos:
        print("No videos found in playlist.", file=sys.stderr)
        return 1
    print(f"Found {len(videos)} videos.")

    written: list[str] = []
    skipped: list[str] = []
    with tempfile.TemporaryDirectory(prefix="playlist-transcripts-") as tmp:
        workdir = Path(tmp)
        for meta in videos:
            meta = fetch_metadata(meta)
            vtt_path = download_vtt(meta, workdir)
            if vtt_path is None:
                print(f"  no subtitles: {meta.title} ({meta.video_id})")
                skipped.append(meta.title)
                continue
            transcript = clean_vtt(vtt_path.read_text(encoding="utf-8"))
            note_name = sanitize_filename(meta.title)
            note_path = dest / f"{note_name}.md"
            note_path.write_text(
                build_note(meta, transcript, args.playlist_tag), encoding="utf-8"
            )
            written.append(note_name)
            words = len(transcript.split())
            print(f"  wrote: {note_path} ({words} words)")

    if written:
        index_path = dest / f"{index_title}.md"
        index_path.write_text(build_index(index_title, written), encoding="utf-8")
        print(f"Index: {index_path}")
    if skipped:
        print(f"Skipped (no subtitles): {', '.join(skipped)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
