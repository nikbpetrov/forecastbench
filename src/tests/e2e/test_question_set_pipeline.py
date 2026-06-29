"""End-to-end: the question-SET creation pipeline (distinct from the forecast-resolution e2e).

Exercises the ``metadata`` -> ``curate_questions`` flow against a ``local_bucket``, with the LLM
mocked, through the real ``question_metadata.jsonl`` handoff artifact. Two complementary views:

1. The composed *stages* (``test_invalid_questions_*`` / ``*_is_deterministic``):

       seed banks -> tag.driver (categories) -> validate.driver (validity)
           -> question_metadata.jsonl -> drop_invalid -> drop_missing_freeze -> human_sample

2. The real ``curate.driver`` (``test_curate_driver_builds_question_set``): seed banks + metadata,
   run the whole driver (filter chain -> allocate -> seeded sample -> write_questions), then read the
   published ``<date>-{llm,human}.json`` back and **golden** the produced rows. This is the headline
   artifact — the question set — finally built in a test, deterministic via ``QUESTION_SET_SEED``.

The key end-to-end property: a question the validator flags as invalid never reaches the sampled
set, and the human set is a subset of the LLM set. Stage logic lives in unit/; this asserts the
stages compose across the two jobs.
"""

import contextlib
from datetime import date, datetime
from unittest.mock import patch

import pandas as pd

from curate_questions.create_question_set import main as curate
from curate_questions.create_question_set.main import (
    drop_invalid_questions,
    drop_missing_freeze_datetime,
    human_sample_questions,
)
from helpers import constants
from metadata.tag_questions import main as tag
from metadata.validate_questions import main as validate
from tests._golden import check_golden
from tests.factories import make_question_df

_SOURCES = {"manifold": {}, "fred": {}}
_MANIFOLD = [
    {"id": "good1", "question": "Public-interest Q1?", "freeze_datetime_value": "0.5"},
    {"id": "good2", "question": "Public-interest Q2?", "freeze_datetime_value": "0.4"},
    {"id": "bad1", "question": "Inappropriate personal Q?", "freeze_datetime_value": "0.3"},
]
_FRED = [
    {"id": "f1", "question": "Will CPI rise?", "freeze_datetime_value": "100"},
    {"id": "f2", "question": "Will GDP rise?", "freeze_datetime_value": "200"},
]


def _run_metadata_jobs(local_bucket):
    """Tag then validate the seeded banks (LLM mocked), writing question_metadata.jsonl."""

    def fake_validate(model_name, prompt, max_tokens=None):
        return "Classification: flag" if "Inappropriate" in prompt else "Classification: ok"

    with patch.object(tag.question_curation, "FREEZE_QUESTION_SOURCES", _SOURCES), patch.object(
        tag.model_eval, "get_response_from_model", return_value="Politics & Governance"
    ), patch.object(tag.time, "sleep"):
        tag.driver(None)

    with patch.object(
        validate.question_curation, "FREEZE_QUESTION_SOURCES", _SOURCES
    ), patch.object(
        validate.model_eval, "get_response_from_model", side_effect=fake_validate
    ), patch.object(
        validate.time, "sleep"
    ):
        validate.driver(None)

    return pd.read_json(local_bucket.question_bank_dir() / constants.META_DATA_FILENAME, lines=True)


def _valid_questions(local_bucket, meta):
    """Curate's intake: per source, drop invalid + freeze-less questions, then concat."""
    kept = []
    for source in _SOURCES:
        dfq = local_bucket.read_questions(source)
        dfq["source"] = source
        dfq = drop_invalid_questions(dfq, meta)
        dfq = drop_missing_freeze_datetime(dfq)
        kept.append(dfq)
    return pd.concat(kept, ignore_index=True)


