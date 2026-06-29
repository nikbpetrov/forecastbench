"""Integration: the ``func_resolve`` driver() — raw forecast set → processed forecast set.

Runs the real ``orchestration/func_resolve/main.py:driver()`` against a ``local_bucket``: it lists
the raw forecast files, downloads + resolves the question set, imputes missing forecasts, and writes
the processed file the leaderboard later consumes. This is the round-trip the resolution e2e skips by
hand-building frames — here the *driver* orchestrates it.

Only the GCP/git-coupled seams are patched; everything between is the real code path:
- ``_io.load_question_bank`` — raises on a GCS freshness check in prod → return a built bank.
- ``_io.upload_resolution_set`` — git-pushes the public resolution set → mock.
- ``_io.load_hash_mapping`` — reads ``<source>/hash_mapping.json`` from GCS (and leaves a stale
  ``/tmp`` copy on a miss) → return ``""`` so the run is hermetic.
- ``slack.send_message`` — posts market-resolution warnings → mock.
"""

import contextlib
from datetime import date
from unittest.mock import patch

from _fb_types import SourceQuestionBank
from orchestration.func_resolve import main as func_resolve
from tests.factories import make_question_df, make_raw_forecast_set, make_resolution_df

_DUE = "2025-01-01"
_FILENAME = f"{_DUE}.OrgA.modela.json"


def _question_bank():
    """metaculus (resolved market → 1.0) + fred (dataset: rose → 1.0, fell → 0.0)."""
    metaculus = SourceQuestionBank(
        dfq=make_question_df(
            [
                {
                    "id": "mc1",
                    "source": "metaculus",
                    "resolved": True,
                    "market_info_resolution_datetime": "2025-01-31T00:00:00Z",
                }
            ]
        ),
        dfr=make_resolution_df(
            [
                {"id": "mc1", "date": "2025-01-01", "value": 0.6},
                {
                    "id": "mc1",
                    "date": "2025-01-31",
                    "value": 1.0,
                },  # final value 1.0 → resolved_to 1
            ]
        ),
    )
    fred = SourceQuestionBank(
        dfq=make_question_df([{"id": "fr1", "source": "fred"}]),
        dfr=make_resolution_df(
            [
                {"id": "fr1", "date": "2025-01-01", "value": 100},  # baseline at due date
                {"id": "fr1", "date": "2025-01-08", "value": 110},  # +7 rose  → 1.0
                {"id": "fr1", "date": "2025-01-31", "value": 90},  # +30 fell → 0.0
            ]
        ),
    )
    return {"metaculus": metaculus, "fred": fred}


def _seed_question_sets(local_bucket):
    """Seed the llm + human question sets the resolver downloads for this forecast due date."""
    llm = {
        "questions": [
            {"id": "mc1", "source": "metaculus", "resolution_dates": "N/A"},
            {"id": "fr1", "source": "fred", "resolution_dates": ["2025-01-08", "2025-01-31"]},
        ]
    }
    human = {"questions": [{"id": "mc1", "source": "metaculus", "resolution_dates": "N/A"}]}
    local_bucket.seed_question_set(f"{_DUE}-llm.json", llm)
    local_bucket.seed_question_set(f"{_DUE}-human.json", human)


def _run_driver(local_bucket, monkeypatch, freeze_today, forecasts, *, eligible=True):
    """Seed inputs, patch the GCP/git seams, run the real driver, return the processed file."""
    _seed_question_sets(local_bucket)
    raw = make_raw_forecast_set(
        forecasts,
        organization="OrgA",
        model="ModelA",
        model_organization="OrgA",
        question_set=f"{_DUE}-llm.json",
        leaderboard_eligible=eligible,
    )
    local_bucket.seed_forecast_set(_DUE, _FILENAME, raw)

    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "0")
    freeze_today(date(2025, 2, 1))  # cutoff = today − 10 ≥ due, so the date is resolved

    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch.object(func_resolve._io, "load_question_bank", return_value=_question_bank())
        )
        stack.enter_context(patch.object(func_resolve._io, "load_hash_mapping", return_value=""))
        stack.enter_context(patch.object(func_resolve._io, "upload_resolution_set"))
        stack.enter_context(patch.object(func_resolve.slack, "send_message"))
        func_resolve.driver(None)

    return local_bucket.read_processed_forecast_set(_DUE, _FILENAME)


def _full_forecasts():
    return [
        {"id": "mc1", "source": "metaculus", "forecast": 0.9, "resolution_date": "2025-01-31"},
        {"id": "fr1", "source": "fred", "forecast": 0.7, "resolution_date": "2025-01-08"},
        {"id": "fr1", "source": "fred", "forecast": 0.3, "resolution_date": "2025-01-31"},
    ]


def test_resolves_and_writes_processed_file(local_bucket, monkeypatch, freeze_today):
    processed = _run_driver(local_bucket, monkeypatch, freeze_today, _full_forecasts())

    # The processed-file schema the leaderboard later reads.
    assert set(processed) >= {
        "organization",
        "model",
        "model_organization",
        "forecast_due_date",
        "question_set",
        "leaderboard_eligible",
        "forecasts",
    }
    assert processed["organization"] == "OrgA"
    assert processed["forecast_due_date"] == _DUE

    rows = processed["forecasts"]
    # Resolved market: binary outcome, marked resolved; the forecaster's value is preserved.
    (mc,) = [r for r in rows if r["id"] == "mc1"]
    assert mc["resolved"] is True and mc["resolved_to"] == 1.0
    assert mc["imputed"] is False and mc["forecast"] == 0.9
    # Dataset resolves to 1.0 (value rose) and 0.0 (value fell) at the two horizons.
    fr = {r["resolution_date"][:10]: r for r in rows if r["id"] == "fr1"}
    assert fr["2025-01-08"]["resolved_to"] == 1.0
    assert fr["2025-01-31"]["resolved_to"] == 0.0
    assert all(r["imputed"] is False for r in fr.values())


def test_imputes_missing_forecast(local_bucket, monkeypatch, freeze_today):
    # Forecaster omits fr1 @ +30 → that row is filled (0.5) and flagged imputed; the rest are kept.
    partial = [
        {"id": "mc1", "source": "metaculus", "forecast": 0.9, "resolution_date": "2025-01-31"},
        {"id": "fr1", "source": "fred", "forecast": 0.7, "resolution_date": "2025-01-08"},
    ]
    processed = _run_driver(local_bucket, monkeypatch, freeze_today, partial)

    fr = {r["resolution_date"][:10]: r for r in processed["forecasts"] if r["id"] == "fr1"}
    assert fr["2025-01-08"]["imputed"] is False and fr["2025-01-08"]["forecast"] == 0.7
    assert fr["2025-01-31"]["imputed"] is True and fr["2025-01-31"]["forecast"] == 0.5


def test_leaderboard_eligible_false_is_preserved(local_bucket, monkeypatch, freeze_today):
    # Eligibility is consumed downstream (by the leaderboard), not here: the file still resolves.
    processed = _run_driver(
        local_bucket, monkeypatch, freeze_today, _full_forecasts(), eligible=False
    )
    assert processed["leaderboard_eligible"] is False
    assert {r["id"] for r in processed["forecasts"]} == {"mc1", "fr1"}
