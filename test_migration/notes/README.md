# Per-file disposition notes

One note per original test file migrated (3 flat dirs + 6 clean-mapping root files). Each records
where the file went and how it was processed (moves, prunes, relocations, path fixes). See
`../PLAN.md` for the overall design and the Codex-review trail.

- `llm_forecaster/`: test_forecast_variants, test_model_runs (→test_fb_model_runs), test_output,
  test_parsing, test_prompts, test_question_set, test_runner (split), test_real_question_set_forecast
  (→e2e), test_smoke_test, test_orchestration_boundary (→contract); plus `smoke_test` (tooling move).
- `orchestration/`: test_llm_forecaster_io, test_forecast_file_io, test_question_set_io,
  test_llm_forecaster_worker, test_llm_forecaster_manager.
- `leaderboard/`: test_llm_identities, test_llm_identity_release_dates.
- root files: test_run_mode, test_cloud_run, test_model_request_params, test_shared_llm_model_runs,
  test_runtime_requirements, test_constants (DROPPED).
