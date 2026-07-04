# test_llm_identity_release_dates.py

- **From:** `src/tests/leaderboard/test_llm_identity_release_dates.py`
- **To:** `src/tests/unit/leaderboard/test_llm_identity_release_dates.py`
- **Level/technique:** unit — model-release-date joins via `utils.llm.model_registry` + `main.get_model_release_date_info`/`score_models`.
- **Processing:** replaced the cross-test import (`from tests.leaderboard.test_llm_identities import _import_leaderboard_main`) with a local trivial `_import_leaderboard_main()`; fixed `ROOT` depth `parents[3]`→`parents[4]`.
- **Pruned:** the `assert not hasattr(llm_identities,"add_model_key")` line inside `test_model_key_is_returned_by_normalized_identity_not_added_later` (kept the behavioral `model_key` assert).
- **Relocated → `contract/`:** `test_processed_forecastbench_llm_files_have_shared_model_run_keys` (external-artifact data audit) → `contract/test_llm_forecast_set_artifacts.py` (skips when the data checkout is absent — the suite's 1 conditional skip).
