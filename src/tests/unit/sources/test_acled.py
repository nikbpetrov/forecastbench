"""Tests for AcledSource: aggregation functions, _acled_resolve, hash mapping."""

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import helpers.acled as acled_helpers
from sources.acled import AcledSource
from tests.factories import (
    make_acled_resolution_df,
    make_forecast_df,
    make_question_df,
)

# ---------------------------------------------------------------------------
# Shared test data factory
# ---------------------------------------------------------------------------


def _make_acled_dfr():
    """Build a small ACLED resolution DataFrame for testing aggregation functions.

    Creates 60 days of data (2024-11-01 to 2024-12-30) for two countries.
    """
    rows = []
    base_date = date(2024, 11, 1)
    for day_offset in range(60):
        d = base_date + timedelta(days=day_offset)
        rows.append(
            {
                "country": "CountryA",
                "event_date": d,
                "Battles": 2,
                "Riots": 1,
            }
        )
        rows.append(
            {
                "country": "CountryB",
                "event_date": d,
                "Battles": 5,
                "Riots": 3,
            }
        )
    return make_acled_resolution_df(rows)


# ---------------------------------------------------------------------------
# _sum_over_past_30_days
# ---------------------------------------------------------------------------


class TestSumOverPast30Days:
    """Test 30-day sum aggregation."""

    def test_sums_correct_window(self):
        dfr = _make_acled_dfr()
        ref_date = date(2024, 12, 15)
        # 30 days before Dec 15 = Nov 15 to Dec 14 = 30 days
        # CountryA has Battles=2 per day → 30 * 2 = 60
        result = AcledSource._sum_over_past_30_days(dfr, "CountryA", "Battles", ref_date)
        assert result == 60

    def test_different_country(self):
        dfr = _make_acled_dfr()
        ref_date = date(2024, 12, 15)
        # CountryB has Battles=5 per day → 30 * 5 = 150
        result = AcledSource._sum_over_past_30_days(dfr, "CountryB", "Battles", ref_date)
        assert result == 150

    def test_different_event_type(self):
        dfr = _make_acled_dfr()
        ref_date = date(2024, 12, 15)
        # CountryA Riots=1 per day → 30
        result = AcledSource._sum_over_past_30_days(dfr, "CountryA", "Riots", ref_date)
        assert result == 30

    def test_empty_country_returns_zero(self):
        dfr = _make_acled_dfr()
        result = AcledSource._sum_over_past_30_days(
            dfr, "NonExistent", "Battles", date(2024, 12, 15)
        )
        assert result == 0

    def test_no_events_in_window_returns_zero(self):
        dfr = _make_acled_dfr()
        # Data starts Nov 1, so a ref_date of Oct 1 has no data in its 30-day window
        result = AcledSource._sum_over_past_30_days(dfr, "CountryA", "Battles", date(2024, 10, 1))
        assert result == 0


# ---------------------------------------------------------------------------
# _thirty_day_avg_over_past_360_days
# ---------------------------------------------------------------------------


class TestThirtyDayAvgOverPast360Days:
    """Test 360-day average (total/12) aggregation."""

    def test_with_60_days_of_data(self):
        dfr = _make_acled_dfr()
        ref_date = date(2024, 12, 31)
        # CountryA Battles: 60 days * 2 = 120 total in 360 window (only 60 days have data)
        # Average = 120 / 12 = 10
        result = AcledSource._thirty_day_avg_over_past_360_days(
            dfr, "CountryA", "Battles", ref_date
        )
        assert result == 10

    def test_empty_country_returns_zero(self):
        dfr = _make_acled_dfr()
        result = AcledSource._thirty_day_avg_over_past_360_days(
            dfr, "NonExistent", "Battles", date(2024, 12, 15)
        )
        assert result == 0


# ---------------------------------------------------------------------------
# _thirty_day_avg_over_past_360_days_plus_1
# ---------------------------------------------------------------------------


