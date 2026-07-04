# test_shared_llm_model_runs.py  (root file)  →  contract

- **From:** `src/tests/test_shared_llm_model_runs.py`
- **To:** `src/tests/contract/test_shared_llm_model_runs.py`
- **Level/technique:** contract — repo-wide AST anti-drift (no local `ModelRun`/`*_MODEL_RUNS` declarations) + selected-shared-run behavior.
- **Processing:** `ROOT` depth `parents[2]`→`parents[3]`; `ALLOWLIST` self-path updated to the `contract/` location; dropped the `Path(fb_model_runs.__file__).name` assert (Codex MUST-2).
- **Augmented (Codex MUST-4):** received the two relocated registry-coverage tests — `test_provider_max_workers_covers_all_shared_providers` (from `test_model_runs`) and `test_model_release_dates_include_canonical_active_llm_model_keys` (from `test_llm_identity_release_dates`).