def test_invalid_questions_never_reach_the_sampled_set(local_bucket):
    local_bucket.seed_metadata([])  # start from known-empty metadata (avoid stale /tmp)
    local_bucket.seed_questions("manifold", make_question_df(_MANIFOLD).to_dict("records"))
    local_bucket.seed_questions("fred", make_question_df(_FRED).to_dict("records"))

    # --- Stage 1: metadata (tag + validate) produces the handoff artifact ---
    meta = _run_metadata_jobs(local_bucket)
    cat = dict(zip(meta["id"].astype(str), meta["category"]))
    valid = dict(zip(meta["id"].astype(str), meta["valid_question"]))
    assert cat["good1"] == "Politics & Governance"  # manifold -> LLM (mocked)
    assert cat["f1"] == "Economics & Business"  # fred -> hard-coded
    assert valid["good1"] is True and valid["bad1"] is False  # validator flagged the bad one

    # --- Stage 2: curate consumes the metadata; invalid is filtered out ---
    llm_pool = _valid_questions(local_bucket, meta)
    assert "bad1" not in set(llm_pool["id"])  # the flagged question is gone end to end
    assert {"good1", "good2", "f1", "f2"} == set(llm_pool["id"])

    # --- Stage 3: the human set is a deterministic subset of the LLM set ---
    human = human_sample_questions({"dfq": llm_pool}, 2, random_state=0)
    assert len(human) == 2
    assert set(human["id"]) <= set(llm_pool["id"])  # humans ⊆ LLM


def test_question_set_pipeline_is_deterministic(local_bucket):
    local_bucket.seed_metadata([])  # start from known-empty metadata (avoid stale /tmp)
    local_bucket.seed_questions("manifold", make_question_df(_MANIFOLD).to_dict("records"))
    local_bucket.seed_questions("fred", make_question_df(_FRED).to_dict("records"))
    meta = _run_metadata_jobs(local_bucket)
    pool = _valid_questions(local_bucket, meta)

    first = human_sample_questions({"dfq": pool}, 2, random_state=7)
    second = human_sample_questions({"dfq": pool}, 2, random_state=7)
    pd.testing.assert_frame_equal(
        first.sort_values("id").reset_index(drop=True),
        second.sort_values("id").reset_index(drop=True),
    )


# ---------------------------------------------------------------------------
# The real curate.driver: build + publish a question set, then golden it.
# ---------------------------------------------------------------------------

# Fixed dates so the published filename + resolution dates (and thus the golden) are deterministic.
_CURATE_FREEZE = datetime(2025, 1, 1)
_CURATE_FORECAST = datetime(2025, 1, 11)  # FREEZE + FREEZE_WINDOW_IN_DAYS (10)
_CURATE_FORECAST_DATE = date(2025, 1, 11)
_CURATE_CLOSE = "2025-03-12T00:00:00"  # FORECAST + 60d → a valid horizon bin; not "too soon"
_CURATE_SOURCES = {
    "manifold": {
        "name": "Manifold",
        "source_intro": "Manifold intro.",
        "resolution_criteria": "Resolves per {url}.",
    },
    "fred": {
        "name": "FRED",
        "source_intro": "FRED intro.",
        "resolution_criteria": "Resolves per {url}.",
    },
}
_CURATE_GOLDEN_COLS = [
    "source",
    "id",
    "question",
    "freeze_datetime_value",
    "freeze_datetime",
    "market_info_close_datetime",
    "resolution_criteria",
    "source_intro",
]


def _seed_curate_inputs(local_bucket):
    """8 markets + 8 datasets, with one invalid / one resolved / one ``Other`` to be filtered out."""
    manifold = make_question_df(
        [
            {
                "id": f"m{i}",
                "source": "manifold",
                "question": f"Market question {i}?",
                "url": f"https://example.com/m{i}",
                "resolved": i == 1,  # m1 is resolved → excluded
                "freeze_datetime_value": "0.5",
                "market_info_close_datetime": _CURATE_CLOSE,
            }
            for i in range(8)
        ]
    ).to_dict("records")
    fred = make_question_df(
        [
            {
                "id": f"f{i}",
                "source": "fred",
                "question": f"Data question {i}?",
                "url": f"https://example.com/f{i}",
                "resolved": False,
                "freeze_datetime_value": str(100 + i),
                "forecast_horizons": [7, 30],  # non-empty → survives the resolve-too-soon filter
            }
            for i in range(8)
        ]
    ).to_dict("records")
    local_bucket.seed_questions("manifold", manifold)
    local_bucket.seed_questions("fred", fred)

    meta = [
        {
            "source": "manifold",
            "id": f"m{i}",
            "category": "Politics & Governance",
            "valid_question": i != 0,  # m0 is invalid → excluded
        }
        for i in range(8)
    ] + [
        {
            "source": "fred",
            "id": f"f{i}",
            "category": "Other" if i == 0 else "Economics & Business",  # f0 "Other" → excluded
            "valid_question": True,
        }
        for i in range(8)
    ]
    local_bucket.seed_metadata(meta)


