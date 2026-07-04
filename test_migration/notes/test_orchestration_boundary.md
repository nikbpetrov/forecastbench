# test_orchestration_boundary.py  →  contract

- **From:** `src/tests/llm_forecaster/test_orchestration_boundary.py`
- **To:** `src/tests/contract/test_llm_forecaster_conventions.py`
- **Level/technique:** contract — architectural layering (AST): the core `llm_forecaster` modules (`runner`, `question_set`, `model_run_transcripts`) must not import `orchestration`.
- **Processing:** the import-layering test moved here (Codex MUST-3: architectural AST → contract). The same file also now hosts the two convention guards relocated from `test_model_runs.py` (top-level-import policy; no-`from __future__ import annotations`, with its glob repointed to `src/llm_forecaster/**` + `unit/llm_forecaster/**`).
