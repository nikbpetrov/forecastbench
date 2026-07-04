# test_forecast_variants.py

- **From:** `src/tests/llm_forecaster/test_forecast_variants.py`
- **To:** `src/tests/unit/llm_forecaster/test_forecast_variants.py`
- **Level/technique:** unit — pure registry/variant logic (no IO).
- **Processing:** moved verbatim. All behavioral (variant registry stability, active-variant set, dataset-sharing groups, context partitions, `get_variant`/`get_known_variant`).
- **Pruned:** none required (the two `not hasattr(ZERO_SHOT,"model_suffix")` asserts were left in as harmless).
