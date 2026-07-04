# Codex review — round 1 (gpt-5.5, xhigh, read-only)

Verdict on `PLAN.md` v1: **CHANGES REQUIRED**. Full analysis below (verbatim summary); how each
point was resolved is tracked in `PLAN.md` §8.

## 1. Level and technique mapping (wrong/mixed placements Codex found)
- **worker/manager → `unit/orchestration/`, not `integration/`.** Their boundaries are entirely
  mocked; integration requires a *real local IO seam* (README:119). The README manager/worker
  deferral concerns `nightly_update_workflow`, not these entrypoints (README:214).
- **`test_orchestration_boundary.py` → `contract/`**, not unit — it's an architectural layering
  contract regardless of parametrization.
- **`test_runner.py` split.** Transcript persistence / filename-target tests (lines 990, 1054, 1119,
  1293) cross a real filesystem boundary → integration; core forecasting behavior stays unit. The
  "4 pure transcript tests" are *not* pure — they create files.
- **smoke subprocess import-layering test → `contract/test_offline_imports.py`**; remaining smoke
  behavior is unit.
- **`test_raw_question_set_readers_do_not_require_gitpython` → contract** (packaging/dependency
  contract, not integration).
- **`test_processed_forecastbench_llm_files_have_shared_model_run_keys` → contract** (system-wide
  data/artifact audit, not unit).
- **`test_forecast_file_io.py` is mixed:** local-write tests are integration; mocked
  list/delegation behavior is unit. Don't move wholesale.
- Cross-registry guarantees (provider coverage, active-model release-date coverage) are better under
  contract, especially where they duplicate existing registry guards.
- Pure LLM/parsing/output/prompt/identity/release-date mappings are reasonable.

## 2. The 10 decisions
1. DIFFERENT — `unit/orchestration/`; no real IO boundary; README deferral is unrelated.
2. AGREE (qualified) — `contract/test_deploy_staging.py`, but keep job-specific assertions and drop
   what `test_runtime_requirements.py` already covers.
3. DIFFERENT — import-layering test → `contract/`.
4. DIFFERENT — split real transcript/filesystem tests from core runner unit tests.
5. DIFFERENT — add offline e2e + golden **and** preserve the real-published-question-set behavior
   (live companion or a fixture derived from those exact four records).
6. AGREE — `src/llm_forecaster/smoke_test.py`; update `python -m llm_forecaster.smoke_test` docs.
7. AGREE — direct `leaderboard.main` imports are safe (verified cold import under the offline guard
   with bogus credentials).
8. DIFFERENT — add **both** worker and manager to `JOB_MODULES` and cold-import coverage
   unconditionally; both cold-import.
9. DIFFERENT — do not preserve implementation guards wholesale; apply the §6 policy.
10. AGREE (qualified) — keep three source-oriented IO files but extract dependency contracts, pure
    helpers, and implementation-absence checks.

## 3. Deduplication
- "Zero existing pyramid coverage" is true for the five level dirs but **false suite-wide**: root
  tests already cover `llm_forecaster`:
  - Shared-run selection overlaps `test_shared_llm_model_runs.py:50`.
  - The repo-wide AST prohibition on local `ModelRun` declarations
    (`test_shared_llm_model_runs.py:20`) is **stronger** than the incoming source-string test
    (`test_model_runs.py:175`).
- Orchestration-IO zero-overlap claim is **correct**.
- Leaderboard identity / 2FE-selection / `get_df_info` classification tests are **complementary**.
- Deploy tests duplicate suite-wide checks for the utils pin and staged runtime requirements
  (`test_runtime_requirements.py:25,54`).

## 4. Behavior-loss risks
- Replacing the fetched 2026-05-24 artifact with arbitrary inline questions **loses the only
  assertion that the runner accepts the real published record shape.** Keep a live companion or
  derive the offline fixture from the exact selected records.
- Golden underspecified: `check_golden` takes a **DataFrame, not JSON** (`_golden.py:62`). Define
  canonical frame(s) keyed by variant/source/id/resolution_date, explicit scalar columns, `rtol=0`.
- Dropping `_patched_import_environment` is **safe**.
- **Path breakage beyond §4.4:** `test_orchestration_boundary.py` `parents[3]`; `test_model_runs.py`
  `src_root` depth (line 368); both leaderboard files' `ROOT` (one absence assertion would silently
  pass against `src/src/...`); the processed-forecast checkout lookup; future-annotations glob must
  include the relocated e2e test.

## 5. Missing edits
- Add `unit/orchestration/__init__.py`.
- Update `src/tests/README.md` (its LLM-forecaster "not yet covered" is now stale; add new rows).
- Add both worker+manager to **cold-subprocess** import coverage, not only in-process `JOB_MODULES`.
- Fold the smoke lazy-import subprocess assertion into the offline-import contract.
- Specify + commit the new golden CSV(s), canonical columns, unique key, stable identity, fixture.
- Remove the manager's test-of-the-test-fixture assertion (`test_llm_forecaster_manager.py:158`) —
  it verifies `sys.modules` scaffolding, not production behavior.
- Replace raw test-count parity with a behavioral-assertion inventory if impl-only tests are pruned.

## 6. Implementation-detail guards — policy
Retain black-box behavior, explicit public/data contracts, and named architecture/security rules
(architectural AST checks → `contract/`). **Remove** private-symbol-absence, private
signature/call-style introspection, and source-substring assertions; where they encode a real
requirement, replace with caller-visible behavior. The guards are **undercounted** in the plan —
they also occur in forecast_variants, output, prompts, orchestration IO, and leaderboard identities.
AGENTS.md rejects tests an equivalent implementation would fail (AGENTS.md:115).

## Verdict list
1. [MUST] worker/manager → `unit/orchestration/`; reserve integration for real local IO.
2. [MUST] Split runner transcript persistence, smoke import layering, GitPython requirements, and
   external-artifact validation into integration/contract homes.
3. [MUST] Preserve real-question-set behavior + add a deterministic offline e2e; fully specify the
   DataFrame golden and stable key.
4. [MUST] Correct every `Path(__file__).parents[...]` and dispersed glob affected by new depths.
5. [MUST] Deduplicate against root-level shared-model-run and deployment tests; revise "zero
   coverage".
6. [MUST] Audit and prune/loosen private-signature, private-symbol-absence, and source-string guards
   under AGENTS.md.
7. [MUST] Add both worker and manager to in-process and cold-subprocess offline-import coverage.
8. [MUST] Update `src/tests/README.md`, add required `__init__.py` files, include committed golden
   artifacts in deliverables.
