# test_llm_identities.py

- **From:** `src/tests/leaderboard/test_llm_identities.py`
- **To:** `src/tests/unit/leaderboard/test_llm_identities.py`
- **Level/technique:** unit — `leaderboard.llm_identities.normalize_llm_identity` + `ForecastBenchLLMIdentity` + `get_df_info`/2FE identity classification (imports `leaderboard.main` directly).
- **Processing:** dropped the heavy `_patched_import_environment` stub+chdir scaffold; `_import_leaderboard_main()` reduced to a trivial `from leaderboard import main` (call sites unchanged) — matches existing `unit/leaderboard/` which imports `leaderboard.main` directly (it's in the offline-import contract). Removed the leftover `importlib/os/sys/types/contextmanager/Path/ROOT` imports.
- **Pruned:** `test_model_run_identity_construction_is_inlined` (private-symbol-absence); the `assert not hasattr(identity,"model")` line inside `test_forecastbench_llm_identity_stores_model_run_object` (Codex MUST-2).
- **Relocated → `contract/`:** `test_leaderboard_deploy_stages_llm_identity_dependencies` → `contract/test_deploy_staging.py`.
- **Result:** 55 passed (with `test_llm_identity_release_dates.py`).