class TestThirtyDayAvgPlus1:
    """Test 1 + 30-day average."""

    def test_adds_one(self):
        dfr = _make_acled_dfr()
        ref_date = date(2024, 12, 31)
        avg = AcledSource._thirty_day_avg_over_past_360_days(dfr, "CountryA", "Battles", ref_date)
        result = AcledSource._thirty_day_avg_over_past_360_days_plus_1(
            dfr, "CountryA", "Battles", ref_date
        )
        assert result == 1 + avg


# ---------------------------------------------------------------------------
# _get_base_comparison_value
# ---------------------------------------------------------------------------


class TestGetBaseComparisonValue:
    """Test dispatch on key string."""

    def test_key_last30_days(self):
        dfr = _make_acled_dfr()
        result = AcledSource._get_base_comparison_value(
            key="last30Days.gt.30DayAvgOverPast360Days",
            dfr=dfr,
            country="CountryA",
            col="Battles",
            ref_date=date(2024, 12, 31),
        )
        expected = AcledSource._thirty_day_avg_over_past_360_days(
            dfr, "CountryA", "Battles", date(2024, 12, 31)
        )
        assert result == expected

    def test_key_last30_days_times_10(self):
        dfr = _make_acled_dfr()
        result = AcledSource._get_base_comparison_value(
            key="last30DaysTimes10.gt.30DayAvgOverPast360DaysPlus1",
            dfr=dfr,
            country="CountryA",
            col="Battles",
            ref_date=date(2024, 12, 31),
        )
        expected = 10 * AcledSource._thirty_day_avg_over_past_360_days_plus_1(
            dfr, "CountryA", "Battles", date(2024, 12, 31)
        )
        assert result == expected

    def test_invalid_key_raises(self):
        dfr = _make_acled_dfr()
        with pytest.raises(ValueError, match="Invalid key"):
            AcledSource._get_base_comparison_value(
                key="invalid_key",
                dfr=dfr,
                country="CountryA",
                col="Battles",
                ref_date=date(2024, 12, 31),
            )


# ---------------------------------------------------------------------------
# _acled_resolve
# ---------------------------------------------------------------------------


class TestAcledResolve:
    """Test the core comparison: int(30_day_sum > baseline)."""

    def test_lhs_greater_returns_1(self):
        dfr = _make_acled_dfr()
        # ref for lhs: Dec 15 → sum = 30 * 2 = 60
        # ref for rhs: Nov 5 → avg over 360 days from Nov 5 = 5 days * 2 / 12 = 0.83
        # 60 > 0.83 → 1
        result = AcledSource._acled_resolve(
            key="last30Days.gt.30DayAvgOverPast360Days",
            dfr=dfr,
            country="CountryA",
            event_type="Battles",
            forecast_due_date=date(2024, 11, 5),
            resolution_date=date(2024, 12, 15),
        )
        assert result == 1

    def test_lhs_not_greater_returns_0(self):
        # Create data where the baseline is very high but 30-day sum is 0
        rows = []
        for day_offset in range(360):
            d = date(2024, 1, 1) + timedelta(days=day_offset)
            rows.append(
                {
                    "country": "CountryX",
                    "event_date": d,
                    "Battles": 100,
                }
            )
        dfr = make_acled_resolution_df(rows)
        # Zero out the last 30 days
        mask = dfr["event_date"] >= pd.Timestamp(date(2024, 12, 1))
        dfr.loc[mask, "Battles"] = 0

        # resolution_date = Dec 31 → sum of last 30 days = 0
        # forecast_due_date = Jan 1 → baseline avg over 360 days is high
        result = AcledSource._acled_resolve(
            key="last30Days.gt.30DayAvgOverPast360Days",
            dfr=dfr,
            country="CountryX",
            event_type="Battles",
            forecast_due_date=date(2024, 1, 1),
            resolution_date=date(2024, 12, 31),
        )
        assert result == 0


# ---------------------------------------------------------------------------
# Hash mapping
# ---------------------------------------------------------------------------


