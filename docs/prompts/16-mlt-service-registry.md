# Prompt 16: in-memory MLT service registry; reject unregistered effects before write (Phase 3)

Hand this whole file to the implementing model.

---

Build one cached, in-memory registry of the MLT services this host can
actually load: filters, transitions, producers, consumers and links. It is
filled from the MLT worker of prompt 14, falling back to `melt -query`. Use it
for three things:

1. Replace the ad-hoc `melt -query filters` call in `app/doctor.py`.
2. Expose two read-only discovery tools.
3. **Reject an unregistered or Kdenlive-unsupported service at the tool
   boundary, before any project write**, with an actionable error: close
   matches plus known substitutes.

Read `docs/prompts/00-README.md` first. Prompt 14 must be merged. Read
`edit_mcp/adapters/mlt/engine.py` and `_worker.py` first.

## Verified facts (MLT 7.42, this machine)

In the worker:

```python
rep = mlt.Factory.init()                  # returns the Repository
def names(props): return sorted({props.get_name(i) for i in range(props.count())})
reg = {k: names(getattr(rep, k)()) for k in ("filters", "transitions", "producers", "consumers", "links")}
md = rep.metadata(mlt.mlt_service_filter_type, "avfilter.eq")   # Properties or None
yaml_text = md.serialise_yaml() if md else None                  # full metadata incl. parameters
# kind constants: filter=6, transition=7, producer=2, consumer=mlt.mlt_service_consumer_type, link=10
```

- Counts: 622 filters, 56 transitions, 44 producers, 11 consumers, 353 links.
  Loading takes 0.2 s.
- `melt -query filters` lists only 610. It hides 12 internal normalizers:
  `avcolor_space avcolour_space avdeinterlace color_transform deinterlace
  fieldorder gtkrescale resample rescale resize swresample swscale`.
  Never assert the two lists are equal.
- `melt -query <kind>` prints YAML to **stdout**: a `---` line, then
  `<kind>:`, then `  - name` lines. Parse it with
  `re.findall(r"^  - (\S+)$", stdout, re.M)`.
  - Kinds: `filters`, `transitions`, `producers`, `consumers`, `links`.
  - Per-service metadata: `melt -query filter=avfilter.eq` (YAML).
  - Each call takes about 0.2 s.
- **The MLT registry does NOT catch Kdenlive's rejections.** `avfilter.crop`,
  `avfilter.curves` and `avfilter.boxblur` are all present in MLT, yet
  Kdenlive flags them missing and drops them (CLAUDE.md hard rule 11). Keep a
  separate, small **Kdenlive denylist** with substitutes:
  - `avfilter.crop` -> `crop`;
  - `avfilter.curves` -> `frei0r.curves` (all 15 numbered props);
  - `avfilter.boxblur` -> `box_blur`.
  - Before adding the list, grep for one that prompt 03
    (`03-effects-kdenlive-identity.md`) may already have added:
    `grep -rn "avfilter.boxblur" workshop-video-brain/src`. Reuse it if it
    exists.
- `timeremap` is a **link**, not a filter. `qtblend` and `affine` are both a
  filter and a transition. Checks must be kind-aware.
- `opencv.tracker` is missing on CI (`melt_has_service` in
  `tests/integration/external/conftest.py` skips on it). The registry is
  host-specific, so tests must not hard-code availability of optional modules.

## Steps

### 1. Worker ops (`adapters/mlt/_worker.py`)

- `registry` returns `{"mlt_version", "filters": [...], "transitions": [...], "producers": [...], "consumers": [...], "links": [...]}`.
- `service_info` takes args `{"kind": "filter", "name": "..."}` and returns
  `{"yaml": <serialise_yaml text or null>}`.

### 2. `edit_mcp/adapters/mlt/registry.py`

```python
@dataclass(frozen=True)
class ServiceRegistry:
    engine: str                 # "bindings" | "melt"
    mlt_version: str
    services: dict[str, frozenset[str]]   # kind ("filters", ...) -> names
    def has(self, kind: str, name: str) -> bool: ...
```

