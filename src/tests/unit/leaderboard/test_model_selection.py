"""Unit tests for the baseline-vs-tournament model-selection filters (pure, no IO).

These two filters decide which models appear on each *published* leaderboard — the single most
product-defining branch in ``leaderboard/main.py``. Their logic is subtle string/regex matching, so
a renamed dummy model, a changed variant suffix, or a regex typo would silently add or drop whole
models from the public leaderboard. These tests pin the exact surviving model set per leaderboard.
"""

import pandas as pd

from helpers import constants
from leaderboard.main import (
    FORECASTBENCH_CREATED_DUMMY_MODEL_NAMES,
    filter_to_baseline_leaderboard_models,
    filter_to_tournament_leaderboard_models,
)

_FB = constants.BENCHMARK_NAME


def _row(model: str, organization: str = _FB, model_organization: str = _FB) -> dict:
    return {"organization": organization, "model": model, "model_organization": model_organization}


# A representative mix: external submission, FB dummy baselines, and FB-LLM variants.
_FRAME = pd.DataFrame(
    [
        _row("GPT-4o", organization="ExternalOrg", model_organization="ExternalOrg"),  # external
        _row("Naive Forecaster"),  # FB dummy (model_org == FB)
        _row("Always 0.5"),  # FB dummy
        _row("Superforecaster median forecast"),  # FB "dummy" (human, in dummy-name set)
        _row("GPT-4 (zero shot)", model_organization="OpenAI"),  # FB-LLM baseline variant
        _row("Claude (scratchpad)", model_organization="Anthropic"),  # FB-LLM baseline variant
        _row("GPT-4 with news", model_organization="OpenAI"),  # FB-LLM tournament variant
        _row("GPT-4 with freeze values", model_organization="OpenAI"),  # FB-LLM tournament variant
        _row(
            "GPT-4 (plain)", model_organization="OpenAI"
        ),  # FB-LLM, neither variant → dropped both
    ]
)


def test_baseline_keeps_fb_dummies_and_zero_shot_scratchpad_only():
    out = set(filter_to_baseline_leaderboard_models(_FRAME)["model"])
    assert out == {
        "Naive Forecaster",
        "Always 0.5",
        "Superforecaster median forecast",
        "GPT-4 (zero shot)",
        "Claude (scratchpad)",
    }
    # The external submission and the tournament/plain variants are excluded from baseline.
    assert "GPT-4o" not in out
    assert "GPT-4 with news" not in out and "GPT-4 (plain)" not in out


def test_tournament_keeps_externals_dummies_and_tournament_variants_only():
    out = set(filter_to_tournament_leaderboard_models(_FRAME)["model"])
    assert out == {
        "GPT-4o",  # external submission
        "Naive Forecaster",
        "Always 0.5",
        "Superforecaster median forecast",
        "GPT-4 with news",
        "GPT-4 with freeze values",
    }
    # Baseline-only FB-LLM variants and the plain variant are excluded from tournament.
    assert "GPT-4 (zero shot)" not in out and "GPT-4 (scratchpad)" not in out
    assert "GPT-4 (plain)" not in out


def test_baseline_excludes_fb_llm_dummy_named_models_that_are_not_benchmark_org():
    # A model whose model_organization is NOT the benchmark is an FB-LLM submission, so it only
    # qualifies for baseline via the (zero shot)/(scratchpad) suffix — never via the dummy-name set,
    # even if its name happens to collide with one.
    frame = pd.DataFrame([_row("Naive Forecaster", model_organization="OpenAI")])
    assert filter_to_baseline_leaderboard_models(frame).empty


def test_filters_are_disjoint_on_the_baseline_only_and_tournament_only_variants():
    # Sanity: the (zero shot)/(scratchpad) variants are baseline-only; the "with news"/"with freeze"
    # variants are tournament-only. A regex/keyword drift would collapse this separation.
    baseline = set(filter_to_baseline_leaderboard_models(_FRAME)["model"])
    tournament = set(filter_to_tournament_leaderboard_models(_FRAME)["model"])
    assert {"GPT-4 (zero shot)", "Claude (scratchpad)"} <= baseline
    assert {"GPT-4 (zero shot)", "Claude (scratchpad)"}.isdisjoint(tournament)
    assert {"GPT-4 with news", "GPT-4 with freeze values"} <= tournament
    assert {"GPT-4 with news", "GPT-4 with freeze values"}.isdisjoint(baseline)


def test_dummy_name_set_is_the_contract_these_filters_depend_on():
    # If a dummy model is renamed in the constant without updating forecast files (or vice-versa),
    # it silently vanishes from BOTH leaderboards. Pin the membership the filters rely on.
    assert {"Naive Forecaster", "Imputed Forecaster", "Always 0.5"} <= (
        FORECASTBENCH_CREATED_DUMMY_MODEL_NAMES
    )
