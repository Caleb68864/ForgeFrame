---
type: factory-manifest
spec: ../2026-04-13-composite-blend-modes.md
run_id: ff-2026-04-13-composite-blend-modes
date: 2026-04-13
---

# Factory Manifest -- Composite Blend Modes

| Stage | Name | Status | Timestamp |
|-------|------|--------|-----------|
| 1 | Init | complete | 2026-04-13 |
| 2 | Spec | complete | 2026-04-13 |
| 3 | Prep | complete | 2026-04-13 |
| 4 | Run | pending | -- |
| 5 | Verify | pending | -- |

## Decisions

- Stage 3 (Prep): Produced 2 phase specs in phase-specs/. Identified critical multi-service mapping: blend modes do not live on a single `composite` MLT service -- they are split across `frei0r.cairoblend` (string-enum) and `qtblend` (integer-enum). Sub-Spec 1 must choose a service per mode and build a two-layer map (abstract name -> service + property name + MLT value).
