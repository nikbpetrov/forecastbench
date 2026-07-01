"""Baseline-vs-tournament model selection — SKIPPED after main's leaderboard rewrite.

These tests pinned the *pre-rewrite* selection logic, where
``filter_to_baseline_leaderboard_models`` / ``filter_to_tournament_leaderboard_models`` classified
models by name/regex against a ``FORECASTBENCH_CREATED_DUMMY_MODEL_NAMES`` constant. ``main``'s
"rewrite LLM forecaster" replaced that with precomputed boolean columns (``baseline_model`` /
``tournament_model``, set in ``leaderboard.main`` around the model-info block and in
``llm_identities`` / ``model_runs``); the filters are now trivial ``df[df["baseline_model"]]``
selections and the constant is gone, so the original name-set assertions no longer map onto any
function. Re-author against the new classification site if this coverage is still wanted.

See REBASE_LOG.md ("test_model_selection") for the rationale.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="model-selection logic rewritten on main (name-regex + FORECASTBENCH_CREATED_DUMMY_"
    "MODEL_NAMES -> precomputed baseline_model/tournament_model columns); pre-rewrite assertions "
    "need re-authoring against the new classification. See REBASE_LOG.md."
)


def test_model_selection_filters_need_reauthoring_after_main_rewrite():
    """Placeholder marking obsolete coverage (see module docstring + REBASE_LOG.md)."""
