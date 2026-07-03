"""External render proofs for track-level audio: volume + ducking.

Non-self-referential: builds real ``.kdenlive`` files, renders them with melt,
and measures the rendered audio with ffmpeg ``astats``. These prove the
track-filter placement (a ``<filter>`` child of the track ``<playlist>``) is
actually applied by MLT, and that ``audio_duck`` dips a music track under
detected speech.

Both tests need melt + ffmpeg; skipped (via the conftest fixtures) when absent.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import AddTrackFilter, SetTrackMute
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence
from workshop_video_brain.edit_mcp.pipelines import timeline_audio as ta

from . import builders
from ._oracle import render_video

pytestmark = pytest.mark.external

FPS = 25.0
FRAMES = 75


def _window_rms_db(ffmpeg_bin: str, media, start: float, dur: float | None) -> float:
    """Overall RMS level (dB) of a time window of *media* via ffmpeg astats."""
    cmd = [ffmpeg_bin, "-hide_banner", "-ss", str(start)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", str(media), "-af", "astats=metadata=1:reset=0", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    val = None
    for line in proc.stderr.splitlines():
        if "RMS level dB:" in line:
            try:
                val = float(line.split("RMS level dB:", 1)[1].strip())
            except ValueError:
                pass
    return val if val is not None else float("-inf")


def _tone_music_project(title: str) -> KdenliveProject:
    """A single audio track carrying a constant MLT ``tone`` producer."""
    proj = builders.solid_color_project(color=builders.RED, frames=FRAMES, fps=FPS, title=title)
    proj.producers.append(
        Producer(id="tone_0", resource="",
                 properties={"mlt_service": "tone", "length": str(FRAMES + 10)})
    )
    audio_pl = next(p for p in proj.playlists if p.id == builders.AUDIO_TRACK)
    audio_pl.entries[0].producer_id = "tone_0"
    return proj


def test_track_volume_renders_quieter_than_control(melt_bin, ffmpeg_bin, render_dir: Path):
    """A -12 dB track volume filter must render measurably quieter than control."""
    # Control: constant tone, no track filter.
    control = _tone_music_project("ctl")
    ctl_path = render_dir / "ctl.kdenlive"
    serialize_project(control, ctl_path)
    ctl_media = render_video(ctl_path, render_dir / "ctl.mp4", frames=FRAMES, melt_bin=melt_bin)
    ctl_rms = _window_rms_db(ffmpeg_bin, ctl_media, 0.5, 1.5)

    # Filtered: -12 dB track volume on the audio track (playlist index 1).
    audio_index = control.playlists.index(
        next(p for p in control.playlists if p.id == builders.AUDIO_TRACK)
    )
    filtered = patcher.patch_project(
        _tone_music_project("vol"),
        [AddTrackFilter(track_index=audio_index, track_ref=builders.AUDIO_TRACK,
                        mlt_service="volume", filter_id="vol", properties={"level": "-12"})],
    )
    vol_path = render_dir / "vol.kdenlive"
    serialize_project(filtered, vol_path)
    vol_media = render_video(vol_path, render_dir / "vol.mp4", frames=FRAMES, melt_bin=melt_bin)
    vol_rms = _window_rms_db(ffmpeg_bin, vol_media, 0.5, 1.5)

    delta = vol_rms - ctl_rms
    # ~-12 dB; allow codec slop but demand an unmistakable, correctly-signed drop.
    assert delta < -8.0, (
        f"track volume not applied: control={ctl_rms:.1f} dB, "
        f"filtered={vol_rms:.1f} dB, delta={delta:.1f} dB"
    )


def test_audio_duck_dips_music_under_voice(melt_bin, ffmpeg_bin, render_dir: Path):
    """Two tracks (voice bursts + constant music): the music must render quieter
    during the voice bursts than between them."""
    # Voice fixture: tone bursts at 0.4-0.9 s and 1.8-2.3 s, silence elsewhere.
    voice_wav = render_dir / "voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "aevalsrc='0.5*sin(2*PI*300*t)*"
         "(between(t,0.4,0.9)+between(t,1.8,2.3))':d=3:s=48000",
         "-c:a", "pcm_s16le", str(voice_wav)],
        capture_output=True, check=True,
    )

    # Two audio tracks: track 0 = voice (real file), track 1 = constant music tone.
    proj = KdenliveProject(
        title="duck",
        profile=ProjectProfile(width=320, height=180, fps=FPS, colorspace="709"),
        producers=[
            Producer(id="voice_0", resource=str(voice_wav),
                     properties={"resource": str(voice_wav), "mlt_service": "avformat",
                                 "length": str(FRAMES + 10)}),
            Producer(id="music_0", resource="",
                     properties={"mlt_service": "tone", "length": str(FRAMES + 10)}),
        ],
        tracks=[
            Track(id="pl_voice", track_type="audio", name="Voice"),
            Track(id="pl_music", track_type="audio", name="Music"),
        ],
        playlists=[
            Playlist(id="pl_voice", entries=[PlaylistEntry(producer_id="voice_0", in_point=0, out_point=FRAMES - 1)]),
            Playlist(id="pl_music", entries=[PlaylistEntry(producer_id="music_0", in_point=0, out_point=FRAMES - 1)]),
        ],
        tractor={"id": "tractor0", "in": "0", "out": str(FRAMES - 1)},
    )

    # Detect voice activity on the source file and build the duck envelope.
    silence = detect_silence(voice_wav, threshold_db=-30.0, min_duration=0.3)
    speech = ta.invert_silence(silence, 0.0, 3.0)
    assert len(speech) >= 2, f"fixture VAD failed: {speech}"
    keyframes = ta.voice_activity_to_duck_keyframes(
        speech, total_frames=FRAMES, fps=FPS, duck_db=-15, attack_ms=150, release_ms=300
    )

    # Duck the music track, and mute the voice track so the render's audio is the
    # ducked music alone (the measurement isolates the music).
    proj = patcher.patch_project(
        proj,
        [
            AddTrackFilter(track_index=1, track_ref="pl_music", mlt_service="volume",
                           filter_id="duck1", properties={"level": keyframes}),
            SetTrackMute(track_ref="pl_voice", muted=True),
        ],
    )
    path = render_dir / "duck.kdenlive"
    serialize_project(proj, path)
    media = render_video(path, render_dir / "duck.mp4", frames=FRAMES, melt_bin=melt_bin)

    during1 = _window_rms_db(ffmpeg_bin, media, 0.5, 0.3)   # inside burst #1
    between = _window_rms_db(ffmpeg_bin, media, 1.1, 0.5)   # between bursts
    during2 = _window_rms_db(ffmpeg_bin, media, 1.9, 0.3)   # inside burst #2

    assert between - during1 > 6.0, (
        f"music not ducked under burst#1: during={during1:.1f} dB, between={between:.1f} dB"
    )
    assert between - during2 > 6.0, (
        f"music not ducked under burst#2: during={during2:.1f} dB, between={between:.1f} dB"
    )
