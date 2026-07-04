# test_runtime_requirements.py  (root file)  →  contract

- **From:** `src/tests/test_runtime_requirements.py`
- **To:** `src/tests/contract/test_runtime_requirements.py`
- **Level/technique:** contract — cross-job deploy/runtime packaging (shared utils pin only in root runtime reqs; every deploy Makefile stages `requirements.runtime.txt`; provider deps not duplicated; root Makefile routes LLM-baseline targets to `func_llm_forecaster_{manager,worker}`; `make test` bootstraps the env).
- **Processing:** `ROOT` depth `parents[2]`→`parents[3]`. Content otherwise unchanged. This file is the canonical GENERIC deploy contract; the new `contract/test_deploy_staging.py` holds only the per-job specifics (deduped against this file).
