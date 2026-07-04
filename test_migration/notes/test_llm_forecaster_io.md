# test_llm_forecaster_io.py

- **From:** `src/tests/orchestration/test_llm_forecaster_io.py`
- **To:** `src/tests/integration/test_llm_forecaster_io.py`
- **Level/technique:** integration — real `_llm_forecaster_io` code, GCS mocked at the `gcp.storage` boundary; final files written to a temp tree ("mock at the boundary, real code between").
- **Processing:** moved verbatim (16 IO tests across the 3 IO files pass). Behavioral: `write_final_forecast_file` schema round-trip + overwrite + raw-record rejection, `final_forecast_set_destination_blob_names`, transcript upload seam.
