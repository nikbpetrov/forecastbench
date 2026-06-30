# ForecastBench test suite

A fast, **GCP-independent** test suite for the refactored ForecastBench code. It runs entirely
offline (`make test`, ~1 minute), and is organized by *test level* so a failure tells you both
what broke and at what scope.

## Mental frame

> **Run the real production code, offline, at the smallest scope that proves the behavior.**

- Most behavior is pinned at the **pure domain layer** (data in → data out, no IO).
- A thin set of tests proves the **IO wiring** (the real storage/driver code against a temp dir).
- Two tiers prove the **whole offline flows**, end to end.
- Nothing in the default run touches GCP, the network, or secrets — enforced. External APIs are checked separately, out of band.

**Level is the directory; technique is how you assert inside it.**

## Layout

```
tests/
  unit/            pure, in-memory logic — the bulk (sources, resolve, leaderboard, curate, metadata)
  contract/        system-wide / registry-parametrized guarantees + the offline-import contract
  integration/     one real IO boundary (local bucket): driver wiring & adjacent-component seams
  e2e/             whole offline flows, end to end, with golden snapshots
  live/            opt-in, real APIs, schema-asserted (never in PR CI)
  golden/          committed snapshot CSVs the e2e / 2FE tests regression-check against
  factories.py     builders (make_*_df, make_*_forecast_set, make_leaderboard_entries, API responses)
  conftest.py      fixtures (freeze_today, local_bucket, autouse offline guards, source instances)
  _harness/        framework code (no-network guard, local-bucket mount)
  _golden.py       check_golden() snapshot helper (UPDATE_GOLDEN=1 to re-bless)
  _sources.py      IMPLEMENTED_SOURCES / STUB_SOURCES classification
```

```
        ▲  few    e2e/          one whole offline flow, incl. buckets → leaderboard
       ╱ ╲        integration/  IO boundary / driver wiring
      ╱   ╲       contract/     registry-wide guarantees (schema, fail-fast, coverage, offline-import)
     ╱     ╲      unit/         pure domain logic + invariants  ◀── primary
    ╱_______╲     live/         sits outside the pyramid (opt-in, real network)
       many
```



## Offline by construction

The default run cannot reach GCP, the network, or Secret Manager — this is enforced by two autouse
fixtures (`conftest.py` / `_harness/network.py`) plus a small Layer-0 refactor that made imports
side-effect-free:

- `_guard_network` replaces `socket.socket`; any non-loopback `connect` raises
`BlockedNetworkError`, so an accidentally-unmocked HTTP call fails loudly instead of hitting a
live API.
- `_fake_secrets` patches `keys.get_secret` to a deterministic dummy, so secret access never
reaches Secret Manager.
- **Lazy by construction:** secrets (`helpers/keys.py`), LLM clients (`helpers/model_eval.py`), env
(`helpers/env.py`), the bucket mount (`utils/gcp/storage.py`), and the leaderboard's
`model_release_dates.csv` are all read at *call* time, not import time — so every job module
imports clean. The **offline-import contract** (in `contract/`, below) makes that executable.

Both guards are lifted for `@pytest.mark.live` tests, which are **excluded by default**
(`addopts = -m 'not live'`).

The `local_bucket` fixture points `BUCKET_MOUNT_POINT` and the `*_BUCKET` env vars at a temp
dir, so `utils.gcp.storage` reads/writes locally through the *real* IO code. Its `LocalBucket`
helpers (`seed_questions`/`seed_fetch`/`seed_resolution_file`/`seed_*_forecast_set`/`seed_metadata`,
`read_*`, `list_*`) use the real filename conventions, so a test exercises the production path with
no GCP.

## Coverage by technique

What each pipeline stage actually has tested, at each level. (A blank cell is intentional — see the
note under each table.)

### `unit/` — pure domain logic, no IO

In-memory, one concern per test, the bulk of the suite. External HTTP is mocked **ad-hoc per
source** (`@patch("sources.X.requests.get")`); the LLM is mocked at `model_eval.get_response_from_model`.


