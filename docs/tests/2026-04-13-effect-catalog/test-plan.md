---
title: "Effect Catalog + Generator Test Plan"
project: "ForgeFrame"
date: 2026-04-13
type: test-plan
tags:
  - test-plan
  - forgeframe
  - effect-catalog
---

# Test Plan: Effect Catalog + Generator for Kdenlive MCP

## Meta
- Project: ForgeFrame (Workshop Video Brain)
- Date: 2026-04-13
- Author: Forge
- Spec Source: docs/specs/2026-04-13-effect-catalog.md
- Scope: All three sub-specs (Parser, Generator, MCP/CLI)

## Prerequisites
- Python 3.12+ with `uv` available.
- Repo at `/home/caleb/Projects/ForgeFrame`.
- For real-Kdenlive scenarios: Kdenlive installed at `/usr/share/kdenlive/effects/` (~376 XML files).
- Hand-crafted XML fixtures present at `tests/unit/fixtures/effect_xml/` (acompressor.xml, transform.xml, list-param.xml, unknown-type.xml, localized-name.xml, missing-paramlistdisplay.xml).
- Tests are self-contained; generator scenarios write to `/tmp/`.
- Test framework: pytest. Tool hint: `bash`.

## Scenarios

### Sub-Spec 1 -- Parser & Data Model

| ID     | Title                                                            | Area    | Priority | Sequential |
|--------|------------------------------------------------------------------|---------|----------|------------|
| SS1-01 | Parser module exports data model symbols                         | Parser  | High     | No         |
| SS1-02 | ParamType enum covers all 16 known Kdenlive types                | Parser  | High     | No         |
| SS1-03 | EffectDef has documented field set                               | Parser  | High     | No         |
| SS1-04 | ParamDef has documented field set                                | Parser  | High     | No         |
| SS1-05 | parse_effect_xml on acompressor fixture returns full EffectDef   | Parser  | High     | No         |
| SS1-06 | parse_param on type=list extracts paramlist + paramlistdisplay   | Parser  | High     | No         |
| SS1-07 | parse_param on type=animated forces keyframable=True             | Parser  | High     | No         |
| SS1-08 | parse_param honours explicit keyframes="1" attr                  | Parser  | High     | No         |
| SS1-09 | parse_param defaults keyframable=False for static types          | Parser  | High     | No         |
| SS1-10 | Unknown param type raises ValueError naming type + filename      | Parser  | High     | No         |
| SS1-11 | kdenlive_id derived from filename stem                           | Parser  | High     | No         |
| SS1-12 | Localized <name lang="..."> variants prefer no-lang              | Parser  | Medium   | No         |
| SS1-13 | type=list missing paramlistdisplay falls back to raw values      | Parser  | Medium   | No         |
| SS1-14 | Empty <description> yields empty string not None                 | Parser  | Medium   | No         |
| SS1-15 | parser pytest run passes                                         | Parser  | High     | No         |

### Sub-Spec 2 -- Generator, Emitter, Upstream Check

| ID     | Title                                                            | Area      | Priority | Sequential |
|--------|------------------------------------------------------------------|-----------|----------|------------|
| SS2-01 | build_catalog signature exported                                 | Generator | High     | No         |
| SS2-02 | emit_python_module signature exported                            | Generator | High     | No         |
| SS2-03 | fetch_upstream_effects signature exported                        | Generator | High     | No         |
| SS2-04 | DiffReport dataclass has documented fields                       | Generator | High     | No         |
| SS2-05 | Generated module exports CATALOG + finders + metadata            | Generator | High     | No         |
| SS2-06 | build_catalog on fixture dir w/ check_upstream=False             | Generator | High     | No         |
| SS2-07 | emit_python_module produces importable round-trip module         | Generator | High     | Yes        |
| SS2-08 | Generated module top docstring includes regen instructions       | Generator | Medium   | No         |
| SS2-09 | fetch_upstream_effects returns None on network failure           | Generator | High     | No         |
| SS2-10 | Duplicate kdenlive_id warns + last-wins                          | Generator | High     | No         |
| SS2-11 | scripts/generate_effect_catalog.py runs against fixtures         | Generator | High     | Yes        |
| SS2-12 | Real Kdenlive run produces > 300 entries matching dir count      | Generator | High     | Yes        |
| SS2-13 | Generated CATALOG importable + count > 300                       | Generator | High     | Yes        |
| SS2-14 | generator pytest run passes                                      | Generator | High     | No         |

### Sub-Spec 3 -- MCP Tools, CLI, Integration

| ID     | Title                                                            | Area    | Priority | Sequential |
|--------|------------------------------------------------------------------|---------|----------|------------|
| SS3-01 | effect_info MCP tool registered                                  | MCP     | High     | No         |
| SS3-02 | effect_info return shape matches contract                        | MCP     | High     | No         |
| SS3-03 | effect_list_common signature unchanged                           | MCP     | High     | No         |
| SS3-04 | CLI `catalog regenerate` subcommand exists with flags            | CLI     | High     | No         |
| SS3-05 | All catalog tools importable as callables (INTEGRATION)          | MCP     | High     | No         |
| SS3-06 | effect_info("acompressor") returns full schema                   | MCP     | High     | No         |
| SS3-07 | effect_info by mlt_service returns same entry                    | MCP     | High     | No         |
| SS3-08 | effect_info on missing name returns structured error             | MCP     | High     | No         |
| SS3-09 | effect_info on empty string returns structured error             | MCP     | Medium   | No         |
| SS3-10 | effect_list_common returns >300 catalog-backed entries           | MCP     | High     | No         |
| SS3-11 | Short description truncates at ~80 chars with ellipsis           | MCP     | Medium   | No         |
| SS3-12 | CLI `catalog regenerate` writes file when invoked                | CLI     | High     | Yes        |
| SS3-13 | MCP+CLI pytest module passes                                     | MCP/CLI | High     | No         |
| SS3-14 | Full suite passes (no regressions)                               | All     | High     | Yes        |

## Coverage Summary
- Total scenarios: 43 (15 parser + 14 generator + 14 MCP/CLI)
- [STRUCTURAL] criteria: 11 covered
- [BEHAVIORAL] criteria: 23 covered (incl. edge-case probes)
- [MECHANICAL] criteria: 7 covered
- [INTEGRATION] criteria: 1 covered
- Sequential scenarios: 5 (mutate `/tmp` files or import freshly generated module)

## Dependencies
- Sub-Spec 2 scenarios depend on Sub-Spec 1 implementation.
- Sub-Spec 3 scenarios depend on a generated `effect_catalog.py` module being importable.
- SS2-12, SS2-13, SS3-10 require Kdenlive installed locally.

## Holdout Scenarios
None -- all scenarios visible during development.

## Execution
Run individually via pytest paths cited in each scenario, or run the full suite:
```
uv run pytest tests/ -v
```
