# test_output.py

- **From:** `src/tests/llm_forecaster/test_output.py`
- **To:** `src/tests/unit/llm_forecaster/test_output.py`
- **Level/technique:** unit — pure filename/blob/`forecast_file_data` builders.
- **Processing:** moved; behavioral filename/data-shape assertions kept.
- **Pruned:** `test_output_module_builds_data_but_does_not_write_files` (source-string `"write_text"/"open("` scan) — its intent (output builds data, doesn't persist) is covered by every return-value test; persistence lives in `_llm_forecaster_io`.
