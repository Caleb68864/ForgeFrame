# Kdenlive canonical profile names

Hard rule 4: when MLT has a profile for a format, use its name. An anonymous name such as `1920x1080_fps25` makes Kdenlive warn about a "non standard framerate".

- **Source of the table:** `/usr/share/mlt-7/profiles` (MLT 7.42), hardcoded in `adapters/kdenlive/profiles.py`. It is not read at run time, because that directory differs on Windows and CI.
- **What gets written:** `kdenlive:docproperties.profile` holds the name, and `<profile description="...">` holds MLT's description verbatim, such as `HD 1080p 29.97 fps`.
- **Evidence:** `clip_speed_400_native.kdenlive` has `atsc_1080p_2997` and that description; `audio_mix_upstream_kde.kdenlive` has `atsc_1080p_25`.
- **Covered:** `atsc_720p_*`, `atsc_1080p_*`, `qhd_1440p_*`, `uhd_2160p_*` and `vertical_hd_{30,60}`. Any other format keeps the anonymous `WxH_fpsN` form.

Timeline builders take the profile from their first usable source through `pipelines/project_profile.profile_from_media`, and fall back to 1080p25 only when no source can be probed.
