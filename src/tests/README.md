# ForecastBench test suite

A fast, **GCP-independent** test suite for the refactored ForecastBench code. It runs entirely
offline (`make test`, ~1 minute), and is organized by *test level* so a failure tells you both
what broke and at what scope.

## Mental frame

> **Run the real production code, offline, at the smallest scope that proves the behavior.**

- Most behavior is pinned at the **pure domain layer** (data in → data out, no IO).
- A thin set of tests proves the **IO wiring** (the real storage code against a temp dir).
- One tier proves the **whole offline flow**, end to end.
- Nothing in the default run touches GCP, the network, or secrets — that is *enforced*, not hoped
  for. External APIs are checked separately, out of band.

**Level is the directory; technique is how you assert inside it.** "schema", "invariant",
"metamorphic", "cross-source" are *techniques* applied within a level, not their own folders.

## Layout

```
tests/
  unit/              many · pure, in-memory, one concern, no IO        ← the bulk
    sources/           per-source parse/update/resolution logic (HTTP mocked ad-hoc per source)
    resolve/           resolve_all, impute, prepare, explode
    leaderboard/       scoring, masks, df_info, bootstrap, ordering invariants, artifact serializers,
                       2FE + bootstrap on a real-data-shaped fixture (test_two_way_fixed_effects.py)
    curate_questions/  allocation/bin math, validity+freeze filters, seeded human sampling
    metadata/          tag + validate parsing (LLM boundary mocked)
    test_base_source.py, test_market_source.py, test_dataset_source.py,
    test_types_and_schemas.py, test_dates.py, test_invariants.py
  contract/          system-wide guarantees, registry-parametrized
    test_resolve_contract.py    resolve() fail-fast + nullification + value/date invariants (cross-source)
    test_update_conformance.py  update() output schema + exact columns per source
    test_registry_coverage.py   every source is implemented-case or named-stub
    test_offline_imports.py     the covered job modules (sources, resolve, leaderboard) import offline
  integration/       two adjacent components across one real boundary (local bucket)
    test_source_drivers.py      func_*/main.py:driver() wiring, parametrized over sources
    test_resolve_driver.py      func_resolve driver() raw → processed forecast-set round-trip
    test_leaderboard_compile.py download_and_compile read → filter → compile seam
    test_orchestration_io.py    _source_io ↔ local bucket (incl. empty-file edge cases)
    test_metadata_drivers.py    tag/validate driver() → question_metadata.jsonl (LLM mocked)
  e2e/               one offline product flow, end to end, parameterized by scenario
    test_resolution_pipeline.py bucket update → resolve → impute → leaderboard scoring/ordering,
                                anchored by semantic asserts + golden snapshots of the outputs
    test_question_set_pipeline.py  bank → tag/validate → metadata → drop_invalid → curate driver → golden
  live/              opt-in, real APIs, schema-asserted (NEVER in PR CI)
    test_api_conformance.py     consumed-field contracts for external APIs
  golden/            committed snapshot CSVs the e2e regression-checks against (re-bless on change)
  factories.py       builders (make_*_df, API-response builders)
  conftest.py        fixtures (freeze_today, source instances, local_bucket, autouse guards,
                     fresh_source, offline_update_case)
  _sources.py        IMPLEMENTED_SOURCES / STUB_SOURCES classification
  _golden.py         check_golden() snapshot helper (UPDATE_GOLDEN=1 to re-bless)
  _harness/          framework code (no-network guard, local bucket mount)
```

```
        ▲  few    e2e/          one whole offline flow, incl. buckets → leaderboard
       ╱ ╲        integration/  IO boundary / driver wiring
      ╱   ╲       contract/     registry-wide guarantees (schema, fail-fast, coverage)
     ╱     ╲      unit/         pure domain logic + invariants  ◀── primary
    ╱_______╲     (foundation: the offline-import contract underpins everything)
       many                     live/ sits outside the pyramid (opt-in, real network)
```

## Foundation: the offline-import contract