class TestAcledHashMapping:
    """Test hash mapping load, dump, and unhash."""

    def test_populate_hash_mapping(self):
        source = AcledSource()
        source.populate_hash_mapping(
            '{"hash1": {"key": "last30Days.gt.30DayAvgOverPast360Days", '
            '"country": "Somalia", "event_type": "Battles"}}'
        )
        assert "hash1" in source.hash_mapping
        assert source.hash_mapping["hash1"]["country"] == "Somalia"

    def test_load_empty_string(self):
        source = AcledSource()
        source.populate_hash_mapping("")
        assert source.hash_mapping == {}

    def test_dump_hash_mapping(self):
        source = AcledSource()
        source.hash_mapping = {"h1": {"key": "test"}}
        result = source.dump_hash_mapping()
        assert '"h1"' in result
        assert '"test"' in result

    def test_id_unhash_found(self):
        source = AcledSource()
        source.hash_mapping = {"h1": {"key": "k1", "country": "X", "event_type": "Y"}}
        assert source._id_unhash("h1") == {"key": "k1", "country": "X", "event_type": "Y"}

    def test_id_unhash_not_found(self):
        source = AcledSource()
        source.hash_mapping = {}
        assert source._id_unhash("missing") is None


# ---------------------------------------------------------------------------
# resolve() / _resolve() orchestration end-to-end
# ---------------------------------------------------------------------------

_KEY = "last30Days.gt.30DayAvgOverPast360Days"


def _resolve_dfr():
    """Build a resolution frame: 60 days (Nov 1 - Dec 30, 2024) for two countries.

    CountryA has Battles=2/day, Riots=1/day; CountryB has Battles=5/day, Riots=3/day.
    max(event_date) is therefore 2024-12-30.
    """
    rows = []
    base = date(2024, 11, 1)
    for day_offset in range(60):
        d = base + timedelta(days=day_offset)
        rows.append({"country": "CountryA", "event_date": d, "Battles": 2, "Riots": 1})
        rows.append({"country": "CountryB", "event_date": d, "Battles": 5, "Riots": 3})
    return make_acled_resolution_df(rows)


def _hash_question(source, country, event_type, key=_KEY):
    """Hash an ACLED question dict into ``source.hash_mapping`` and return the hash id."""
    return source._id_hash({"key": key, "country": country, "event_type": event_type})


