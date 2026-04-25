# Chronicler Log

Append-only operation log.

- 2026-04-25 — Added Kdenlive 25.x serialization knowledge pages: shape, uuid trap, twin chain, per-track tractor, source pointers, golden-fixture testing. First v25-compatible MCP output opened cleanly in Kdenlive 25.08.3.
- 2026-04-25 — Multi-track + editable title smoke (`smoke_2`) opens in Kdenlive. Six contract fixes: main sequence needs `kdenlive:control_uuid`, no `hide` on the sequence's black-track ref, every timeline `<entry>` carries `<property name="kdenlive:id">`, `kdenlive:kextractor=1` on both timeline and bin twins, bin twin uses `mlt_service=avformat` (timeline keeps `-novalidate`), user clip `kdenlive:id` starts at 4 (2 = Sequences folder, 3 = sequence). Title cards must be `mlt_service=kdenlivetitle` with `xmldata` payload, `clip_type=2`, and a host-installed font. Added [[kdenlive-title-card-pattern]] page.
