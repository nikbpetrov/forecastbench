# smoke_test/smoke_test.py  (operator tooling, not a pytest test)

- **From:** `src/tests/llm_forecaster/smoke_test/smoke_test.py`
- **To:** `src/llm_forecaster/smoke_test.py` (moved OUT of the tests tree into the package it drives)
- **Processing:** the module is a full-path LLM smoke-test CLI, not a test. Its invocation docstring was updated (`python -m src.tests...smoke_test` → `python -m llm_forecaster.smoke_test`, `PYTHONPATH=src`). It lazy-imports everything, so `import llm_forecaster.smoke_test` stays clean (proven by the relocated offline-import assertion). No external references needed updating (grep-confirmed).
