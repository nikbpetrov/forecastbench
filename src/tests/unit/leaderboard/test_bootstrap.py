"""Unit tests for the seedable bootstrap resampler.

The leaderboard's confidence intervals come from ``generate_simulated_leaderboards``, which runs
bootstrap replicates under ``joblib``/loky subprocesses. Reproducibility therefore needs a
*per-replicate* seed (a parent-process seed would not reach the children). These tests pin the
extracted, seedable resampling primitive that makes that determinism possible.
"""

import numpy as np
import pandas as pd

from leaderboard.main import _question_level_bootstrap


def _df():
    return pd.DataFrame({"question_pk": [f"q{i}" for i in range(20)], "v": list(range(20))})


def test_same_seed_is_deterministic():
    a = _question_level_bootstrap(_df(), random_state=np.random.RandomState(42))
    b = _question_level_bootstrap(_df(), random_state=np.random.RandomState(42))
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_preserves_count_and_membership():
    out = _question_level_bootstrap(_df(), random_state=np.random.RandomState(1))
    assert len(out) == 20  # frac=1 resample
    base_pks = {pk.split("_sim_id_")[0] for pk in out["question_pk"]}
    assert base_pks <= {f"q{i}" for i in range(20)}


def test_resampled_question_pks_are_unique_per_draw():
    out = _question_level_bootstrap(_df(), random_state=np.random.RandomState(7))
    # The "_sim_id_N" suffix guarantees duplicate draws get distinct keys for the FE model.
    assert out["question_pk"].is_unique
