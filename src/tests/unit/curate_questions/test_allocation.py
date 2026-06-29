"""Unit tests for question-set allocation + stratification math (pure, deterministic).

``allocate_evenly`` is the core: spread N picks across keys as evenly as availability allows, and
**fail loudly** if it can't hit N exactly. The bin helpers map a market's value/horizon to a
stratum (or ``"unknown"``). All pure — no IO, no RNG.
"""

import pandas as pd
import pytest

from curate_questions.create_question_set.main import (
    allocate_across_categories,
    allocate_across_sources,
    allocate_evenly,
    get_market_value_bin,
    get_time_horizon_bin,
)


class TestAllocateEvenly:
    def test_even_split_when_ample(self):
        out = allocate_evenly({"a": 50, "b": 50, "c": 50}, 30)
        assert out == {"a": 10, "b": 10, "c": 10}
        assert sum(out.values()) == 30

    def test_caps_at_availability_and_redistributes(self):
        # 'a' can only supply 2; the remainder must spill to 'b' so the total still hits n.
        out = allocate_evenly({"a": 2, "b": 50}, 20)
        assert out["a"] == 2
        assert sum(out.values()) == 20
        assert all(out[k] <= avail for k, avail in {"a": 2, "b": 50}.items())

    def test_exact_total_passthrough(self):
        # sum(available) == n -> return availability unchanged.
        assert allocate_evenly({"a": 10, "b": 10}, 20) == {"a": 10, "b": 10}

    def test_over_request_raises(self):
        # Asking for more than is available can't be allocated evenly -> fail loudly, never silently
        # under-deliver.
        with pytest.raises(ValueError, match="allocate"):
            allocate_evenly({"a": 1, "b": 1}, 10)


def test_allocate_across_categories_is_even_and_sums():
    dfq = pd.DataFrame({"category": ["x"] * 10 + ["y"] * 10 + ["z"] * 10})
    out = allocate_across_categories(9, dfq)
    assert sum(out.values()) == 9
    assert out == {"x": 3, "y": 3, "z": 3}


def test_allocate_across_sources_annotates_and_balances():
    questions = {
        "fred": {"num_questions_available": 100},
        "manifold": {"num_questions_available": 100},
    }
    out = allocate_across_sources(questions, 40)
    assert out["fred"]["num_questions_to_sample"] == 20
    assert out["manifold"]["num_questions_to_sample"] == 20
    # deepcopy: the caller's dict is untouched.
    assert "num_questions_to_sample" not in questions["fred"]


class TestBinning:
    @pytest.mark.parametrize("value", ["N/A", None, "not-a-number"])
    def test_market_value_unknown_inputs(self, value):
        assert get_market_value_bin(value) == "unknown"

    def test_market_value_known_input_lands_in_a_bin(self):
        # 0.5 is a real probability -> some defined stratum, never "unknown".
        assert get_market_value_bin(0.5) != "unknown"

    @pytest.mark.parametrize("value", ["N/A", None, "not-a-date"])
    def test_time_horizon_unknown_inputs(self, value):
        assert get_time_horizon_bin(value) == "unknown"
