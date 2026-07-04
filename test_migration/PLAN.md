# Test Migration Plan v2 — fold main's LLM-forecaster tests into the offline pyramid

**Branch:** `feat/offline-test-framework` · **Status:** v3 — **Codex-agreed** across rounds 1–3
(see `codex_review_round1.md` + §9). Ready to execute.

---

## 0. Context, scope & baseline

After rebasing onto `main`, commit `6566923 refactor: rewrite LLM forecaster` left **non-pyramid
test artifacts** beside the offline pyramid (`unit/ contract/ integration/ e2e/ live/`):

- **3 dirs:** `src/tests/llm_forecaster/` (10 files + `smoke_test/smoke_test.py`),
  `src/tests/orchestration/` (5), `src/tests/leaderboard/` (2).
- **9 root-level `src/tests/*.py` files** (missed in the first inventory) — all from the same commit.

**Scope (user-approved):** the **3 dirs** + the **6 clean-mapping root files**
(`test_run_mode`, `test_constants`, `test_cloud_run`, `test_model_request_params`,
`test_shared_llm_model_runs`, `test_runtime_requirements`). **Left at root** (out of scope):
`test_nightly_workflow_llm_forecaster` (README-deferred nightly DAG), `test_legacy_llm_cleanup`,
`test_utils_cleanup`.

**Baseline (external `/home/venv`, offline):** the 3 dirs = 216 passed / 1 skipped / 1 `@live`
deselected (218 cases). The 6 root files add more; whole suite is green.

**Success = behavior preserved, not raw-count preserved.** Because impl-detail guards are pruned
(§6), track a **behavioral-assertion inventory** (every black-box behavior/contract survives),
not a test-count parity check (Codex MUST-8/§5).

---

## 1. Principles (level semantics tightened per Codex)

1. **Behavior-preserving.** Every black-box behavior, data contract, and named architecture/security
   rule survives — relocated to the right level, or rewritten as caller-visible behavior.
