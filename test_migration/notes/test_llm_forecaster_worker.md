# test_llm_forecaster_worker.py

- **From:** `src/tests/orchestration/test_llm_forecaster_worker.py`
- **To:** `src/tests/unit/orchestration/test_llm_forecaster_worker.py` (new package + `__init__.py`)
- **Level/technique:** unit — Cloud Run worker orchestration with ALL boundaries mocked (`runner.iter_model_forecasts`, `_io`, provider keys). Placed at unit (Codex MUST-1): no real IO boundary is crossed; integration is reserved for real-local-IO. (The README-deferred item is the `nightly_update_workflow` DAG, not this entrypoint.)
- **Kept (behavioral):** env parsing (`parse_env_vars`), test-mode question limiting, prod no-limit, per-variant upload-before-failure, transcript-upload failure logging.
- **Relocated → `contract/`:** `test_worker_deploy_stages_runtime_requirements_and_shared_code` → `contract/test_deploy_staging.py` (job-specific asserts; generic asserts dropped, covered by `test_runtime_requirements.py`). Removed now-unused `subprocess`/`ROOT`/`UTILS_PIN`.