| Stage / area              | What's pinned                                                                                                                                                                                                         |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **sources** (per source)  | parsing of fetched payloads, `update()` assembly, and `resolve()` outcomes — one `unit/sources/test_<source>.py` each                                                                                                 |
| **source base classes**   | `BaseSource` / market / dataset shared behavior, hashable id/direction columns, types & schemas, date helpers, cross-source invariants                                                                                |
| **resolve**               | `resolve_all` (market + dataset), `impute_missing_forecasts` (0.5 / Naive / Imputed), `check_and_prepare_forecast_file` (drop/validate), `explode_question_set`                                                       |
| **metadata** (LLM mocked) | tag parsing → `category ∈ QUESTION_CATEGORIES` (unknown → `Other`); validate parsing → `ok` / `flag` / missing / ambiguous                                                                                            |
| **curate_questions**      | `allocate_evenly` invariants (even / capped / over-request *raises*), market+horizon bin math, validity + freeze filters, `drop_invalid` `(id, source)` join, **seeded** human + LLM sampling                         |
| **leaderboard**           | Brier / peer / Brier-skill scoring, question masks, `get_df_info` + `question_pk`, ordering invariants, artifact serializers, and **2FE + bootstrap** on a real-data-shaped fixture (`test_two_way_fixed_effects.py`) |


> No shared recorded-fixture replay layer is kept on purpose: parse paths are covered here, and
> *drift* against the real APIs is caught by the opt-in `live/` suite.



### `contract/` — system-wide / registry guarantees

