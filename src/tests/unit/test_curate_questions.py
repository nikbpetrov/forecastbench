"""Unit tests for question-set sampling determinism.

Question-set creation samples questions randomly; with an injected RNG the result is reproducible,
which is what makes a deterministic question-set test (or e2e) possible. Only the human-sample
path is seeded so far (the stratified/LLM bin+category chain is a documented follow-up).
"""

import random

import pandas as pd

from curate_questions.create_question_set.main import human_sample_questions
from tests.factories import make_question_df


def _values(n=20):
    return {"dfq": make_question_df([{"id": f"q{i}", "source": "fred"} for i in range(n)])}


def test_human_sample_is_deterministic_with_seeded_rng():
    a = human_sample_questions(_values(), 5, rng=random.Random(0))
    b = human_sample_questions(_values(), 5, rng=random.Random(0))
    pd.testing.assert_frame_equal(a, b)


def test_human_sample_respects_count_and_membership():
    out = human_sample_questions(_values(), 5, rng=random.Random(1))
    assert len(out) == 5
    assert set(out["id"]) <= {f"q{i}" for i in range(20)}


def test_human_sample_caps_at_available():
    out = human_sample_questions(_values(n=3), 10, rng=random.Random(2))
    assert len(out) == 3  # min(n_single, available)
