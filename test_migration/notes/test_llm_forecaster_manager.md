# test_llm_forecaster_manager.py

- **From:** `src/tests/orchestration/test_llm_forecaster_manager.py`
- **To:** `src/tests/unit/orchestration/test_llm_forecaster_manager.py`
- **Level/technique:** unit — Cloud Run manager orchestration with `helpers.cloud_run` stubbed at import + all boundaries mocked (Codex MUST-1).
- **Kept (behavioral):** env-default run mode, `run_manager` wiring (task count, worker call, block-and-check), the `import_manager_with_cloud_run_stub` fixture.
- **Pruned:** `test_manager_fixture_replaces_stale_parent_cloud_run_attribute` (tests test-fixture scaffolding, not production — Codex §5) + the two fixtures that supported only it.
- **Relocated → `contract/`:** `test_manager_deploy_stages_runtime_requirements_and_shared_code` → `contract/test_deploy_staging.py` (unique job asserts preserved incl. `TEST_OR_PROD`, exact job name; generic asserts dropped). Removed now-unused `subprocess`/`Path`/`ROOT`/`UTILS_PIN`.