Cross-source and whole-suite invariants, parametrized so a new source is covered automatically —
**registry-aware, not registry-blind** (`offline_update_case` in `conftest.py` patches the network
seams of `update()` so its *assembly* is what's asserted).


| Guarantee                             | What's asserted                                                                                                                                                                                                                                                      |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `resolve()` behavior — all sources    | fail-fast on missing id / empty / unknown source; nullified rows dropped; value ∈ [0,1]; no resolution date before the due date                                                                                                                                      |
| `update()` conformance — all sources  | output validates `QuestionFrame` with **exactly** `QUESTION_FILE_COLUMNS` (catches column leaks `strict=False` schemas miss)                                                                                                                                         |
| registry coverage                     | every `sources.registry` entry is an `IMPLEMENTED_SOURCES` case or a named `STUB_SOURCES` (`_sources.py`) — a new source fails until classified                                                                                                                      |
| offline-import — **all covered jobs** | every job entry (each source fetch/update, `func_resolve`, `metadata` tag+validate, `curate_questions`, `leaderboard.main`) + lazy `helpers.{keys,env,model_eval}` import with no GCP/network/secrets; heavy chains re-checked in a cold subprocess with bogus creds |


> `contract/` holds *cross-source / system-wide* guarantees, so it's parametrized over the registry
> or the job list. Single (non-registry) jobs — metadata, curate, leaderboard — have **no per-job
> contract folder by design**: their system-level proof is the offline-import row above plus an e2e
> golden; their behavioral contracts are unit + integration tests.



### `integration/` — one real IO boundary (the local bucket)

Two adjacent components across a real seam: the production `driver()` reads inputs from a
`local_bucket`, runs, and writes outputs — no GCP. `fetch()`/`update()`/LLM/git/Slack are mocked at
the boundary; everything between is the real code.


| Boundary / driver            | Wired & asserted                                                                                                                                                                                            |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **source** `driver()`**s**   | read bank + fetch → `fetch()`/`update()` (mocked) → write questions + resolution files; **parametrized over** `IMPLEMENTED_SOURCES`; `polymarket.update()` also run **unmocked** as a real end-to-end chain |
| `func_resolve.driver()`      | raw forecast set + question set + bank → resolve + impute → **processed forecast set** (schema, `resolved`/`resolved_to`/`imputed`, JSON round-trip, eligibility preserved)                                 |
| **leaderboard compile**      | seeded processed sets → `download_and_compile` date / min-resolved / eligibility filters → `get_df_info` → exact `question_pk` keys                                                                         |
| **metadata** `driver()`**s** | tag + validate → `question_metadata.jsonl`; **stateful**: idempotent re-run, incremental tagging, stale-row prune, `Other` persists (LLM + `time.sleep` mocked)                                             |
| **orchestration IO**         | `_source_io` ↔ `local_bucket`, including empty-file edge cases                                                                                                                                              |


> Rule of thumb: parametrize while the seam is uniform; the moment a source/job needs bespoke
> setup, give it a dedicated test *beside* the parametrized one rather than branching inside it.



### `e2e/` — whole offline flows + golden snapshots

Each e2e runs many real stages across sources and asserts behavior *throughout* — a few
**intent-revealing anchors** (open market excluded, `Good` ranks above `Bad`, a flagged question
never reaches the set) *and* a `check_golden` **snapshot** of the terminal frame. They're
complementary: the anchors pin *what's correct*, the golden is the catch-all net for *everything
else that moved*, so a wrong re-bless that flips behavior still trips an anchor.


| Flow                                                        | Stages exercised                                                                                                                                | Golden snapshot                                          |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **forecast resolution** (`test_resolution_pipeline.py`)     | bucket update (polymarket) + seeded banks → `explode_question_set` → `resolve_all` → impute → leaderboard scoring/ordering                      | resolved frame + scored leaderboard, × {base, nullified} |
| **question-set creation** (`test_question_set_pipeline.py`) | seed banks + metadata → tag/validate `driver()` → `drop_invalid` / freeze filters → **curate** `driver()` → published `<date>-{llm,human}.json` | the published question set (llm + human)                 |


> The leaderboard's real ranking method (2FE + bootstrap) also has a golden, but in
> `unit/leaderboard/test_two_way_fixed_effects.py` — `pyfixest` is degenerate on tiny input, so it
> needs a real-data-shaped fixture rather than the e2e's small one.
>
> Goldens demand determinism (`freeze_today`, a seeded RNG, a stable sort key) and freeze only
> scalar columns that round-trip through CSV. **Check** runs inside `make test`; **re-bless** is a
> deliberate dev step, never CI:
>
> ```bash
> UPDATE_GOLDEN=1 make test ARGS="src/tests/e2e"   # rewrite the e2e goldens; the diff is the review
> ```
>
> CSV (not Parquet) is chosen so the diff is human-readable; `.gitignore` un-ignores
> `src/tests/golden/**/*.csv`.



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

`make lint` (black/isort/flake8/pydocstyle) must pass before committing. Time-dependent logic must
use `freeze_today`; seed any RNG; never rely on row ordering.

## Adding tests


| You want to test…                                                             | Put it in                                                                                               |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| A source's parse/update/resolution edge case on synthetic data                | `unit/sources/test_<source>.py` (`make_*` factories; mock `requests` ad-hoc)                            |
| A `resolve` / `leaderboard` / `metadata` / `curate_questions` logic edge case | `unit/<area>/` (mock `model_eval.get_response_from_model` for the LLM)                                  |
| A guarantee every source/stage must satisfy                                   | `contract/` (parametrize over the registry or the job list)                                             |
| A new source's `driver()` wiring                                              | nothing — `integration/test_source_drivers.py` is registry-parametrized; only add a test if it diverges |
| Another job's `driver()` against the bucket                                   | `integration/test_<job>_*.py` with `local_bucket`                                                       |
| The forecast-resolution flow to the leaderboard                               | `e2e/test_resolution_pipeline.py` (anchors + `check_golden`)                                            |
| The question-set creation flow                                                | `e2e/test_question_set_pipeline.py` (metadata → curate driver + `check_golden`)                         |
| An external API's field contract                                              | `live/` (mark `@pytest.mark.live`)                                                                      |




## Not yet covered

- `base_eval` (naive + LLM forecasters) — deferred; an incoming PR reshapes the job. When it
lands: naive forecasters are data-in/data-out → invariants in `unit/`; LLM forecasters → the same
mock-the-boundary technique as `metadata`; schema + golden the forecast-set output.
- `nightly_update_workflow` (manager/worker) — the DAG/scheduling logic is testable offline with
a fake job runner, but needs a small refactor first (extract `compute_dag` + a pluggable runner
from the Cloud Run glue).
- `www.forecastbench.org` (Jekyll) — site build belongs in a separate, non-Python CI lane.

**The LLM boundary technique.** `metadata` (and `base_eval`'s LLM forecasters) talk to a
non-deterministic model, so you **mock** `model_eval.get_response_from_model` and test the code
*around* it — prompt assembly, response parsing, output schema, IO — never the model's *judgement*.
Whether a category or forecast is *correct* is validated out of band (like `live/` for APIs), never
in `make test`.

## Still open on covered jobs

- **Public-artifact schemas.** The leaderboard CSV/JS and question-set JSON have golden *value*
checks but no *schema* gate (`contract/artifacts/`). A schema contract would catch shape drift
independent of the frozen values.
- **Pandera** `Check` **tightening.** The frame-level invariants asserted at the contract layer
(value ∈ [0,1]; no pre-due resolution date) could be promoted into the prod `_schemas.py` models
as `Check`s — deferred until validated against real prod data, since a too-strict schema on unseen
data would break the nightly.

