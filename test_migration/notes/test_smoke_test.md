# test_smoke_test.py

- **From:** `src/tests/llm_forecaster/test_smoke_test.py`
- **To:** `src/tests/unit/llm_forecaster/test_smoke_test.py`
- **Level/technique:** unit — fakes for runner/io; CLI selection + exit-code + orchestration logic.
- **Processing:** import retargeted `from src.tests.llm_forecaster.smoke_test import smoke_test` → `from llm_forecaster import smoke_test` (tooling relocated — see `smoke_test.md`). Removed the unused `sys`/`os`/`subprocess` imports.
- **Relocated → `contract/`:** the subprocess lazy-import assertion `test_module_import_does_not_require_orchestration_io` → `contract/test_offline_imports.py::test_smoke_test_tooling_imports_without_orchestration_io` (retargeted to `llm_forecaster.smoke_test`).