The job modules under contract — every source fetch/update job, `func_resolve`, and
`leaderboard.main` (plus the lazy `helpers.{keys,env,model_eval}`) — import with **no GCP, no
network, no Secret Manager, no import-time env**. (Other jobs — curate/metadata/base_eval/nightly —
aren't in the contract yet; see "Expanding to other jobs".)
This required small Layer-0 source changes (lazy secrets in `helpers/keys.py`, lazy LLM clients in
`helpers/model_eval.py`, call-time env in `helpers/env.py`, call-time mount in
`utils/gcp/storage.py`, deferred CSV in `leaderboard/main.py`). The contract is **executable**:
`contract/test_offline_imports.py` evicts each module and re-imports it under the guards, and also
imports the heavy chains in a cold subprocess with bogus creds.

Two autouse fixtures (in `conftest.py` / `_harness/network.py`) make every test offline-safe:

- `_guard_network` — replaces `socket.socket`; a non-loopback connect raises `BlockedNetworkError`,
  so an accidentally-unmocked HTTP call fails loudly instead of reaching a live API.
- `_fake_secrets` — patches `keys.get_secret` to a deterministic dummy.

Both are lifted for `@pytest.mark.live` tests, which are **excluded by default**
(`addopts = -m 'not live'`).

## The local harness (`_harness/`)

- **`LocalBucket`** + the **`local_bucket`** fixture point `BUCKET_MOUNT_POINT` and the `*_BUCKET`
  env vars at a temp dir, so `utils.gcp.storage` reads/writes locally. Helpers (`seed_questions`,
  `seed_fetch`, `seed_resolution_file`, `read_*`, `list_resolution_ids`) use the real filename
  conventions, so tests exercise the actual IO code path with no GCP.
- **`network`** installs/uninstalls the socket-level no-network guard.

Source HTTP is mocked **ad-hoc per source** in `unit/sources/` (e.g.
`@patch("sources.X.requests.get")` with hand-built responses). There is intentionally no shared
recorded-fixture replay layer: the parse paths are covered by those unit tests, and *drift* against
the real APIs is caught by the opt-in `live/` suite.

## Registry-aware contracts

The source contracts (`contract/test_resolve_contract.py`, `contract/test_update_conformance.py`)
are parametrized over `sources.registry` so a new source is covered automatically — but
**registry-aware, not registry-blind**:

- `update()` reaches the network in four of five sources (resolution is built via the network), so
  `offline_update_case` (in `conftest.py`) patches the common `_build_resolution_df` seam, plus
  `_get_market` (manifold/metaculus) and `ticker_renames` (yfinance). The conformance test then
  asserts update()'s *assembly* contract: the question frame validates against `QuestionFrame`
  with **exactly** `QUESTION_FILE_COLUMNS` (schemas are `strict=False`, so the explicit column
  check catches leaks the schema won't).
- `resolve()` is uniform and pure, so the behavioral contracts (fail-fast on missing id /
  empty / unknown source; nullified-drop; value ∈ [0,1]; no pre-due resolution date) run there.
- `test_registry_coverage.py` forces every source into `IMPLEMENTED_SOURCES` or `STUB_SOURCES`
  (`_sources.py`) — a new source fails until it is classified.

## Integration: parametrized driver wiring

`integration/test_source_drivers.py` proves each `func_*/main.py:driver()` *wires* read → call →
write against a `local_bucket`. The wiring is uniform across sources, so the contract is
**parametrized over `IMPLEMENTED_SOURCES`** — a new source is covered the moment it joins the
registry, no new file. `fetch()`/`update()` are **mocked** here on purpose: this layer is wiring
only; parse/update *logic* lives in `unit/sources/` and `contract/test_update_conformance.py`.

When a source diverges, add a **narrower test in the same file** (don't fork the parametrization):

- **Different call shape → scope to a subset.** `manifold`/`metaculus` fetch drivers call
  `fetch()` statelessly (no question bank), so the "passes the existing bank as `fetch(dfq=...)`"
  assertion runs only over `BANK_READING_FETCH = [infer, polymarket, yfinance]`.
- **A source can do more for real → its own test.** Only `polymarket.update()` is network-free, so
  `TestPolymarketUpdateRealChain` runs it **unmocked** to prove the whole chain end to end. (It
  still appears in the mocked parametrized test too — the two assert different things.)

Rule of thumb: parametrize while the seam is uniform; the moment a source needs bespoke
setup/asserts, give it a dedicated test beside the parametrized one rather than branching inside.

## Regression goldens (e2e)

The e2e keeps a few **intent-revealing asserts** (open market excluded, `Good` ranks above `Bad`,
`n_overall == 3`) *and* freezes its terminal frames as **golden snapshots** via `check_golden`
(`_golden.py`): the resolved frame and the scored leaderboard, one CSV per scenario in `golden/`.
The asserts pin *what's correct*; the golden is the catch-all net for *everything else that moved*.
They are complementary — a wrong re-bless that flips behaviour is still caught by a failing anchor.

- **Check** runs inside `make test` — offline, deterministic, CI-gating. Just another assertion.
- **Re-bless** is a deliberate dev step, never CI:

  ```bash
  UPDATE_GOLDEN=1 make test ARGS="src/tests/e2e"   # rewrite the e2e goldens
  ```

  The regenerated CSV is the **review artifact**: a readable diff of which rows changed. CSV (not
  Parquet) is chosen for exactly this reason; `.gitignore` un-ignores `src/tests/golden/**/*.csv`.

Goldens require determinism (`freeze_today`, seeded RNG, a stable sort key) — without it they flap.
Freeze only scalar columns that round-trip through CSV (tuple columns like `direction` are dropped
via `cols=`). This is the spiritual successor to the deleted old-vs-new comparator — a real
consumer this time, comparing committed-output vs current-code rather than two live deployments.

## Live conformance

`live/` asserts that the **fields our code consumes** are still present in real API responses
(permissive — not byte equality, since live data changes). It is opt-in and never blocks PR CI:

```bash
make test ARGS="-m live"
```

A failure means an external API dropped or renamed a field we depend on. Run it on a schedule or
before a release.

## Running

```bash
make test                                   # whole suite, offline
make test ARGS="-k polymarket"              # keyword filter
make test ARGS="src/tests/unit/leaderboard" # one directory
make test ARGS="-m live"                    # opt into live (network) tests
UPDATE_GOLDEN=1 make test ARGS="src/tests/e2e"  # re-bless e2e goldens (dev only, never CI)
```

`make lint` (black/isort/flake8/pydocstyle) must pass before committing.

## Adding tests

| You want to test… | Put it in |
| --- | --- |
| A source's parse/update/resolution edge case on synthetic data | `unit/sources/test_<source>.py` (`make_*` factories; mock `requests` ad-hoc) |
| Leaderboard scoring / ordering / artifact serialization | `unit/leaderboard/` |
| A `metadata`/`curate_questions` logic edge case | `unit/metadata/` or `unit/curate_questions/` (mock `model_eval.get_response_from_model` for the LLM) |
| A guarantee every source/stage must satisfy | `contract/` (parametrize over the registry) |
| A new source's `driver()` wiring | nothing — `integration/test_source_drivers.py` is parametrized over the registry; only add a test if it diverges |
| The orchestration IO boundary | `integration/test_orchestration_io.py` with `local_bucket` |
| The forecast-resolution flow to the leaderboard | `e2e/test_resolution_pipeline.py` (semantic anchors + `check_golden`) |
| The question-set creation flow | `e2e/test_question_set_pipeline.py` (metadata → curate driver + `check_golden`) |
| An external API's field contract | `live/` (mark `@pytest.mark.live`) |

Time-dependent logic must use `freeze_today`; seed any RNG; never rely on row ordering.

## Expanding to other jobs (sources & resolve are just the start)

This suite is deep on **sources → resolve → leaderboard**, and now also covers **`metadata`** and
**`curate_questions`** (see the table). Still open: `base_eval`, `nightly_update_workflow`, the
website. The offline-import contract (`contract/test_offline_imports.py`) today covers the source
fetch/update jobs, `func_resolve`, and `leaderboard.main` — **not** the metadata/curate/base_eval/
nightly job modules yet; adding each to `JOB_MODULES` is the cheap first step when you start on it.
Beyond import, job *behavior* splits into two kinds:

**1. Pure-logic jobs** — same playbook we already use: `unit/` for the logic, *invariants* for the
properties, a *golden* for the whole output. No new technique.

**2. LLM-dependent jobs** (`metadata`, the LLM forecasters in `base_eval`) — need a **new
technique**: the model is a non-deterministic boundary you **mock** (this is why `model_eval` was
made lazy/offline-importable). You test the code *around* the model — prompt assembly, response
parsing, output schema, IO — **not the model's judgement**. Whether a category or forecast is
*correct* is validated out of band (like `live/` for APIs), never in `make test`.

| Job | Level(s) | Technique | Status / notes |
| --- | --- | --- | --- |
| `curate_questions` (question sets) | `unit/curate_questions/` + `e2e/test_question_set_pipeline.py` | allocation **invariants** (`allocate_evenly`: even, capped, sums or raises); bin/validity/freeze filters; **seeded** market + data + human sampling (`random_state`); the real `driver()` builds a published set, **goldened** | **covered** (units + curate-driver golden e2e). The whole sampling chain is now seedable via `QUESTION_SET_SEED`. Follow-up: JSON-schema the `*-llm.json`/`*-human.json` artifacts |
| `metadata` (tag + validate, **LLM**) | `unit/metadata/` (LLM mocked) + `integration/` + `e2e/` | mock the LLM → assert the response **parses** to `category ∈ QUESTION_CATEGORIES` / `valid_question ∈ {True,False}` (unknown→`"Other"`, missing→unvalidated); driver writes `question_metadata.jsonl` | **covered**. Categorization *correctness* is out of scope (validated out of band) |
| `base_eval` (naive + **LLM** forecasters) | `unit/` + `contract/artifacts/` | the naive forecast *functions* are data-in/data-out → invariants with fixed inputs (`forecast ∈ [0,1]`; naive uses `freeze_datetime_value`) — but the job does IO and the dummy forecasters use **unseeded** `np.random`, so seed or exclude those when goldening; LLM forecasters → mock boundary, parse → `forecast ∈ [0,1]`, schema the forecast-set file | uncovered (incoming PR will change this job) |
| `leaderboard` | `unit/leaderboard/` + `integration/test_leaderboard_compile.py` + `e2e/test_resolution_pipeline.py` | scoring/ordering (units + resolution e2e golden); read→filter→compile seam (`download_and_compile`, integration); **2FE + bootstrap** on a real-data-shaped fixture, **goldened** (`test_two_way_fixed_effects.py`); artifact serializers (`write_leaderboard_js_file_*`) unit-tested | **covered** for scoring + artifacts + compile + 2FE. Follow-up: schema-gate the published CSV/JS |
| `nightly_update_workflow` (manager/worker) | `unit/` | the **DAG/scheduling** logic with a fake job runner (what blocks on what, what parallelizes); real Cloud Run is GCP | out of scope for offline; logic-only |
| `www.forecastbench.org` (Jekyll) | — | site build (`bundle exec jekyll build`) in a **separate CI lane** | not Python; not part of `make test` |

The shape stays the same: registry-/scenario-**parametrize** what's uniform, give divergences their
own test, and reach for a **golden** wherever the output is large and emergent (a question set, a
forecast set, the leaderboard CSV) rather than hand-asserting every cell.

## Known follow-ups

- **Sampling seeding — done.** The whole sampling surface is now seedable: `curate_questions`
  threads a `random_state` through `human_sample_questions` / `llm_sample_questions` /
  `sample_market_questions` / `stratified_sample_questions` (driver opts in via `QUESTION_SET_SEED`),
  and `leaderboard.generate_simulated_leaderboards` takes a per-replicate `seed`. Both have golden /
  determinism tests.
- **Pandera `Check` tightening.** The frame-level invariants (value ∈ [0,1]; no pre-due resolution
  date) are asserted at the contract layer. Promoting them into the prod `_schemas.py` models as
  `Check`s is deferred until validated against real prod data (a too-strict schema on unseen data
  would break the nightly).
- **Public-artifact schemas.** Leaderboard CSV/JS and question-set outputs don't yet have schema
  gates (`contract/artifacts/`) — the goldens pin *values*, not a *schema* contract.
- **2FE / bootstrap scoring — covered.** `unit/leaderboard/test_two_way_fixed_effects.py` exercises
  the real ranking method on a real-data-shaped fixture (the `unit/leaderboard` scoring tests still
  use the non-regression scorers, since `pyfixest` is fragile on tiny inputs).
