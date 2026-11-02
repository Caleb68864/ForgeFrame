# Sizing a melt render

Do not size a melt render with `width=` and `height=` consumer properties. Found 2026-11-02 with melt 7.42.

Those properties make melt render through its default profile instead of the project's:

- **Black pillars.** A 16:9 project at 1280x720 came out with bars at both sides.
- **Shifted colours.** The output is tagged `smpte170m`, and pure red decoded as `0xe1` rather than `0xf4`. Against the correct picture it measures 22 dB.
- **A hang.** With a project that is not 25 fps, melt spins forever on the first frame and writes 48 bytes. Adding `frame_rate_num=25` does not help. `frame_rate_num=` alone does not convert the rate either: 121 frames of a 29.97 project play at 25, which stretches 4.04 s to 4.84 s.

Use a profile file:

```
melt -profile /tmp/render.mltprofile project.kdenlive -consumer avformat:out.mp4 vcodec=libx264 ...
```

`execute_render` writes that file from the render profile's size and the **project's** frame rate, and removes it afterwards. So a render keeps its project's rate, whatever the render profile's `frame_rate` says. `_build_melt_command` still returns the old form; `_with_melt_profile` rewrites it just before running.
