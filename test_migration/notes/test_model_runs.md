# test_model_runs.py  →  test_fb_model_runs.py

- **From:** `src/tests/llm_forecaster/test_model_runs.py`
- **To:** `src/tests/unit/llm_forecaster/test_fb_model_runs.py` (renamed to match source `fb_model_runs.py`)
- **Level/technique:** unit — registry lookups + `utils.llm` call-arg assertions + provider-key config (mocked).
- **Kept (behavioral):** shared-run selection, `get_response` call args, slug uniqueness, options-by-run, provider max-workers plan, `configure_and_validate_provider_keys`, lookup-raises.
- **Dropped (dedup):** `test_forecastbench_does_not_declare_local_model_runs` — duplicated (weaker) by the repo-wide AST guard in `contract/test_shared_llm_model_runs.py`.
- **Pruned (impl-detail, AGENTS.md):** `test_forecastbench_selected_model_run_indexes_use_prefixed_names` (hasattr-absence), `test_forecastbench_model_runs_do_not_declare_local_api_key_config` (source-string), and the `inspect.getsource` source-string asserts inside `test_options_are_declared_...` (kept its option-value asserts).
- **Relocated → `contract/`:** `test_forecastbench_model_run_imports_are_top_level` + `test_llm_forecaster_files_do_not_use_future_annotations` → `contract/test_llm_forecaster_conventions.py`; `test_provider_max_workers_covers_all_shared_providers` → `contract/test_shared_llm_model_runs.py`.
