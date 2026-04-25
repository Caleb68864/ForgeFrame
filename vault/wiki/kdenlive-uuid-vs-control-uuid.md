# `kdenlive:uuid` vs `kdenlive:control_uuid` — the bin loader trap

Putting `<property name="kdenlive:uuid">` on a media `<chain>` makes Kdenlive's bin loader silently refuse to register that clip, and the project then opens with **"Project corrupted. Clip <id> ({<uuid>}) not found in project bin."**

This bug cost ~3 iteration rounds before we read the Kdenlive source.

## The contract

| Property | Belongs on | Belongs **NOT** on |
|---|---|---|
| `kdenlive:uuid` | The main sequence tractor (the one with id `{<uuid>}`) | Producers, chains, playlists, other tractors |
| `kdenlive:control_uuid` | Every media chain (timeline + bin twin) | Sequence/project tractors |

Both are `{8-4-4-4-12}`-format UUIDs in braces. They serve different purposes:

- `kdenlive:uuid` flags the element as a *sequence* — Kdenlive's bin loader looks at this property's *existence* (not its value) to decide which loading branch to take.
- `kdenlive:control_uuid` is the bin lookup key — both chains in a [[kdenlive-twin-chain-pattern|twin pair]] share it so Kdenlive knows they're the same source.

## Why it fails

`projectitemmodel.cpp::loadBinPlaylist` iterates `<entry>` children of `main_bin`:

```cpp
if (prod->parent().property_exists("kdenlive:uuid")) {
    // sequence-handling branch -- only registers tractor sequences,
    // does `continue` for non-tractor producers, never populates binIdCorresp.
} else {
    // media branch -- registers via binIdCorresp[control_uuid] = newId
}
```

Then `meltBuilder.cpp::constructTrackFromMelt` resolves every timeline `<entry>` by looking up `chain.get("kdenlive:control_uuid")` in `binIdCorresp`. A media chain with `kdenlive:uuid` set takes the wrong branch, never gets registered, and the lookup misses → fatal "not found in project bin" error.

## The fix in this repo

`adapters/kdenlive/serializer.py::serialize_project` — `_emit_media_element` does **not** call `_set_prop(elem, "kdenlive:uuid", ...)`. Only the main sequence tractor block sets it.

Test that locks in the contract: `tests/unit/test_serializer_bin.py::TestProducerMetadata::test_control_uuid_present` — explicitly asserts `"kdenlive:uuid" not in props` for every media element.

## Sources

- Kdenlive [`projectitemmodel.cpp`](https://invent.kde.org/multimedia/kdenlive/-/blob/master/src/bin/projectitemmodel.cpp) — `loadBinPlaylist`, around the property_exists check (line ~1473)
- Kdenlive [`meltBuilder.cpp`](https://invent.kde.org/multimedia/kdenlive/-/blob/master/src/timeline2/model/builders/meltBuilder.cpp) — error emission at ~line 1030, lookup at ~line 1050

## Related

- [[kdenlive-25-document-shape]]
- [[kdenlive-twin-chain-pattern]]
- [[kdenlive-bin-loader-source-pointers]]
