# MLT's service registry and Kdenlive's are different gates

`adapters/mlt/registry.py` answers "can MLT on this host load this service?". It does not answer "will Kdenlive keep it?". Both matter, so `effect_add` checks both before writing.

- **MLT registry.** Filled from the bindings worker, else `melt -query`. Cached in memory; a miss is remembered for 60 s, so a host without MLT does not respawn on every call. It fails open: with no registry at all, the check reports `unchecked`.
- **Kdenlive denylist.** `KDENLIVE_UNSUPPORTED` is the only static list: `avfilter.crop` to `crop`, `avfilter.curves` to `frei0r.curves`, `avfilter.boxblur` to `box_blur`, all from CLAUDE.md hard rule 11. MLT loads all three. `allow_unregistered=True` skips the host check but not this list.

**Open question (2026-11-02):** Kdenlive 26.08.2 ships `avfilter_boxblur.xml` and `avfilter_curves.xml`, and both ids are in `effect_ids.KNOWN_EFFECT_IDS`. So on 26.08 only `avfilter.crop` is really missing. The list follows the 25.x rule until the supported version is settled in prompt 06.

## Facts worth keeping

- `melt -query filters` hides 12 internal normalizers that the bindings list: `avcolor_space avcolour_space avdeinterlace color_transform deinterlace fieldorder gtkrescale resample rescale resize swresample swscale`. Never assert the two lists are equal; the bindings are a superset.
- `timeremap` is a **link**, not a filter. `qtblend` and `affine` are both a filter and a transition. So checks are per kind.
- The registry is host-specific. `opencv.tracker` is absent on CI.
- The serializer only warns, and only from a registry already in memory. It never triggers a load, because many tests write synthetic services and a write should not spawn processes.