- `get_registry(refresh=False) -> ServiceRegistry | None`.
  - Use the bindings worker (`run_worker("registry", {}, timeout=CAPABILITY_TIMEOUT_SECONDS)`).
  - Else the melt CLI (5 `melt -query <kind>` calls, each with
    `timeout=CAPABILITY_TIMEOUT_SECONDS`).
  - Else return `None`.
  - Cache in a module global behind a `threading.Lock`. A failed attempt is
    cached too (as `None`) for 60 s, so a host without MLT does not re-spawn
    on every call.
  - Do **not** add a disk cache.
- `service_info(kind, name) -> str | None`: YAML from the worker op, or
  `melt -query <singular-kind>=<name>` as the fallback.
- `KDENLIVE_UNSUPPORTED: dict[str, str]`: the denylist, mapping service to
  substitute.
- `UnregisteredServiceError(ValueError)` carries `kind`, `name`,
  `suggestions: list[str]` and `substitute: str | None`.
- `check_service(kind, name, *, registry=None) -> str` returns `"ok"` or
  `"unchecked"` (no registry available), or raises `UnregisteredServiceError`.
  Rules, in this order:
  1. The name is in `KDENLIVE_UNSUPPORTED`: raise with `substitute` set, even
     when MLT has it.
  2. No registry: return `"unchecked"`. Fail **open**: CI's `unit` job has no
     melt and no bindings.
  3. `registry.has(kind, name)`: return `"ok"`.
  4. Otherwise raise with
     `suggestions = difflib.get_close_matches(name, registry.services[kind], n=3, cutoff=0.6)`.
- A module-level test seam, `_override: ServiceRegistry | None`, plus a
  `use_registry(reg)` context manager for tests.

### 3. Reject at the tool boundary, before any write

- **`effect_add`** (`edit_mcp/server/tools/effects_catalog.py`, around
  line 39).
  - Add the parameter `allow_unregistered: bool = False`. Some users build
    projects on one machine and render on another that has extra plugins.
  - Right after the `effect_name` emptiness check (around line 68), and
    **before** `parse_project` and `create_snapshot`, call
    `check_service("filters", effect_name)`.
  - Catch `UnregisteredServiceError` and return
    `invalid_input(message, suggestion, param="effect_name", given=effect_name, suggestions=[...], substitute=...)`.
    Suggestion voice examples:
    - "Kdenlive drops 'avfilter.crop' on load; use 'crop' instead."
    - "'avfilter.gblurr' is not an MLT filter on this host. Did you mean: avfilter.gblur? Run mlt_services to search, or pass allow_unregistered=true if the render machine has this plugin."
  - When `allow_unregistered` is true, skip the MLT check but **not** the
    Kdenlive denylist.
  - Add `"service_check": "ok" | "unchecked" | "skipped"` to the `_ok`
    payload.
- **`effect_stack_apply`** (same file, around line 513).
  - Presets carry `mlt_service` values. Check each one before snapshotting.
  - Reject the whole apply on the first failure, naming the preset entry.
  - `pipelines/stack_presets.py` (around line 324) already checks each
    preset service against the **Kdenlive** effect catalog
    (`effect_catalog.find_by_service`). Add the MLT-host check next to it.
    Do not replace the catalog check.
- Leave `pipelines/effect_apply.apply_effect` permissive.
  `tests/unit/test_effect_apply.py` (around line 126) deliberately asserts
  that a custom name passes at the pipeline level. Do not change that test.
- **Serializer: warning only.** In `serialize_project`, before the write,
  collect every `mlt_service` of `<filter>`/`<transition>` elements in the
  final tree.
  - When a cached registry is already loaded, `logger.warning` the unknown
    ones.
  - Never trigger a registry load from the serializer, and never raise. Many
    existing tests write synthetic services.

### 4. Discovery tools (`edit_mcp/server/bundles/mlt_services.py`)

```
mlt_services(kind: str = "filters", query: str = "", limit: int = 200) -> dict
mlt_service_info(kind: str, name: str) -> dict
```

- These do not take `workspace_path`: they operate on the host, which the
  CLAUDE.md naming rule allows.
- `kind` must be one of the five plural kinds. Validate it with
  `invalid_input`.
- `query` is a case-insensitive substring filter.
- The payload includes `engine`, `mlt_version`, `count`, `names`, and a
  `kdenlive_unsupported` flag per returned name.
- `mlt_service_info` returns the YAML text, plus the Kdenlive substitute when
  the service is denylisted. An unknown name returns
  `not_found("MLT service", name, hint=<close matches>)`.
