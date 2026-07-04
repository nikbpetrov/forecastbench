# test_cloud_run.py  (root file)

- **From:** `src/tests/test_cloud_run.py`
- **To:** `src/tests/unit/test_cloud_run.py`
- **Level/technique:** unit — `helpers.cloud_run.block_and_check_job_result` with `google.cloud.run_v2` + `helpers.slack` stubbed at import.
- **Kept (behavioral):** the SystemExit + slack-message assertions; the `import_cloud_run_with_stubs` fixture.
- **Pruned:** `test_cloud_run_stub_import_leaves_no_parent_package_attribute` + `test_cloud_run_fixture_replaces_stale_parent_package_attributes` (both test test-fixture scaffolding) and the two fixtures supporting only the second.
