# test_real_question_set_forecast.py  →  e2e

- **From:** `src/tests/llm_forecaster/test_real_question_set_forecast.py` (was `@pytest.mark.live`)
- **To:** `src/tests/e2e/test_llm_forecaster_pipeline.py`
- **Level/technique:** e2e — question set → `runner.run_model` (LLM boundary mocked) → `_llm_forecaster_io` writes the forecast set; anchors + `check_golden`.
- **Processing:** split into TWO tests (Codex MUST-3):
  1. **offline** `test_llm_forecaster_pipeline_offline_writes_forecast_set` — builds a `QuestionSet` from the **real published 14-key record shape** (captured from a live `*-llm.json`), fixed `FixedRun`, deterministic `get_response`; keeps all schema/row/marker anchors; adds a golden `src/tests/golden/e2e_llm_forecaster_forecast_set.csv` (key `variant/source/id/resolution_date`, `rtol=0`).
  2. **`@live`** `test_llm_forecaster_pipeline_accepts_real_published_question_set` — fetches the actual `2026-05-24-llm.json` and asserts the runner accepts it (drift detection). Deselected by default.
- **Why:** the live version only ever *fetched* the question set (never called a provider); converting to offline restores determinism + a golden while the `@live` companion preserves the real-record-shape assertion.