def _run_curate_driver(local_bucket, monkeypatch):
    """Run the real driver on the seeded inputs; return the published (llm, human) question sets."""
    _seed_curate_inputs(local_bucket)
    monkeypatch.delenv("RUNNING_LOCALLY", raising=False)  # so write_questions writes to the bucket
    monkeypatch.setenv("QUESTION_SET_SEED", "0")  # deterministic sampling → stable golden
    qc = curate.question_curation
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(qc, "FREEZE_QUESTION_SOURCES", _CURATE_SOURCES))
        stack.enter_context(patch.object(qc, "FREEZE_NUM_LLM_QUESTIONS", 8))
        stack.enter_context(patch.object(qc, "FREEZE_NUM_HUMAN_QUESTIONS", 4))
        stack.enter_context(patch.object(qc, "FREEZE_DATETIME", _CURATE_FREEZE))
        stack.enter_context(patch.object(qc, "FORECAST_DATETIME", _CURATE_FORECAST))
        stack.enter_context(patch.object(qc, "FORECAST_DATE", _CURATE_FORECAST_DATE))
        stack.enter_context(patch.object(qc, "is_today_question_curation_date", return_value=True))
        curate.driver(None)

    def _read(target):
        payload = local_bucket.read_json("QUESTION_SETS_BUCKET", f"2025-01-11-{target}.json")
        return pd.DataFrame(payload["questions"])

    return _read("llm"), _read("human")


def test_curate_driver_builds_question_set(local_bucket, monkeypatch):
    llm, human = _run_curate_driver(local_bucket, monkeypatch)

    # --- Anchors: the filter chain + even cross-source allocation are correct ---
    assert len(llm) == 8  # 4 market + 4 data (FREEZE_NUM_LLM_QUESTIONS // 2 per question type)
    ids = set(llm["id"])
    assert "m0" not in ids and "m1" not in ids  # invalid + resolved markets dropped
    assert "f0" not in ids  # "Other"-category dataset dropped
    assert set(llm[llm["source"] == "manifold"]["id"]) <= {f"m{i}" for i in range(2, 8)}
    assert set(llm[llm["source"] == "fred"]["id"]) <= {f"f{i}" for i in range(1, 8)}
    assert (llm["source"] == "manifold").sum() == 4 and (llm["source"] == "fred").sum() == 4

    # Enrichment: resolution_criteria URL-templated, source_intro + freeze_datetime stamped.
    assert llm["resolution_criteria"].str.contains("https://example.com/").all()
    assert set(llm["source_intro"]) == {"Manifold intro.", "FRED intro."}
    assert (llm["freeze_datetime"] == "2025-01-01T00:00:00").all()
    # Dataset horizons → resolution dates; markets carry "N/A".
    assert llm[llm["source"] == "fred"]["resolution_dates"].iloc[0] == ["2025-01-18", "2025-02-10"]
    assert (llm[llm["source"] == "manifold"]["resolution_dates"] == "N/A").all()

    # The human set is a deterministic subset of the LLM set.
    assert len(human) == 4  # 2 market + 2 data
    assert set(human["id"]) <= set(llm["id"])

    # --- Golden: freeze the produced question-set rows (scalar columns only) ---
    check_golden("question_set_llm", llm, key=["source", "id"], cols=_CURATE_GOLDEN_COLS)
    check_golden("question_set_human", human, key=["source", "id"], cols=_CURATE_GOLDEN_COLS)
