# test_runner.py  (split)

- **From:** `src/tests/llm_forecaster/test_runner.py`
- **To:** `src/tests/unit/llm_forecaster/test_runner.py` (core forecasting) + `src/tests/unit/llm_forecaster/test_model_run_transcripts.py` (pure `LLMCallTranscript` file tests, extracted per push-back #2 — transcripts write to `tmp_path`, an established unit technique here).
- **Level/technique:** unit — mock-the-boundary (`FakeRun.get_response`, monkeypatch `runner.parsing.parse_*`), threaded concurrency, tmp_path transcripts.
- **Kept (behavioral):** dataset/market forecasting, concurrency+ordering, extract-on-unparseable, skip-vs-fail-fast, variant/dataset sharing, progress logging, sorting, run_model persistence guarantees, transcript file contents.
- **Extracted:** `test_llm_call_transcript_writes_local_markdown_and_jsonl_files`, `test_llm_call_transcript_requires_question_url` → `test_model_run_transcripts.py`.
- **Pruned (impl-detail):** `test_runner_helpers_do_not_force_keyword_only_arguments`, `test_runner_helper_calls_pass_arguments_by_name`, `test_run_model_does_not_expose_timing_recorder_argument`, `test_runner_does_not_expose_final_forecast_file_persistence_helpers`, `test_llm_call_transcript_owns_file_write_helpers`, `test_model_run_transcripts_does_not_expose_upload_target_builder`, and the three `not hasattr(runner,"_render_*")` asserts inside `test_prompt_rendering_helpers_are_not_cached_by_question_phase` (kept its render behavior).
- **Result:** test_runner 37 passed; test_model_run_transcripts 2 passed.
