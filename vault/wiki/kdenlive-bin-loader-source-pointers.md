# Kdenlive bin loader — source pointers

Direct pointers into the KDE/kdenlive C++ source for the two functions that decide whether a generated `.kdenlive` will open. Reading these is faster than guessing when Kdenlive emits an opaque error.

## `projectitemmodel.cpp::loadBinPlaylist`

**Path**: `src/bin/projectitemmodel.cpp`
**URL**: https://invent.kde.org/multimedia/kdenlive/-/blob/master/src/bin/projectitemmodel.cpp

This function iterates `<entry>` children of the `<playlist id="main_bin">` and decides what each entry is. The discriminator that traps you is around line **1473**:

```cpp
if (prod->parent().property_exists("kdenlive:uuid")) {
    // SEQUENCE BRANCH
    // Only registers tractor sequences. For non-tractor producers
    // (chains, simple producers) it `continue`s without populating
    // the bin-id map. Result: any media chain that has kdenlive:uuid
    // is silently dropped from the bin.
} else {
    // MEDIA BRANCH (~line 1556)
    // newId = QString::number(getFreeClipId());
    // uuid  = prod->get("kdenlive:control_uuid");
    // requestAddBinClip(newId, ...);
    // binIdCorresp[uuid] = newId;       // <-- the lookup map
}
```

**Implication**: Never put `kdenlive:uuid` on a media `<chain>`. See [[kdenlive-uuid-vs-control-uuid]].

## `meltBuilder.cpp::constructTrackFromMelt`

**Path**: `src/timeline2/model/builders/meltBuilder.cpp`
**URL**: https://invent.kde.org/multimedia/kdenlive/-/blob/master/src/timeline2/model/builders/meltBuilder.cpp

This function walks each per-track tractor's playlist entries and resolves each `<entry>` to a bin clip via the map populated by `loadBinPlaylist`. The lookup is around line **1050**:

```cpp
QString clipId = clip->parent().get("kdenlive:control_uuid");
if (binIdCorresp.count(clipId) == 0) {
    m_errorMessage << i18n("Project corrupted. Clip %1 (%2) not found in project bin.",
                           clip->parent().get("id"), clipId);
    // ...timeline clip is dropped...
}
```

**Implication**: The error message is precise — it tells you the chain element id and the control_uuid Kdenlive failed to look up. Match that against your file to find the broken end of the link.

## Linked issue

- [Kdenlive issue #735](https://invent.kde.org/multimedia/kdenlive/-/issues/735) — "Project corrupted. Clip ... not found in project bin"

## Workflow when you hit a Kdenlive load error

1. Copy the exact message text from the Kdenlive dialog.
2. Search the kdenlive source on GitLab for the literal English text (it lives inside an `i18n("...")` call).
3. Read the surrounding 50 lines to find the condition that emits the message.
4. Trace the condition's inputs back to the XML property/element they came from.
5. Compare against the saved-by-Kdenlive reference fixture at `tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive`.

This loop solved the bin-not-found bug in one round after three rounds of guessing. **Reading source > pattern matching.**

## Related

- [[kdenlive-uuid-vs-control-uuid]]
- [[kdenlive-twin-chain-pattern]]
- [[kdenlive-25-document-shape]]