- No registry at all returns `missing_binary("melt", ...)`.

### 5. Doctor (`app/doctor.py`, line 28)

- Replace `effects = _probe('melt', ['-query', 'filters'])` with the
  registry.
- Keep the report key `'mlt_effects'`. Give it the value
  `{'available': bool, 'engine', 'mlt_version', 'counts': {kind: n}}`.
- Keep `doctor` bounded. `get_registry(refresh=True)` uses the
  capability timeouts.
- `test_doctor_absent_binaries_models_and_engines` patches `shutil.which` to
  None and forbids `subprocess.run`. With prompt 14's `find_mlt_python` patch
  in that test, the registry must return None without spawning anything, and
  `mlt_effects.available` must be False. Make sure the melt fallback checks
  `shutil.which("melt")` before spawning.

### 6. Tests (all required)

- `tests/unit/test_mlt_registry.py` (no MLT needed). Inject a fake
  `ServiceRegistry` via `use_registry`. Cover:
  - ok;
  - unknown with suggestions (`avfilter.gblurr` -> `avfilter.gblur`);
  - kind-awareness (`timeremap` ok as a link, rejected as a filter);
  - the denylist rejects `avfilter.crop` even when the fake registry
    contains it;
  - no registry returns `"unchecked"`;
  - parse canned `melt -query` stdout, including the `---` header.
- `tests/unit/test_effect_add_service_check.py`, using `call_tool` on
  `effect_add` with a hermetic project (see `tests/integration/test_stack_ops_mcp_tools.py`
  for the workspace fixture pattern) and a fake registry:
  - an unknown name returns `invalid_input` and the project file is
    byte-identical with **no new snapshot directory**;
  - `allow_unregistered=True` succeeds;
  - `avfilter.boxblur` is rejected with `substitute == "box_blur"`.
- `tests/integration/test_mlt_registry_live.py`:
  - With `requires_mlt_bindings`: `engine == "bindings"`;
    `filters` contains `avfilter.eq`, `frei0r.curves` and `box_blur`;
    `links` contains `timeremap`.
  - With `requires_melt`: same, via the melt engine (patch
    `find_mlt_python` to None). Bindings filters must be a superset of the
    melt filters when both are available.
- Existing integration tests call `effect_add` with `brightness`,
  `avfilter.eq`, `volume`, `charcoal`, `avfilter.gblur`, `avfilter.negate`,
  `frei0r.IIRblur` and `lift_gamma_gain`. All are real MLT filters, and they
  must still pass on this host and on CI (melt 7.22 with `frei0r-plugins`).
  If one fails because the service is genuinely missing on CI, do not weaken
  the check; report it.

## Acceptance criteria

- `effect_add(effect_name="avfilter.gblurr")` returns an error suggesting
  `avfilter.gblur`, and writes nothing.
- `mlt_services(kind="links", query="time")` lists `timeremap`.
- `wvb doctor --json` shows `mlt_effects.engine == "bindings"` on this
  machine, and no `melt -query` process is spawned when bindings work.
- The full suite is green.

## Do NOT

- Do not hard-fail when no registry exists. Fail open and report
  `"unchecked"`.
- Do not change `tests/integration/external/conftest.py::melt_has_service`.
  The oracle tier stays independent of product code.
- Do not hard-code the list of MLT services in source. The denylist is the
  only static list.
- Do not make the serializer spawn processes.
- Do not reject inside `pipelines/effect_apply` or the patcher intents.

## When done

1. `docs/plans/2026-10-13-media-mcp-expansion.md`, Phase 3 item (4): mark it
   done.
2. Add a vault note, `vault/wiki/mlt-service-registry-vs-kdenlive-registry.md`.
   It must cover:
   - that the MLT registry contains `avfilter.crop`/`curves`/`boxblur` while
     Kdenlive drops them (two different gates);
   - the 12 hidden normalizers;
   - that `timeremap` is a link.
   Link it from `kdenlive-not-all-avfilter-shapes-registered.md`.
3. Mention `mlt_services` / `mlt_service_info` and the `effect_add` rejection
   in `docs/video-editing-guide/12-effects-titles-graphics.md`.
4. Regenerate `docs/capabilities.md` (command in prompt 14 "When done").
5. Report per 00-README. Include the registry counts per kind for each
   engine on this host.