2. **Level = smallest scope that proves it:**
   - **unit/** — pure logic **and** code exercised with its external backend *mocked at the seam*
     (LLM `get_response`, `gcp.storage.*`, `_io.urlopen`). Writing scratch files to `tmp_path` is a
     unit technique (existing runner tests already do it).
   - **integration/** — real IO wiring: the real `_io`/storage/driver code, GCS mocked at the
     `gcp.storage` seam, reading/writing a temp tree (`local_bucket` **or** `tmp_path`). Precedent:
     `integration/test_orchestration_io.py` already mocks `gcp.storage.list/upload`.
   - **contract/** — system-wide/registry guarantees, architectural AST checks, packaging/dependency
     contracts, offline-import, and external-artifact/data audits.
   - **e2e/** — whole offline flow + `check_golden` snapshot. **live/** — real network, `@live`.
3. **LLM boundary technique:** mock the model run's `get_response` (and `runner.parsing.parse_*`);
   never call a provider.
4. **Dedup against the *whole* suite** (incl. the 9 root files), not just the 5 level dirs.
5. **Impl-detail guard policy (Codex/AGENTS.md):** keep black-box behavior, public/data contracts,
   named architecture/security rules (AST → contract). **Remove** private-symbol-absence, private
   signature/call-style introspection, source-substring assertions, and tests-of-test-fixtures;
   where they encode a real requirement, rewrite as caller-visible behavior. Every prune is recorded
   in `test_migration/notes/`.

### Two evidence-based push-backs on Codex round 1 (for round-2 confirmation)
- **Keep the 3 orchestration-IO files cohesive at `integration/`** rather than unit/integration
  splitting each. This follows the README's *own* integration definition — *"fetch()/update()/LLM/
  git/Slack are mocked at the boundary; everything between is the real code"* — which is exactly what
  these tests do: mock the GCS/`urlopen` boundary, exercise the real `_io`/`_llm_forecaster_io`
  routing code, and (several) write/read a real temp tree. It also honors Codex **decision 10**
  ("retain three source-oriented IO files, but extract dependency contracts, pure helpers,
  implementation-absence checks"), which we do: **extract** the GitPython dependency test → contract
  and **prune** the impl-absence test. (Codex MUST-1's "integration = real local IO *only*"
  over-reads the README, whose integration tier explicitly includes boundary-mocked tests.)
- **Keep `LLMCallTranscript` tests at `unit/`** (in a cohesive `test_model_run_transcripts.py`),
  not integration. Existing runner unit tests already write/read transcript files under `tmp_path`
  (e.g. `test_*_empty_response_does_not_call_extraction_model` reads `transcript.markdown_filename`).
  Splitting transcript-content tests to integration while leaving sibling tmp_path-writing runner
  tests at unit would be inconsistent. (If Codex still prefers integration, we move the pure
  `LLMCallTranscript` file-format tests there; the decision is isolated to one file.)

---

## 2. Target structure (v2)

```
unit/llm_forecaster/  (NEW + __init__.py)
  test_forecast_variants.py      ← test_forecast_variants.py            (prune hasattr-absence)
  test_fb_model_runs.py          ← test_model_runs.py                   (drop dup; prune source-string; fix src_root depth; repoint globs)
  test_output.py                 ← test_output.py                       (drop source-string "no write" guard)
  test_parsing.py                ← test_parsing.py
  test_prompts.py                ← test_prompts.py                      (prune "parser is private")
  test_question_set.py           ← test_question_set.py                 (prune __file__/hasattr guards)
  test_runner.py                 ← test_runner.py  (core forecasting)   (prune signature/AST/hasattr guards)
  test_model_run_transcripts.py  ← test_runner.py  (LLMCallTranscript file tests; push-back #2)
  test_smoke_test.py             ← test_smoke_test.py                   (behavioral; subprocess lazy-import assertion → contract/test_offline_imports.py)

unit/orchestration/  (NEW + __init__.py)
  test_llm_forecaster_worker.py  ← orchestration/test_llm_forecaster_worker.py   (minus deploy-staging; fix parents→[4])
  test_llm_forecaster_manager.py ← orchestration/test_llm_forecaster_manager.py  (minus deploy-staging + test-of-fixture; fix parents→[4])

unit/  (root-level unit, like existing test_dates.py)
  test_run_mode.py               ← test_run_mode.py                     (root file)
  test_cloud_run.py              ← test_cloud_run.py                    (root file; prune 2 test-of-fixture guards)
  [test_constants.py DROPPED — not relocated; whole file is an impl-detail guard, §5/MUST-2]

unit/metadata/
  test_model_request_params.py   ← test_model_request_params.py        (root file; keep behavioral, prune source-string; fix parents→[4])

unit/leaderboard/
  test_llm_identities.py         ← leaderboard/test_llm_identities.py   (drop _patched_import_environment→direct import; minus deploy-staging; prune hasattr; fix parents→[4])
  test_llm_identity_release_dates.py ← leaderboard/test_llm_identity_release_dates.py (direct import; minus external-artifact audit; fix parents→[4])

integration/
  test_llm_forecaster_io.py      ← orchestration/test_llm_forecaster_io.py
  test_forecast_file_io.py       ← orchestration/test_forecast_file_io.py         (prune impl-absence guard)
  test_question_set_io.py        ← orchestration/test_question_set_io.py           (minus GitPython test; parents stays [3])

e2e/
  test_llm_forecaster_pipeline.py ← llm_forecaster/test_real_question_set_forecast.py
        offline golden test  +  @live companion (real published set)               (Codex MUST-3)

contract/
  test_llm_forecaster_conventions.py ← llm_forecaster/test_orchestration_boundary.py (import-layering AST)
                                        + top-level-import policy + future-annotations convention (relocated from test_model_runs — MUST-4)
  test_shared_llm_model_runs.py  ← test_shared_llm_model_runs.py  (root; parents→[3]; fix ALLOWLIST path; drop `__file__` assert — MUST-2)
                                     + provider-coverage + active-model release-date coverage (relocated registry guarantees — MUST-4)
  test_runtime_requirements.py   ← test_runtime_requirements.py   (root; parents→[3])
  test_deploy_staging.py         ← NEW: job-specific deploy asserts from worker/manager/leaderboard (deduped vs runtime_requirements) + GitPython test
  test_llm_forecast_set_artifacts.py ← NEW: the processed-forecast-set model-run-key audit (from release_dates)
  test_offline_imports.py        ← EDIT: +worker +manager (JOB_MODULES + COLD_IMPORT_MODULES); +smoke lazy-import subprocess assertion

MOVE (tooling out of tests/):
  src/llm_forecaster/smoke_test.py ← src/tests/llm_forecaster/smoke_test/smoke_test.py

EDIT: src/tests/README.md  (new unit/integration/e2e rows; drop stale "LLM forecaster not yet covered")
DELETE (emptied): src/tests/{llm_forecaster,orchestration,leaderboard}/ + the 5 relocated root files
DELETE (dropped): src/tests/test_constants.py  (impl-detail-only guard, §5/MUST-2)
```

---

## 3. Path-depth fixes (Codex MUST-4) — every `Path(__file__).parents[N]` / glob in scope

| File (new home) | old | new | extra |
| --- | --- | --- | --- |
| `unit/llm_forecaster/test_fb_model_runs.py` | `src_root=parents[2]` | `parents[3]` | repoint globs to `src/llm_forecaster/**` + relocated test homes |
| `unit/orchestration/test_llm_forecaster_worker.py` | `parents[3]` | `parents[4]` | — |
| `unit/orchestration/test_llm_forecaster_manager.py` | `parents[3]` | `parents[4]` | — |
| `unit/metadata/test_model_request_params.py` | `parents[2]` | `parents[4]` | — |
| `unit/leaderboard/test_llm_identities.py` | `parents[3]` | `parents[4]` | — |
| `unit/leaderboard/test_llm_identity_release_dates.py` | `parents[3]` | `parents[4]` | `ROOT.parent/"forecastbench-processed-forecast-sets"` stays valid once ROOT fixed (audit moves to contract) |
| `contract/test_shared_llm_model_runs.py` | `parents[2]` | `parents[3]` | ALLOWLIST self-path → `.../contract/test_shared_llm_model_runs.py` |
| `contract/test_runtime_requirements.py` | `parents[2]` | `parents[3]` | — |
| `contract/test_llm_forecaster_conventions.py` (← test_orchestration_boundary.py) | `parents[3]` | `parents[3]` (unchanged) | same depth (llm_forecaster→contract) |
| `integration/test_question_set_io.py` | `parents[3]` | `parents[3]` (unchanged) | same depth (orchestration→integration) |

---

## 4. Dedup (Codex MUST-5) — incoming vs existing whole-suite

| Incoming | Existing | Action |
| --- | --- | --- |
| `test_model_runs.py::test_forecastbench_does_not_declare_local_model_runs` (source-string on fb_model_runs) | `contract/test_shared_llm_model_runs.py::test_forecastbench_does_not_declare_local_model_runs` (repo-wide AST, stronger) | **DROP** incoming |
| `test_model_runs.py::test_forecastbench_selects_active_shared_model_run_objects` | `test_shared_llm_model_runs.py::test_forecastbench_declares_selected_shared_model_run_keys_only` (core equality) | keep incoming (richer: per-run `active`, round-trip); note overlap |
| worker/manager/leaderboard `test_*_deploy_stages_*` — generic parts (`UTILS_PIN not in requirements`, `cat runtime.txt requirements.txt > upload/…`) | `test_runtime_requirements.py` (covers these for *all* deploy dirs) | **DROP** generic asserts; **preserve every unique job contract** (MUST-3) in `contract/test_deploy_staging.py`: exact job names `func-llm-forecaster-{worker,manager}`, manager `TEST_OR_PROD=$(if …)` staging, service-account, `ORCHESTRATION_EXTRA_PACKAGES=llm_forecaster`, `cp _llm_forecaster_io.py`, leaderboard `cp -r $(ROOT_DIR)src/llm_forecaster` + `LEADERBOARD_DEPENDENCIES` |
| orchestration-IO tests | `integration/test_orchestration_io.py` (`_source_io`, `upload_resolution_set`, `read_forecast_file`) | **no overlap** — keep all |
| leaderboard identity / 2FE-selection / `get_df_info`-classification | `unit/leaderboard/test_{two_way_fixed_effects,df_info_and_masks,scoring}.py` | **complementary** — keep all |

---

## 5. Impl-detail guard audit (Codex MUST-6) — KEEP / RELOCATE / PRUNE / LOOSEN

| Test | Kind | Action |
| --- | --- | --- |
| variants `…not hasattr(ZERO_SHOT,"model_suffix")` | hasattr-absence | LOOSEN (drop the two asserts; keep the active-variant behavior) |
| model_runs `…does_not_declare_local_model_runs` | source-string | DROP (dup, §4) |
| model_runs `…options_are_declared_…` (source-string half) | source-string | PRUNE source-string asserts; KEEP option-value asserts |
| model_runs `…indexes_use_prefixed_names` | hasattr-absence | PRUNE |
| model_runs `…model_runs_do_not_declare_local_api_key_config` | source-string | PRUNE |
| model_runs `…model_run_imports_are_top_level` | AST (module) | **RELOCATE → contract/test_llm_forecaster_conventions.py** (MUST-4) |
| model_runs `…files_do_not_use_future_annotations` | glob/convention | **RELOCATE → contract/test_llm_forecaster_conventions.py** (MUST-4); repoint globs (§3) |
| model_runs `…provider_max_workers_covers_all_shared_providers` | registry coverage | **RELOCATE → contract/test_shared_llm_model_runs.py** (MUST-4) |
| release_dates `…include_canonical_active_llm_model_keys` | registry coverage | **RELOCATE → contract/test_shared_llm_model_runs.py** (MUST-4) |
| shared_llm_model_runs `assert Path(fb_model_runs.__file__).name == …` | `__file__` assert | **DROP** (MUST-2; keep the `FB_MODEL_RUNS == select_model_runs` behavior) |
| identities `assert not hasattr(identity, "model")` | hasattr-absence | **DROP** (MUST-2; keep the identity attribute/`as_normalized_fields` behavior) |
| output `…builds_data_but_does_not_write_files` | source-string | PRUNE (intent covered by all return-value tests) |
| prompts `…field_parser_is_private` | hasattr-absence | PRUNE |
| question_set `…module_name_matches_domain` / `…does_not_load_through_boundary_reader` | `__file__`/hasattr | PRUNE |
| runner `…do_not_force_keyword_only_arguments` / `…pass_arguments_by_name` / `…does_not_expose_timing_recorder_argument` / `…does_not_expose_final_forecast_file_persistence_helpers` | signature/AST/hasattr | PRUNE |
| runner `…prompt_rendering_helpers_are_not_cached…` | hasattr-absence + behavior | SPLIT: keep the render behavior; drop hasattr asserts |
| runner `…does_not_preload_prompts` | behavioral (monkeypatch render→fail) | KEEP |
| transcripts `…owns_file_write_helpers` / `…does_not_expose_upload_target_builder` | staticmethod/hasattr | PRUNE |
| manager `…fixture_replaces_stale_parent_cloud_run_attribute` | test-of-test-fixture | PRUNE (Codex §5) |
| cloud_run `…stub_import_leaves_no_parent_package_attribute` / `…fixture_replaces_stale_parent_package_attributes` | test-of-test-fixture | PRUNE |
| forecast_file_io `…does_not_expose_llm_transcript_upload_helper` | hasattr-absence | PRUNE |
| identities `…construction_is_inlined` | hasattr-absence | PRUNE |
| identities `…lookup_is_not_built_for_keyless…` / `…legacy_variant_metadata_tracks…` / `…model_key_is_returned_…_not_added_later` | hasattr + behavior | SPLIT: keep behavior (KeyError/values); drop hasattr |
| model_request_params `…callers_use_metadata_model_response_helper` / `…no_longer_contains_legacy_provider_routing` / `…constants_do_not_expose_legacy…` | source-string/hasattr | PRUNE (behavior covered by the routing tests kept) |
| constants `…logo_lookup_lives_with_leaderboard_code` (whole `test_constants.py`) | hasattr-absence | **DROP the file** (MUST-2; intent — logo lookup lives in leaderboard — is covered by the leaderboard `get_org_logo` tests). **FLAG to user:** you asked to fold `test_constants.py`, but its sole content is an impl-detail guard; per the agreed guard policy it is pruned, not relocated. Restore on request. |
| release_dates `…model_release_dates_csv_is_removed` | file-absence | KEEP (real "CSV removed" data contract) |

**Net:** ~11 prune, ~6 split (keep behavior), ~3 loosen, rest keep. All recorded per-file.

---

## 6. e2e + golden spec (Codex MUST-3)

`e2e/test_llm_forecaster_pipeline.py`:
- **Offline golden test:** build a `QuestionSet` from a fixture carrying the **full published record
  field set** (2 dataset + 2 market; fields per the runner's real consumers — the same shape the
  runner tests' `_dataset_question`/`_market_question` use, derived from the real 2026-05-24 set) →
  `run_model` with a **fixed** `FakeRun` (stable slug/provider/lab/model_run_key) + deterministic
  `get_response` (dataset probs by index, market `*0.42*`) → write final files (offline). Assert the
  existing schema/row/marker anchors **and** `check_golden(frame)`.
  - **Golden frame:** one DataFrame combining both variants, columns
    `[variant, source, id, resolution_date, forecast, reasoning]`, unique key
    `(variant, source, id, resolution_date)`, sorted by it, `rtol=0`. Commit
    `src/tests/golden/e2e_llm_forecaster_forecast_set.csv`.
- **`@live` companion:** the original test (fetch the real published `2026-05-24-llm.json`, mocked
  `get_response`, assert the runner accepts it + writes valid files). Marked `@pytest.mark.live`,
  deselected by default — preserves the real-published-record-shape assertion (Codex §4).

---

## 7. Cross-cutting edits

- **`__init__.py`:** add `unit/llm_forecaster/__init__.py` **and** `unit/orchestration/__init__.py`.
- **Import roots:** `src.tests.llm_forecaster.smoke_test` → `llm_forecaster.smoke_test`; the
  `tests.leaderboard.test_llm_identities._import_leaderboard_main` cross-import disappears with the
  direct-import switch.
- **Offline-import contract (MUST-7):** add `orchestration.func_llm_forecaster_worker.main` **and**
  `orchestration.func_llm_forecaster_manager.main` to `JOB_MODULES` **and** `COLD_IMPORT_MODULES`
  (both verified cold-importable under the offline guard). Fold the smoke lazy-import subprocess
  assertion here.
- **README (MUST-8):** drop the stale "LLM forecaster not yet covered" note; add the new
  unit/integration/e2e/contract rows.
- **smoke_test.py docs:** update the invocation to `python -m llm_forecaster.smoke_test`; update the
  subprocess guard's blocked-import target.
- **Empty-dir cleanup:** delete the 3 dirs + the 6 relocated root files (+ `__pycache__`).

---

## 8. Execution order & verification

1. Create `unit/llm_forecaster/`, `unit/orchestration/` (+`__init__.py`).
2. `git mv` + rename the pure/unit llm_forecaster tests; apply §5 prunes; split transcripts.
3. Move `smoke_test.py` → `src/llm_forecaster/`; fix `test_smoke_test.py` import; move its subprocess
   guard into `contract/test_offline_imports.py`.
4. Move worker/manager → `unit/orchestration/`; fix `parents[4]`; prune fixture-test; extract deploy.
5. Move the 3 IO files → `integration/`; extract GitPython test → contract; prune impl-absence.
6. Move leaderboard tests → `unit/leaderboard/`; direct imports; extract artifact audit → contract;
   fix `parents[4]`.
7. Relocate 5 root files (unit/contract); **drop `test_constants.py`**; fix all `parents[N]`/ALLOWLIST (§3).
8. Build `e2e/test_llm_forecaster_pipeline.py` + golden (§6).
9. Build `contract/test_deploy_staging.py` (deduped) + `contract/test_llm_forecast_set_artifacts.py`;
   edit `test_offline_imports.py` (MUST-7).
10. Update `src/tests/README.md`; delete emptied dirs/files.
11. **Verify:** `pytest src/tests -q` from `/home/venv` (0 failures); `UPDATE_GOLDEN=1` once, review
    diff; `make lint` clean. Confirm the **behavioral-assertion inventory** (§0): every kept
    behavior/contract present; every prune is a non-behavioral guard listed in the notes.

## 9. Deliverables & Codex round-1 resolution

- `PLAN.md` (this) + `codex_review_round1.md` (verdict) + `test_migration/notes/` (one note per
  original file: destination, prunes, rewrites).
- **Codex round-1 → resolution:** MUST-1 ✔ (unit/orchestration); MUST-2 ✔ (smoke/gitpython/artifact
  extracted; transcript = push-back #2); MUST-3 ✔ (offline golden + `@live` companion, spec'd);
  MUST-4 ✔ (§3 table); MUST-5 ✔ (§4 table); MUST-6 ✔ (§5 audit); MUST-7 ✔ (worker+manager,
  in-process+cold); MUST-8 ✔ (README + both `__init__.py` + committed golden). Two push-backs (IO
  cohesion; transcripts at unit) submitted for round-2.
- **Codex round-2 → resolution:** *"Both push-backs accepted; path table and e2e/golden sufficient."*
  4 residual MUSTs folded into this v3: (r2-1) `test_smoke_test.py → unit/llm_forecaster/` mapping
  added (§2); (r2-2) complete pruning — drop `test_constants.py`, the shared-run `__file__` assert,
  the identity `.model`-absence assert (§5); (r2-3) preserve unique deploy contracts — manager
  `TEST_OR_PROD`, exact job names, leaderboard `cp -r src/llm_forecaster` (§4); (r2-4) relocate
  architecture/registry checks (top-level-import, future-annotations, provider-coverage,
  active-model release-date coverage) to `contract/` (§2, §5).
- **Codex round-3 → AGREE on substance.** Residual items were plan-consistency only (stale
  `test_constants.py` relocation in §2/§8; the §3 `test_import_boundaries`→`test_llm_forecaster_conventions`
  name; v2/round-2 labels) — all fixed in this v3. Plan is settled; executing.

---

## 10. Result (executed)

- **Suite:** `868 passed, 5 skipped, 6 deselected, 0 failed` (offline, external `/home/venv`). Lint:
  `black`/`isort`/`flake8`/`pydocstyle` clean. `@live` e2e companion verified passing against the
  real published question set.
- **Count:** the ~11 fewer passing vs the pre-migration 879 is the intentional impl-detail-guard
  pruning (Codex MUST-6), net of the new e2e + offline-import + registry additions. Every black-box
  behavior/data-contract/architecture rule survives (behavioral-assertion inventory, not raw count).
- **Tree:** the 3 flat dirs + `test_constants.py` are gone; `src/tests/` is a clean pyramid.
  `smoke_test.py` now lives in `src/llm_forecaster/`. New golden:
  `src/tests/golden/e2e_llm_forecaster_forecast_set.csv`.