class TestAcledResolveOrchestration:
    """Test AcledSource.resolve()/_resolve() against exact resolved_to/resolved oracles.

    The frame from ``_resolve_dfr`` makes the comparison oracle hand-computable:
    ``resolved_to = int(30-day sum at resolution_date > 30-day avg over 360 days at due date)``.
    """

    def test_resolves_positive(self, acled_source):
        """A single question whose 30-day sum exceeds the baseline resolves to 1.0.

        CountryA Battles, resolution_date=2024-12-15: 30-day sum = 30 * 2 = 60.
        forecast_due_date=2024-11-05: 360-day avg = (4 days * 2) / 12 = 0.667.
        60 > 0.667 -> resolved_to == 1.0, resolved == True.
        """
        dfr = _resolve_dfr()
        h = _hash_question(acled_source, "CountryA", "Battles")
        dfq = make_question_df([{"id": h}])
        df = make_forecast_df(
            [
                {
                    "id": h,
                    "source": "acled",
                    "forecast_due_date": "2024-11-05",
                    "resolution_date": "2024-12-15",
                }
            ]
        )

        out, warnings = acled_source.resolve(df, dfq, dfr, forecast_due_date=date(2024, 11, 5))

        assert warnings == []
        assert len(out) == 1
        assert bool(out.iloc[0]["resolved"]) is True
        assert out.iloc[0]["resolved_to"] == 1.0

    def test_resolves_negative(self, acled_source):
        """A single question whose 30-day sum is below the baseline resolves to 0.0.

        CountryA Battles, resolution_date=2024-11-03: 30-day sum = 2 days (Nov 1-2) * 2 = 4.
        forecast_due_date=2024-12-30: 360-day avg = (59 days * 2) / 12 = 9.833.
        4 > 9.833 is False -> resolved_to == 0.0, resolved == True.
        """
        dfr = _resolve_dfr()
        h = _hash_question(acled_source, "CountryA", "Battles")
        dfq = make_question_df([{"id": h}])
        df = make_forecast_df(
            [
                {
                    "id": h,
                    "source": "acled",
                    "forecast_due_date": "2024-12-30",
                    "resolution_date": "2024-11-03",
                }
            ]
        )

        out, _ = acled_source.resolve(df, dfq, dfr, forecast_due_date=date(2024, 12, 30))

        assert bool(out.iloc[0]["resolved"]) is True
        assert out.iloc[0]["resolved_to"] == 0.0

    def test_combo_resolves_via_change_sign(self, acled_source):
        """A combo row combines both legs through ``_combo_change_sign``.

        Both legs resolve positive (1). With direction (1, -1) the combo value is
        ``1 * (1 - 1) == 0.0``; flipping to direction (1, 1) gives ``1 * 1 == 1.0``.
        """
        dfr = _resolve_dfr()
        h_a = _hash_question(acled_source, "CountryA", "Battles")
        h_b = _hash_question(acled_source, "CountryB", "Battles")
        dfq = make_question_df([{"id": h_a}, {"id": h_b}])

        df_flip = make_forecast_df(
            [
                {
                    "id": (h_a, h_b),
                    "source": "acled",
                    "direction": (1, -1),
                    "forecast_due_date": "2024-11-05",
                    "resolution_date": "2024-12-15",
                }
            ]
        )
        out_flip, _ = acled_source.resolve(df_flip, dfq, dfr, forecast_due_date=date(2024, 11, 5))
        assert bool(out_flip.iloc[0]["resolved"]) is True
        assert out_flip.iloc[0]["resolved_to"] == 0.0

        df_same = make_forecast_df(
            [
                {
                    "id": (h_a, h_b),
                    "source": "acled",
                    "direction": (1, 1),
                    "forecast_due_date": "2024-11-05",
                    "resolution_date": "2024-12-15",
                }
            ]
        )
        out_same, _ = acled_source.resolve(df_same, dfq, dfr, forecast_due_date=date(2024, 11, 5))
        assert out_same.iloc[0]["resolved_to"] == 1.0

    def test_resolution_date_beyond_data_stays_unresolved(self, acled_source):
        """A resolution_date past max(event_date) is excluded by the mask and stays unresolved.

        max(event_date) is 2024-12-30; a resolution_date of 2025-06-01 is outside the mask, so
        the row keeps its input defaults (resolved == False, resolved_to is NaN).
        """
        dfr = _resolve_dfr()
        h = _hash_question(acled_source, "CountryA", "Battles")
        dfq = make_question_df([{"id": h}])
        df = make_forecast_df(
            [
                {
                    "id": h,
                    "source": "acled",
                    "forecast_due_date": "2024-11-05",
                    "resolution_date": "2025-06-01",
                }
            ]
        )

        out, _ = acled_source.resolve(df, dfq, dfr, forecast_due_date=date(2024, 11, 5))

        assert bool(out.iloc[0]["resolved"]) is False
        assert pd.isna(out.iloc[0]["resolved_to"])

    def test_question_missing_from_dfq_is_nan_but_marked_resolved(self, acled_source):
        """An id absent from dfq yields resolved_to=NaN yet resolved=True (latent issue).

        ``_resolve_single_question`` returns NaN when ``_get_question`` finds nothing, but
        ``_resolve`` ends with a blanket ``df.loc[mask, "resolved"] = True`` over every in-window
        row, so the row is still marked resolved despite having no resolution value. We pin the
        current behavior; the resolved=True here is arguably a bug.
        """
        dfr = _resolve_dfr()
        # Hash exists in hash_mapping, but its id is NOT present in dfq.
        h = _hash_question(acled_source, "CountryA", "Battles")
        dfq = make_question_df([{"id": "some-other-id"}])
        df = make_forecast_df(
            [
                {
                    "id": h,
                    "source": "acled",
                    "forecast_due_date": "2024-11-05",
                    "resolution_date": "2024-12-15",
                }
            ]
        )

        out, _ = acled_source.resolve(df, dfq, dfr, forecast_due_date=date(2024, 11, 5))

        assert pd.isna(out.iloc[0]["resolved_to"])
        assert bool(out.iloc[0]["resolved"]) is True

    def test_unhashable_id_is_nan_but_marked_resolved(self, acled_source):
        """An id present in dfq but absent from hash_mapping is NaN yet marked resolved=True.

        ``_resolve_single_question`` returns NaN when ``_id_unhash`` misses, but the blanket
        ``df.loc[mask, "resolved"] = True`` still flips resolved for the in-window row. Same latent
        issue as the missing-question case; pinned here for the unhash path.
        """
        dfr = _resolve_dfr()
        unhashable_id = "not-in-hash-mapping"
        dfq = make_question_df([{"id": unhashable_id}])
        df = make_forecast_df(
            [
                {
                    "id": unhashable_id,
                    "source": "acled",
                    "forecast_due_date": "2024-11-05",
                    "resolution_date": "2024-12-15",
                }
            ]
        )

        out, _ = acled_source.resolve(df, dfq, dfr, forecast_due_date=date(2024, 11, 5))

        assert pd.isna(out.iloc[0]["resolved_to"])
        assert bool(out.iloc[0]["resolved"]) is True


