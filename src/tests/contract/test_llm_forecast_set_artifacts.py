"""External-artifact contract: published ForecastBench-LLM forecast sets map to known identities.

A system-wide data audit (not a unit test): every processed ForecastBench-LLM forecast file in the
sibling ``forecastbench-processed-forecast-sets`` checkout must normalize to a shared model-run key
and a supported forecast-variant key. Skipped when that checkout is absent (e.g. CI), so it never
blocks the offline suite.
"""

import json
from pathlib import Path

import pytest

# src/tests/contract/ -> repo root is three parents up.
ROOT = Path(__file__).resolve().parents[3]


def test_processed_forecastbench_llm_files_have_shared_model_run_keys():
    processed_forecast_sets = ROOT.parent / "forecastbench-processed-forecast-sets"
    if not processed_forecast_sets.exists():
        pytest.skip("Processed ForecastBench forecast sets are not checked out.")

    from utils.llm import model_runs as shared_model_runs

    from leaderboard import llm_identities
    from llm_forecaster import forecast_variants

    missing_mappings = []
    forecastbench_llm_files = 0
    for path in sorted(processed_forecast_sets.rglob("*.json")):
        data = json.loads(path.read_text())
        if data.get("organization") != "ForecastBench":
            continue
        if data.get("model_organization") == "ForecastBench":
            continue

        forecastbench_llm_files += 1
        identity = {
            "organization": data.get("organization"),
            "model": data.get("model"),
            "model_organization": data.get("model_organization"),
        }
        normalized = llm_identities.normalize_llm_identity(identity)
        model_run_key = normalized["model_run_key"]
        forecast_variant_key = normalized["forecast_variant_key"]
        if model_run_key not in shared_model_runs.MODEL_RUNS_BY_KEY:
            missing_mappings.append(
                f"{path}: {data.get('model_organization')} / {data.get('model')} "
                f"-> {model_run_key}"
            )
        if forecast_variant_key not in forecast_variants.SUPPORTED_FORECAST_VARIANT_KEYS:
            missing_mappings.append(
                f"{path}: {data.get('model_organization')} / {data.get('model')} "
                f"-> {forecast_variant_key}"
            )

    assert forecastbench_llm_files > 0
    assert missing_mappings == []
