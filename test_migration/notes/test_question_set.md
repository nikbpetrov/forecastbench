# test_question_set.py

- **From:** `src/tests/llm_forecaster/test_question_set.py`
- **To:** `src/tests/unit/llm_forecaster/test_question_set.py`
- **Level/technique:** unit — pure `split_questions` / `limit_questions_for_test_mode` / `from_question_set_json`.
- **Processing:** moved; behavioral split/limit/from-json kept.
- **Pruned:** `test_question_set_module_name_matches_domain` (`__file__` assert) and `test_question_set_module_does_not_load_through_boundary_reader` (hasattr-absence).
