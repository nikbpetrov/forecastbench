"""Tests for WikipediaSource: _compare_values, _ffill_dfr, _transform_id, hash mapping, resolve."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from sources.wikipedia import QuestionType, WikipediaSource
from tests.factories import make_resolution_df

# ---------------------------------------------------------------------------
# _compare_values
# ---------------------------------------------------------------------------


class TestCompareValues:
    """Parametrized tests for WikipediaSource._compare_values."""

    @pytest.mark.parametrize(
        "question_type,res_val,due_val,expected",
        [
            # SAME
            (QuestionType.SAME, 100, 100, True),
            (QuestionType.SAME, 101, 100, False),
            (QuestionType.SAME, 99, 100, False),
            # SAME_OR_MORE
            (QuestionType.SAME_OR_MORE, 100, 100, True),
            (QuestionType.SAME_OR_MORE, 101, 100, True),
            (QuestionType.SAME_OR_MORE, 99, 100, False),
            # SAME_OR_LESS
            (QuestionType.SAME_OR_LESS, 100, 100, True),
            (QuestionType.SAME_OR_LESS, 99, 100, True),
            (QuestionType.SAME_OR_LESS, 101, 100, False),
            # MORE
            (QuestionType.MORE, 101, 100, True),
            (QuestionType.MORE, 100, 100, False),
            (QuestionType.MORE, 99, 100, False),
            # ONE_PERCENT_MORE
            (QuestionType.ONE_PERCENT_MORE, 101, 100, True),
            (QuestionType.ONE_PERCENT_MORE, 100.99, 100, False),
            (QuestionType.ONE_PERCENT_MORE, 100, 100, False),
            (QuestionType.ONE_PERCENT_MORE, 1010, 1000, True),
            (QuestionType.ONE_PERCENT_MORE, 1009.99, 1000, False),
        ],
    )
    def test_compare_values(self, question_type, res_val, due_val, expected):
        result = WikipediaSource._compare_values(question_type, res_val, due_val)
        assert result == expected

    def test_invalid_question_type_raises(self):
        with pytest.raises(ValueError, match="Invalid QuestionType"):
            WikipediaSource._compare_values("not_a_type", 100, 100)


# ---------------------------------------------------------------------------
# _transform_id
# ---------------------------------------------------------------------------


class TestTransformId:
    """Test deprecated ID mapping."""

    def test_mapped_id_returns_new_id(self):
        # First entry from _TRANSFORM_ID_MAPPING
        old_id = "d4fd9e41e71c3e5a2992b9c8b36ff655eb7265b7a46a434484f1267eabd59b92"
        new_id = "a1c131d5c2ad476fc579b30b72ea6762e3b6324b0252a57c10c890436604f44f"
        assert WikipediaSource._transform_id(old_id) == new_id

    def test_unmapped_id_returns_original(self):
        original = "not_a_mapped_id"
        assert WikipediaSource._transform_id(original) == original


# ---------------------------------------------------------------------------
# _ffill_dfr
# ---------------------------------------------------------------------------


class TestFfillDfr:
    """Test forward-fill of resolution values."""

    def test_fills_gaps_between_observations(self, freeze_today):
        freeze_today(date(2025, 1, 10))

        dfr = make_resolution_df(
            [
                {"id": "q1", "date": "2025-01-01", "value": 10},
                {"id": "q1", "date": "2025-01-05", "value": 20},
            ]
        )

        result = WikipediaSource._ffill_dfr(dfr)
        q1 = result[result["id"] == "q1"].sort_values("date")

        # Should have daily values from Jan 1 to Jan 9 (yesterday)
        assert len(q1) == 9
        # Jan 2-4 should be forward-filled with 10
        jan3_val = q1[q1["date"] == pd.Timestamp("2025-01-03")]["value"].iloc[0]
        assert jan3_val == 10
        # Jan 5 onward should be 20
        jan7_val = q1[q1["date"] == pd.Timestamp("2025-01-07")]["value"].iloc[0]
        assert jan7_val == 20

    def test_extends_to_yesterday(self, freeze_today):
        freeze_today(date(2025, 1, 10))

        dfr = make_resolution_df([{"id": "q1", "date": "2025-01-05", "value": 42}])

        result = WikipediaSource._ffill_dfr(dfr)
        q1 = result[result["id"] == "q1"]
        max_date = q1["date"].max()
        assert max_date == pd.Timestamp("2025-01-09")  # yesterday
        # All values should be 42
        assert (q1["value"] == 42).all()

    def test_multiple_ids_independent(self, freeze_today):
        freeze_today(date(2025, 1, 10))

        dfr = make_resolution_df(
            [
                {"id": "q1", "date": "2025-01-05", "value": 10},
                {"id": "q2", "date": "2025-01-07", "value": 20},
            ]
        )

        result = WikipediaSource._ffill_dfr(dfr)
        assert set(result["id"].unique()) == {"q1", "q2"}
        q1 = result[result["id"] == "q1"]
        q2 = result[result["id"] == "q2"]
        assert len(q1) == 5  # Jan 5-9
        assert len(q2) == 3  # Jan 7-9

    def test_explicit_nan_not_forward_filled(self, freeze_today):
        """Explicit NaN (off-the-charts) must be preserved, not filled over."""
        freeze_today(date(2025, 1, 10))

        dfr = make_resolution_df(
            [
                {"id": "q1", "date": "2025-01-01", "value": 10},
                {"id": "q1", "date": "2025-01-05", "value": float("nan")},
            ]
        )

        result = WikipediaSource._ffill_dfr(dfr)
        q1 = result[result["id"] == "q1"].sort_values("date")

        # Should have daily values from Jan 1 to Jan 9 (yesterday)
        assert len(q1) == 9

        # Jan 2-4 should be forward-filled with 10 (gap filling)
        for day in [2, 3, 4]:
            val = q1[q1["date"] == pd.Timestamp(f"2025-01-0{day}")]["value"].iloc[0]
            assert val == 10, f"Jan {day} should be 10"

        # Jan 5 was explicit NaN -- must NOT be filled
        jan5_val = q1[q1["date"] == pd.Timestamp("2025-01-05")]["value"].iloc[0]
        assert pd.isna(jan5_val), "Jan 5 explicit NaN should be preserved"

        # Jan 6-9 (extended to yesterday) should also be NaN
        for day in [6, 7, 8, 9]:
            val = q1[q1["date"] == pd.Timestamp(f"2025-01-0{day}")]["value"].iloc[0]
            assert pd.isna(val), f"Jan {day} should be NaN (off the charts)"


# ---------------------------------------------------------------------------
# Hash mapping
# ---------------------------------------------------------------------------


class TestWikipediaHashMapping:
    """Test hash mapping load, dump, and unhash."""

    def test_populate_hash_mapping(self):
        source = WikipediaSource()
        source.populate_hash_mapping('{"abc": {"id_root": "page1"}}')
        assert source.hash_mapping == {"abc": {"id_root": "page1"}}

    def test_load_empty_string(self):
        source = WikipediaSource()
        source.populate_hash_mapping("")
        assert source.hash_mapping == {}

    def test_dump_removes_deprecated_keys(self):
        source = WikipediaSource()
        deprecated_key = "d4fd9e41e71c3e5a2992b9c8b36ff655eb7265b7a46a434484f1267eabd59b92"
        source.hash_mapping = {
            deprecated_key: {"id_root": "old"},
            "keep_me": {"id_root": "new"},
        }
        result = source.dump_hash_mapping()
        import json

        parsed = json.loads(result)
        assert deprecated_key not in parsed
        assert "keep_me" in parsed

    def test_id_unhash_applies_transform(self):
        source = WikipediaSource()
        old_id = "d4fd9e41e71c3e5a2992b9c8b36ff655eb7265b7a46a434484f1267eabd59b92"
        new_id = "a1c131d5c2ad476fc579b30b72ea6762e3b6324b0252a57c10c890436604f44f"
        source.hash_mapping = {new_id: {"id_root": "page1"}}
        result = source._id_unhash(old_id)
        assert result == {"id_root": "page1"}

    def test_id_unhash_not_found_returns_none(self):
        source = WikipediaSource()
        source.hash_mapping = {}
        assert source._id_unhash("nonexistent") is None


# ---------------------------------------------------------------------------
# nullified_questions
# ---------------------------------------------------------------------------


class TestWikipediaNullifiedQuestions:
    """Verify nullified questions are correctly defined."""

    def test_nullified_questions_count(self):
        assert len(WikipediaSource.nullified_questions) == len(
            [entry for entry in WikipediaSource.nullified_questions]
        )
        assert len(WikipediaSource.nullified_questions) > 0

    def test_nullified_questions_are_nullified_question_instances(self):
        from _fb_types import NullifiedQuestion

        for nq in WikipediaSource.nullified_questions:
            assert isinstance(nq, NullifiedQuestion)
            assert isinstance(nq.id, str)
            assert isinstance(nq.nullification_start_date, date)


# ---------------------------------------------------------------------------
# _resolve / _resolve_single_question orchestration
# ---------------------------------------------------------------------------
#
# These tests drive the full row-by-row resolution path (mask gating, hash lookup,
# PAGES question_type dispatch, ffill, combo branch, nullification) and assert the
# exact resolved_to / resolved against a hand-computed oracle. _resolve() takes the
# already-source-filtered df and returns (df, warnings). The df is shaped like the
# ResolveReadyFrame rows that BaseSource.resolve() hands down: id, source, direction,
# forecast_due_date, resolution_date, resolved, resolved_to.
#
# id_root -> QuestionType (from helpers.wikipedia.PAGES), used as the oracle:
#   FIDE_rankings_elo_rating         -> ONE_PERCENT_MORE (res >= due * 1.01)
#   FIDE_rankings_ranking            -> SAME_OR_LESS      (res <= due)
#   List_of_world_records_in_swimming-> SAME              (res == due)
#   List_of_infectious_diseases      -> MORE              (res > due)


def _make_wiki_resolve_df(rows: list[dict]) -> pd.DataFrame:
    """Build a ResolveReadyFrame-shaped df for WikipediaSource._resolve().

    Each row dict needs ``id``, ``forecast_due_date``, ``resolution_date``; ``direction``
    defaults to ``()`` (single question). ``source`` is stamped to ``"wikipedia"`` and the
    resolution-output columns (``resolved`` / ``resolved_to``) are seeded as
    BaseSource.resolve() seeds them before delegating.

    Args:
        rows (list): Row dicts (id, forecast_due_date, resolution_date, optional direction).
    """
    df = pd.DataFrame(rows)
    if "direction" not in df.columns:
        df["direction"] = [() for _ in range(len(df))]
    df["source"] = "wikipedia"
    df["forecast_due_date"] = pd.to_datetime(df["forecast_due_date"])
    df["resolution_date"] = pd.to_datetime(df["resolution_date"])
    df["resolved"] = False
    df["resolved_to"] = np.nan
    return df


def _wiki_source(hash_mapping: dict) -> WikipediaSource:
    """Return a WikipediaSource with the given hash_mapping populated."""
    src = WikipediaSource()
    src.hash_mapping = hash_mapping
    return src


class TestWikipediaResolveSingle:
    """Exact-oracle resolution of single (non-combo) Wikipedia questions."""

    def test_one_percent_more_resolves_true(self, freeze_today):
        """ONE_PERCENT_MORE: 100 -> 102 satisfies 102 >= 100 * 1.01, so resolved_to is 1.0."""
        freeze_today(date(2025, 1, 10))  # yesterday = 2025-01-09
        src = _wiki_source(
            {"hA": {"id_root": "FIDE_rankings_elo_rating", "id_field_value": "Player A"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hA", "date": "2025-01-01", "value": 100.0},
                {"id": "hA", "date": "2025-01-05", "value": 102.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hA", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, warnings = src._resolve(df, pd.DataFrame(), dfr)

        assert warnings == []
        assert bool(out["resolved"].iloc[0]) is True
        assert out["resolved_to"].iloc[0] == 1.0

    def test_one_percent_more_resolves_false(self, freeze_today):
        """ONE_PERCENT_MORE: 100 -> 100 fails 100 >= 100 * 1.01, so resolved_to is 0.0."""
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hA": {"id_root": "FIDE_rankings_elo_rating", "id_field_value": "Player A"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hA", "date": "2025-01-01", "value": 100.0},
                {"id": "hA", "date": "2025-01-05", "value": 100.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hA", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert bool(out["resolved"].iloc[0]) is True
        assert out["resolved_to"].iloc[0] == 0.0

    def test_more_resolves_true(self, freeze_today):
        """MORE (List_of_infectious_diseases): 0 -> 1 satisfies 1 > 0, so resolved_to is 1.0."""
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hD": {"id_root": "List_of_infectious_diseases", "id_field_value": "Disease D"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hD", "date": "2025-01-01", "value": 0.0},
                {"id": "hD", "date": "2025-01-05", "value": 1.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hD", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert out["resolved_to"].iloc[0] == 1.0

    def test_more_resolves_false(self, freeze_today):
        """MORE: 1 -> 1 fails 1 > 1, so resolved_to is 0.0."""
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hD": {"id_root": "List_of_infectious_diseases", "id_field_value": "Disease D"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hD", "date": "2025-01-01", "value": 1.0},
                {"id": "hD", "date": "2025-01-05", "value": 1.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hD", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert out["resolved_to"].iloc[0] == 0.0

    def test_same_resolves_true(self, freeze_today):
        """SAME (swimming WR): 1 -> 1 satisfies 1 == 1, so resolved_to is 1.0."""
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hS": {"id_root": "List_of_world_records_in_swimming", "id_field_value": "Swimmer S"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hS", "date": "2025-01-01", "value": 1.0},
                {"id": "hS", "date": "2025-01-05", "value": 1.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hS", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert out["resolved_to"].iloc[0] == 1.0

    def test_same_resolves_false(self, freeze_today):
        """SAME: 1 -> 0 fails 0 == 1 (record lost), so resolved_to is 0.0."""
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hS": {"id_root": "List_of_world_records_in_swimming", "id_field_value": "Swimmer S"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hS", "date": "2025-01-01", "value": 1.0},
                {"id": "hS", "date": "2025-01-05", "value": 0.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hS", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert out["resolved_to"].iloc[0] == 0.0

    def test_same_or_less_resolves_true(self, freeze_today):
        """SAME_OR_LESS (FIDE ranking): rank 5 -> 3 satisfies 3 <= 5, so resolved_to is 1.0."""
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hR": {"id_root": "FIDE_rankings_ranking", "id_field_value": "Player R"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hR", "date": "2025-01-01", "value": 5.0},
                {"id": "hR", "date": "2025-01-05", "value": 3.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hR", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert out["resolved_to"].iloc[0] == 1.0

    def test_ffilled_interpolated_days_drive_comparison(self, freeze_today):
        """due/resolution dates falling on ffilled days read the carried-forward value.

        With observations only at Jan 1 (=100) and Jan 10 (=200), _ffill_dfr carries
        100 forward through Jan 9. Due date Jan 3 and resolution date Jan 8 both read the
        ffilled 100, so ONE_PERCENT_MORE (100 >= 100 * 1.01) is False -> resolved_to is 0.0.
        """
        freeze_today(date(2025, 1, 13))  # yesterday = 2025-01-12, mask admits Jan 8
        src = _wiki_source(
            {"hF": {"id_root": "FIDE_rankings_elo_rating", "id_field_value": "Player F"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hF", "date": "2025-01-01", "value": 100.0},
                {"id": "hF", "date": "2025-01-10", "value": 200.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hF", "forecast_due_date": "2025-01-03", "resolution_date": "2025-01-08"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert bool(out["resolved"].iloc[0]) is True
        assert out["resolved_to"].iloc[0] == 0.0


class TestWikipediaResolveCombo:
    """Exact-oracle resolution of combo (tuple-id) Wikipedia questions."""

    def _combo_setup(self):
        """Build a source + dfr where sub-question A resolves True and B resolves False.

        Both are ONE_PERCENT_MORE: A goes 100 -> 102 (>= 101, True); B goes 100 -> 100
        (< 101, False).
        """
        src = _wiki_source(
            {
                "cA": {"id_root": "FIDE_rankings_elo_rating", "id_field_value": "A"},
                "cB": {"id_root": "FIDE_rankings_elo_rating", "id_field_value": "B"},
            }
        )
        dfr = make_resolution_df(
            [
                {"id": "cA", "date": "2025-01-01", "value": 100.0},
                {"id": "cA", "date": "2025-01-05", "value": 102.0},  # True
                {"id": "cB", "date": "2025-01-01", "value": 100.0},
                {"id": "cB", "date": "2025-01-05", "value": 100.0},  # False
            ]
        )
        return src, dfr

    def test_combo_both_positive_direction(self, freeze_today):
        """With direction (1, 1): combo_to = True * False = 1.0 * 0.0 = 0.0."""
        freeze_today(date(2025, 1, 10))
        src, dfr = self._combo_setup()
        df = _make_wiki_resolve_df(
            [
                {
                    "id": ("cA", "cB"),
                    "direction": (1, 1),
                    "forecast_due_date": "2025-01-01",
                    "resolution_date": "2025-01-05",
                }
            ]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert bool(out["resolved"].iloc[0]) is True
        assert out["resolved_to"].iloc[0] == 0.0

    def test_combo_negated_second_direction(self, freeze_today):
        """With direction (1, -1): combo_to = True * (1 - False) = 1.0 * 1.0 = 1.0."""
        freeze_today(date(2025, 1, 10))
        src, dfr = self._combo_setup()
        df = _make_wiki_resolve_df(
            [
                {
                    "id": ("cA", "cB"),
                    "direction": (1, -1),
                    "forecast_due_date": "2025-01-01",
                    "resolution_date": "2025-01-05",
                }
            ]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert out["resolved_to"].iloc[0] == 1.0


class TestWikipediaResolveEdgeCases:
    """Mask gating, missing-due-value nullification, and unknown id_root paths."""

    def test_missing_due_date_value_nullifies_to_nan(self, freeze_today):
        """No value on/before the forecast due date -> nullification path returns np.nan.

        The first (and only) observation is on the resolution date, so there is no value at
        the earlier forecast_due_date and ffill cannot back-fill before the first observation.
        _resolve_single_question sees a NaN forecast_due_date_value and returns np.nan, but the
        row is still flagged resolved (it was in the mask).
        """
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hM": {"id_root": "FIDE_rankings_elo_rating", "id_field_value": "Player M"}}
        )
        dfr = make_resolution_df([{"id": "hM", "date": "2025-01-05", "value": 102.0}])
        df = _make_wiki_resolve_df(
            [{"id": "hM", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert bool(out["resolved"].iloc[0]) is True
        assert pd.isna(out["resolved_to"].iloc[0])

    def test_resolution_date_after_yesterday_stays_unresolved(self, freeze_today):
        """A resolution_date strictly after yesterday is gated out by the mask: row unresolved.

        yesterday = 2025-01-09; resolution_date = 2025-01-20 fails ``resolution_date <= yesterday``,
        so the row is never iterated. It retains the seeded resolved=False / resolved_to=NaN even
        though the underlying values would otherwise resolve it True.
        """
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hU": {"id_root": "FIDE_rankings_elo_rating", "id_field_value": "Player U"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hU", "date": "2025-01-01", "value": 100.0},
                {"id": "hU", "date": "2025-01-05", "value": 102.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hU", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-20"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert bool(out["resolved"].iloc[0]) is False
        assert pd.isna(out["resolved_to"].iloc[0])

    def test_unknown_id_root_question_type_nullifies_to_nan(self, freeze_today):
        """An id_root with no matching PAGES entry yields !=1 matches -> np.nan.

        The hash unmaps to an id_root absent from PAGES, so the question_type lookup finds zero
        matches (len != 1) and returns np.nan; the row is flagged resolved with resolved_to NaN.
        """
        freeze_today(date(2025, 1, 10))
        src = _wiki_source(
            {"hX": {"id_root": "NOT_A_REAL_PAGE_ROOT", "id_field_value": "Player X"}}
        )
        dfr = make_resolution_df(
            [
                {"id": "hX", "date": "2025-01-01", "value": 100.0},
                {"id": "hX", "date": "2025-01-05", "value": 102.0},
            ]
        )
        df = _make_wiki_resolve_df(
            [{"id": "hX", "forecast_due_date": "2025-01-01", "resolution_date": "2025-01-05"}]
        )

        out, _ = src._resolve(df, pd.DataFrame(), dfr)

        assert bool(out["resolved"].iloc[0]) is True
        assert pd.isna(out["resolved_to"].iloc[0])
