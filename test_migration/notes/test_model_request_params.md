# test_model_request_params.py  (root file)

- **From:** `src/tests/test_model_request_params.py`
- **To:** `src/tests/unit/metadata/test_model_request_params.py`
- **Level/technique:** unit — `helpers.metadata_llm` model-request routing (shared ModelRun + provider config + OpenAI safety id).
- **Kept (behavioral):** `test_metadata_model_response_routes_through_shared_model_run`, `..._configures_model_run_provider_before_request`, `test_project_openai_safety_identifier_comes_from_secret_manager`, helper `import_metadata_llm_without_secret_fetch`.
- **Pruned (source-string):** `test_metadata_callers_use_metadata_model_response_helper`, `test_metadata_llm_no_longer_contains_legacy_provider_routing`, `test_constants_do_not_expose_legacy_llm_model_maps`. After pruning, `ROOT`/`Path`/`constants`/`LEGACY_*` were unused and removed (so no `parents[...]` fix was needed).
