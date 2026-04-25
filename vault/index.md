# Vault Index

## Kdenlive XML serialization

- [[kdenlive-25-document-shape]] — what a Kdenlive 25.x `.kdenlive` file must look like
- [[kdenlive-uuid-vs-control-uuid]] — the bin-loader trap (`kdenlive:uuid` on chains breaks loading)
- [[kdenlive-twin-chain-pattern]] — every avformat clip gets two `<chain>` elements, linked by `control_uuid`
- [[kdenlive-per-track-tractor-pattern]] — track wiring with A/B playlists + audio filters
- [[kdenlive-bin-loader-source-pointers]] — exact Kdenlive source files & lines for the load checks
- [[kdenlive-title-card-pattern]] — editable title cards (`mlt_service=kdenlivetitle` with `xmldata`)
- [[kdenlive-cross-dissolve-pattern]] — cross-dissolves are always stacked clips + a sequence transition
- [[kdenlive-image-and-qtblend-pattern]] — image producers + Ken Burns `qtblend` keyframe transforms
- [[kdenlive-clip-speed-pattern]] — clip speed via separate `timewarp` producer; timeline entry redirects, bin chain unchanged
- [[kdenlive-audio-fade-pattern]] — audio fade-in/out via `volume` filter inside the entry, with scalar `gain`/`end` (not keyframes)

## Process

- [[golden-fixture-testing]] — testing the serializer against a real Kdenlive save without launching Kdenlive
- [[external-kdenlive-examples-survey]] — survey of upstream KDE test suite + dev-docs, with a 10-item priority backlog of patterns we don't yet implement
