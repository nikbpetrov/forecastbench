# test_forecast_file_io.py

- **From:** `src/tests/orchestration/test_forecast_file_io.py`
- **To:** `src/tests/integration/test_forecast_file_io.py`
- **Level/technique:** integration — real `_io` forecast-file helpers; `gcp.storage.list/upload/file_exists` mocked; local writes to a temp tree.
- **Processing:** moved. Kept: nested-test-file exclusion, `write_forecast_file`, text helpers, bucket routing.
- **Pruned:** `test_generic_io_does_not_expose_llm_transcript_upload_helper` (private-symbol-absence).