# ---------------------------------------------------------------------------
# helpers.acled.read_dff
# ---------------------------------------------------------------------------


def _write_acled_fetch_jsonl(directory, rows):
    """Write ``rows`` to ``acled_fetch.jsonl`` (the name generate_filenames produces) in directory.

    ``read_dff(local_question_bank_dir=...)`` reads ``{dir}/acled_fetch.jsonl`` directly.
    """
    path = directory / "acled_fetch.jsonl"
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def _acled_fetch_row(**overrides):
    """Build a single raw ACLED fetch row (all FETCH_COLUMNS present)."""
    base = {
        "event_id_cnty": "X1",
        "event_date": "2024-11-01",
        "iso": 1,
        "region": "Region",
        "country": "Aruba",
        "admin1": "A1",
        "event_type": "Battles",
        "fatalities": 0,
        "timestamp": "ts",
    }
    base.update(overrides)
    return base


class TestReadDff:
    """Test the fetch-file parsing, malformed-year correction, and aggregation in read_dff."""

    def test_fixes_malformed_year_prefixes(self, tmp_path):
        """The '0025-'/'0024-' year-prefix bug is corrected to '2025-'/'2024-'.

        ACLED emitted dates like '0025-01-15' (meant 2025) and '0024-12-31' (meant 2024).
        After read_dff the parsed event_date Timestamps must be 2025-01-15 and 2024-12-31.
        """
        rows = [
            _acled_fetch_row(
                event_id_cnty="ABW24",
                event_date="0025-01-15",
                event_type="Battles",
                fatalities=3,
            ),
            _acled_fetch_row(
                event_id_cnty="NCL346",
                event_date="0024-12-31",
                event_type="Riots",
                fatalities=1,
            ),
        ]
        _write_acled_fetch_jsonl(tmp_path, rows)

        df, _ = acled_helpers.read_dff(local_question_bank_dir=str(tmp_path))

        dates = set(df["event_date"].dt.date)
        assert date(2025, 1, 15) in dates
        assert date(2024, 12, 31) in dates
        # The malformed century never survives.
        assert all(d.year >= 2024 for d in df["event_date"].dt.date)

    def test_aggregates_one_column_per_event_type_by_country_date(self, tmp_path):
        """The dfr has one column per event type, grouped/summed by (country, event_date).

        Two Aruba rows on 2025-01-15 (Battles fatalities=3, Riots fatalities=5) collapse into a
        single (Aruba, 2025-01-15) row with Battles=1, Riots=1, fatalities=8. A separate
        (Aruba, 2024-12-31) Riots row stays distinct with Battles=0, Riots=1, fatalities=1.
        """
        rows = [
            _acled_fetch_row(
                event_id_cnty="A1",
                event_date="2025-01-15",
                event_type="Battles",
                fatalities=3,
            ),
            _acled_fetch_row(
                event_id_cnty="A2",
                event_date="2025-01-15",
                event_type="Riots",
                fatalities=5,
            ),
            _acled_fetch_row(
                event_id_cnty="A3",
                event_date="2024-12-31",
                event_type="Riots",
                fatalities=1,
            ),
        ]
        _write_acled_fetch_jsonl(tmp_path, rows)

        _, dfr = acled_helpers.read_dff(local_question_bank_dir=str(tmp_path))

        # One column per event type plus the country/event_date keys and fatalities.
        assert "Battles" in dfr.columns
        assert "Riots" in dfr.columns
        assert {"country", "event_date"}.issubset(dfr.columns)

        # (country, event_date) is the grouping key: two source rows on 2025-01-15 -> one row.
        assert len(dfr) == 2

        jan15 = dfr[dfr["event_date"] == pd.Timestamp(2025, 1, 15)].iloc[0]
        assert jan15["Battles"] == 1
        assert jan15["Riots"] == 1
        assert jan15["fatalities"] == 8

        dec31 = dfr[dfr["event_date"] == pd.Timestamp(2024, 12, 31)].iloc[0]
        assert dec31["Battles"] == 0
        assert dec31["Riots"] == 1
        assert dec31["fatalities"] == 1


