# Native Kdenlive import validation

Runtime XML validation checks producer references and bin registration before committing a generated project. This exposes two existing native import limitations that older tests missed by checking only well-formed XML and repeated serialization.

- `corpus_clip_ids_2604.kdenlive`: native chains with timecode attributes are retained as opaque XML, but their bin registrations are not reconstructed by the serializer. Referenced timeline chains have no registered bin clip.
- `corpus_nesting_effects_2604.kdenlive`: preserved native playlists reference nested sequence producers that the serializer does not recreate. References can point to absent sequence UUIDs.

Parsing these originals remains supported. Rewriting them now raises `ProjectSerializeError` before writing, and regression tests assert that an existing destination remains unchanged. Full editable import needs parsing native timecodes, preserving bin registration relationships, and modeling multiple nested sequences before these fixtures can satisfy the roundtrip contract.

The adversarial `bad_entry_int.kdenlive` fixture also remains parseable but is rejected on writing: its preserved malformed entry references an absent `p0` producer. The typed error identifies that reference.

An unrelated false positive was corrected: an unused preserved native chain using `avformat-novalidate` does not make the entire regenerated document a twin-chain document. Twin detection considers actual timeline usage or an explicit validating bin chain, preserving native speed-clip imports while enforcing the strict twin contract on generated twins.
