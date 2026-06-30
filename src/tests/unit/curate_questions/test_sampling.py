"""Unit tests for the curate selection path: validity/freeze filters + seeded sampling.

``drop_invalid_questions`` is the seam where the ``metadata`` job's verdict actually takes effect
(invalid questions never reach a question set). The human + LLM samplers are seedable via
``random_state``, which is what makes a deterministic question-set e2e (and golden) possible.
"""

from datetime import datetime
from unittest.mock import patch

import numpy as np
import pandas as pd

from curate_questions.create_question_set.main import (
    drop_invalid_questions,
    drop_missing_freeze_datetime,
    drop_questions_that_resolve_too_soon,
    human_sample_questions,
    llm_sample_questions,
    market_resolves_before_forecast_due_date,
)
from helpers import question_curation
from tests.factories import make_question_df


class TestDropInvalidQuestions:
    def test_keeps_only_valid_and_drops_the_flag_column(self):
        dfq = pd.DataFrame(
            [
                {"id": "q1", "source": "manifold", "question": "a"},
                {"id": "q2", "source": "manifold", "question": "b"},
            ]
        )
        dfmeta = pd.DataFrame(
            [
                {"id": "q1", "source": "manifold", "valid_question": True},
                {"id": "q2", "source": "manifold", "valid_question": False},
            ]
        )
        out = drop_invalid_questions(dfq, dfmeta)
        assert out["id"].tolist() == ["q1"]
        assert "valid_question" not in out.columns

    def test_empty_metadata_passes_through(self):
        dfq = pd.DataFrame([{"id": "q1", "source": "manifold"}])
        out = drop_invalid_questions(dfq, pd.DataFrame())
        pd.testing.assert_frame_equal(out, dfq)

    def test_joins_on_both_id_and_source(self):
        # Same id across two sources with opposite validity: the join must key on (id, source),
        # so only the valid (dup, manifold) row survives — a join on id alone would not.
        dfq = pd.DataFrame([{"id": "dup", "source": "manifold"}, {"id": "dup", "source": "fred"}])
        dfmeta = pd.DataFrame(
            [
                {"id": "dup", "source": "manifold", "valid_question": True},
                {"id": "dup", "source": "fred", "valid_question": False},
            ]
        )
        out = drop_invalid_questions(dfq, dfmeta)
        assert out[["id", "source"]].to_dict("records") == [{"id": "dup", "source": "manifold"}]


def test_drop_missing_freeze_datetime():
    dfq = pd.DataFrame(
        {
            "id": ["a", "b", "c", "d"],
            "freeze_datetime_value": ["0.5", "N/A", "nan", None],
        }
    )
    out = drop_missing_freeze_datetime(dfq)
    assert out["id"].tolist() == ["a"]


class TestResolveTooSoonFilter:
    """The market resolve-too-soon filter + its date math (no negative case lives in the e2e)."""

    # all_forecasts_due = FREEZE_DATETIME + FREEZE_WINDOW_IN_DAYS, at 23:59:59 → 2025-01-11 EOD.
    _FREEZE = patch.object(question_curation, "FREEZE_DATETIME", datetime(2025, 1, 1))
    _WINDOW = patch.object(question_curation, "FREEZE_WINDOW_IN_DAYS", 10)

    def test_market_resolves_before_due_date_boundary(self):
        with self._FREEZE, self._WINDOW:
            # Closes before all-forecasts-due → too soon.
            assert market_resolves_before_forecast_due_date(datetime(2025, 1, 5)) is True
            # Same calendar day but before 23:59:59 → still too soon.
            assert market_resolves_before_forecast_due_date(datetime(2025, 1, 11, 12)) is True
            # Comfortably after → not too soon.
            assert market_resolves_before_forecast_due_date(datetime(2025, 1, 20)) is False
            assert market_resolves_before_forecast_due_date(datetime(2025, 3, 12)) is False

    def test_drop_markets_that_close_too_soon(self):
        dfq = pd.DataFrame(
            {
                "id": ["soon", "ok"],
                "market_info_close_datetime": ["2025-01-05T00:00:00", "2025-03-12T00:00:00"],
            }
        )
        with self._FREEZE, self._WINDOW:
            out = drop_questions_that_resolve_too_soon("manifold", dfq)
        assert out["id"].tolist() == ["ok"]  # the too-soon market is dropped

    def test_drop_data_questions_with_empty_or_na_horizons(self):
        dfq = pd.DataFrame(
            {
                "id": ["keep", "empty", "na"],
                "forecast_horizons": [[7, 30], [], "N/A"],
            }
        )
        out = drop_questions_that_resolve_too_soon("fred", dfq)
        assert out["id"].tolist() == ["keep"]  # empty / "N/A" horizons dropped


class TestHumanSampleQuestions:
    @staticmethod
    def _values(n: int = 20) -> dict:
        return {"dfq": make_question_df([{"id": f"q{i}", "source": "fred"} for i in range(n)])}

    def test_deterministic_with_seeded_rng(self):
        a = human_sample_questions(self._values(), 5, random_state=0)
        b = human_sample_questions(self._values(), 5, random_state=0)
        pd.testing.assert_frame_equal(a, b)

    def test_respects_count_and_membership(self):
        out = human_sample_questions(self._values(), 5, random_state=1)
        assert len(out) == 5
        assert set(out["id"]) <= {f"q{i}" for i in range(20)}

    def test_caps_at_available(self):
        out = human_sample_questions(self._values(n=3), 10, random_state=2)
        assert len(out) == 3  # min(n_single, available)


class TestLLMDataSamplingIsSeeded:
    """The data-source LLM path (category-even ``.sample``) is reproducible under a seed."""

    @staticmethod
    def _values(n: int = 20) -> dict:
        rows = [
            {"id": f"q{i}", "source": "fred", "category": "Economics & Business"} for i in range(n)
        ]
        return {"dfq": make_question_df(rows)}

    def test_same_seed_same_sample(self):
        a = llm_sample_questions(self._values(), 5, random_state=np.random.RandomState(0))
        b = llm_sample_questions(self._values(), 5, random_state=np.random.RandomState(0))
        assert len(a) == 5
        pd.testing.assert_frame_equal(
            a.sort_values("id").reset_index(drop=True),
            b.sort_values("id").reset_index(drop=True),
        )

    def test_different_seed_can_differ(self):
        a = llm_sample_questions(self._values(), 5, random_state=np.random.RandomState(0))
        c = llm_sample_questions(self._values(), 5, random_state=np.random.RandomState(99))
        # Not a hard guarantee, but with 20→5 the odds of an identical id-set across two seeds are
        # negligible; this pins that the seed actually drives selection.
        assert set(a["id"]) != set(c["id"])