# ---------------------------------------------------------------------------
# helpers.acled.get_forecast (naive forecaster; stochastic but seedable)
# ---------------------------------------------------------------------------


def _forecast_dfr(yhat=5.0, spread=1.0, periods=30):
    """Build a Prophet-style frame (ds/yhat/yhat_upper/yhat_lower) for get_forecast."""
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    return pd.DataFrame(
        {
            "ds": dates,
            "yhat": [yhat] * periods,
            "yhat_upper": [yhat + spread] * periods,
            "yhat_lower": [yhat - spread] * periods,
        }
    )


class TestGetForecast:
    """Test the naive forecaster's Monte-Carlo probability estimate (seeded for determinism)."""

    def test_deterministic_under_fixed_seed(self):
        """Two calls with the same np.random seed produce exactly the same probability.

        get_forecast draws 1000 normal samples; seeding numpy makes it reproducible.
        """
        np.random.seed(0)
        first = acled_helpers.get_forecast(
            comparison_value=150,
            dfr=_forecast_dfr(),
            country="Aruba",
            col="Battles",
            ref_date=date(2024, 1, 31),
        )
        np.random.seed(0)
        second = acled_helpers.get_forecast(
            comparison_value=150,
            dfr=_forecast_dfr(),
            country="Aruba",
            col="Battles",
            ref_date=date(2024, 1, 31),
        )
        assert first == second
        assert 0.0 <= first <= 1.0

    def test_probability_decreases_as_comparison_value_rises(self):
        """P(30-day sum > comparison_value) is monotonically non-increasing in comparison_value.

        With 30 days of yhat=5 the simulated 30-day sum centers near 150. A threshold below the
        center (130) must give a probability >= a threshold at the center (150) >= one well above
        it (170); the extremes saturate toward 1.0 and 0.0. Seeded so the comparison is exact.
        """
        np.random.seed(123)
        p_low = acled_helpers.get_forecast(
            comparison_value=130,
            dfr=_forecast_dfr(),
            country="Aruba",
            col="Battles",
            ref_date=date(2024, 1, 31),
        )
        np.random.seed(123)
        p_mid = acled_helpers.get_forecast(
            comparison_value=150,
            dfr=_forecast_dfr(),
            country="Aruba",
            col="Battles",
            ref_date=date(2024, 1, 31),
        )
        np.random.seed(123)
        p_high = acled_helpers.get_forecast(
            comparison_value=170,
            dfr=_forecast_dfr(),
            country="Aruba",
            col="Battles",
            ref_date=date(2024, 1, 31),
        )
        assert p_low >= p_mid >= p_high
        assert p_low > 0.5 > p_high
