"""Integration: the ``metadata`` job drivers against a ``local_bucket`` (no GCP, LLM mocked).

These run the real ``tag_questions``/``validate_questions`` ``driver()`` IO chain — read each source's
question bank, classify/validate, write ``question_metadata.jsonl`` back to the bucket. The LLM is
mocked (``model_eval.get_response_from_model``) since it's a non-deterministic external boundary, and
``time.sleep`` (the per-source rate-limit pause) is stubbed so the test is fast. Only the seeded
sources contribute rows; the rest read back empty and are no-ops.
"""

from unittest.mock import patch

import pandas as pd

from helpers import constants
from metadata.tag_questions import main as tag
from metadata.validate_questions import main as validate
from tests.factories import make_question_df


def _seed_bank(local_bucket, source, rows):
    local_bucket.seed_questions(source, make_question_df(rows).to_dict("records"))


def _read_metadata(local_bucket):
    return pd.read_json(local_bucket.question_bank_dir() / constants.META_DATA_FILENAME, lines=True)


def _meta_row(source, id_, category="", valid_question=""):
    """A pre-existing question_metadata.jsonl row (the handoff artifact's full column set)."""
    return {"source": source, "id": id_, "category": category, "valid_question": valid_question}


class TestTagDriver:
    """Reads each source's bank, assigns categories (LLM or hard-coded), writes the metadata file."""

    def test_writes_categories_via_llm_and_hardcoded_sources(self, local_bucket):
        local_bucket.seed_metadata([])  # start from known-empty metadata (avoid stale /tmp)
        _seed_bank(
            local_bucket, "manifold", [{"id": "m1", "question": "Will X?", "background": "b"}]
        )
        _seed_bank(local_bucket, "fred", [{"id": "CPI", "question": "Will CPI rise?"}])
        _seed_bank(local_bucket, "acled", [{"id": "war", "question": "Battles in Y?"}])

        # Scope the driver to the seeded sources (the loop only uses the keys) — focused and fast.
        sources = {"manifold": {}, "fred": {}, "acled": {}}
        with patch.object(tag.question_curation, "FREEZE_QUESTION_SOURCES", sources), patch.object(
            tag.model_eval, "get_response_from_model", return_value="Science & Tech"
        ), patch.object(tag.time, "sleep"):
            tag.driver(None)

        meta = _read_metadata(local_bucket)
        by_id = dict(zip(meta["id"].astype(str), meta["category"]))
        assert by_id["m1"] == "Science & Tech"  # manifold -> LLM (mocked)
        assert by_id["CPI"] == "Economics & Business"  # fred -> hard-coded
        assert by_id["war"] == "Security & Defense"  # acled -> hard-coded
        # Every persisted category is a member of the allowed set.
        assert set(meta["category"]) <= set(constants.QUESTION_CATEGORIES)


class TestValidateDriver:
    """Reads each source's bank, validates (LLM or auto), writes valid_question to the metadata file."""

    def test_writes_validity_via_llm_and_auto_sources(self, local_bucket):
        local_bucket.seed_metadata([])  # start from known-empty metadata (avoid stale /tmp)
        _seed_bank(
            local_bucket,
            "manifold",
            [
                {"id": "good", "question": "Reasonable public-interest question?"},
                {"id": "bad", "question": "Inappropriate personal question?"},
            ],
        )
        _seed_bank(local_bucket, "fred", [{"id": "CPI", "question": "Will CPI rise?"}])

        def fake_model(model_name, prompt, max_tokens=None):
            assert "Will CPI rise?" not in prompt, "fred (a data source) must bypass the LLM"
            # 'bad' is flagged; everything else passes.
            return "Classification: flag" if "Inappropriate" in prompt else "Classification: ok"

        sources = {"manifold": {}, "fred": {}}
        with patch.object(
            validate.question_curation, "FREEZE_QUESTION_SOURCES", sources
        ), patch.object(
            validate.model_eval, "get_response_from_model", side_effect=fake_model
        ) as mock_model, patch.object(
            validate.time, "sleep"
        ):
            validate.driver(None)

        meta = _read_metadata(local_bucket)
        by_id = dict(zip(meta["id"].astype(str), meta["valid_question"]))
        assert by_id["good"] is True  # manifold -> LLM ok
        assert by_id["bad"] is False  # manifold -> LLM flag
        assert by_id["CPI"] is True  # fred (data source) -> auto-valid...
        assert mock_model.call_count == 2  # ...proven by: only the 2 manifold rows hit the LLM
        assert meta["valid_question"].dtype == bool


class TestTagDriverStatefulBehavior:
    """The tag driver is incremental + idempotent: it only tags what's new and prunes what's gone.

    The metadata file is the running handoff artifact; re-running over an unchanged bank must not
    re-pay the LLM, a new question must get tagged without disturbing existing rows, and a question
    removed from the bank must lose its (now-orphan) metadata row. The category gate is
    ``category == ""``, so any value already in ``QUESTION_CATEGORIES`` (incl. ``"Other"``) is kept.
    """

    def _run_tag(self, local_bucket, sources, **mock_kwargs):
        with patch.object(tag.question_curation, "FREEZE_QUESTION_SOURCES", sources), patch.object(
            tag.model_eval, "get_response_from_model", **mock_kwargs
        ) as mock_llm, patch.object(tag.time, "sleep"):
            tag.driver(None)
        return mock_llm

    def test_existing_tags_kept_only_new_questions_hit_the_llm(self, local_bucket):
        # m1 is already tagged (and already validated); m2 is brand new.
        local_bucket.seed_metadata([_meta_row("manifold", "m1", "Science & Tech", True)])
        _seed_bank(
            local_bucket,
            "manifold",
            [{"id": "m1", "question": "Q1?"}, {"id": "m2", "question": "Q2?"}],
        )

        mock_llm = self._run_tag(
            local_bucket, {"manifold": {}}, return_value="Politics & Governance"
        )

        meta = _read_metadata(local_bucket)
        cat = dict(zip(meta["id"].astype(str), meta["category"]))
        assert cat["m1"] == "Science & Tech"  # preserved, not recomputed
        assert cat["m2"] == "Politics & Governance"  # newly tagged
        assert mock_llm.call_count == 1  # only the untagged m2 was sent
        # m1's prior validity verdict rides through the tag pass untouched.
        valid = dict(zip(meta["id"].astype(str), meta["valid_question"]))
        assert valid["m1"] is True
        # Exactly one row per (source, id) — no duplication on re-run.
        assert not meta.duplicated(subset=["source", "id"]).any()
        assert len(meta) == 2

    def test_drops_metadata_for_questions_removed_from_the_bank(self, local_bucket):
        # "gone" has a metadata row but is no longer in the bank.
        local_bucket.seed_metadata(
            [
                _meta_row("manifold", "m1", "Science & Tech", True),
                _meta_row("manifold", "gone", "Sports", True),
            ]
        )
        _seed_bank(local_bucket, "manifold", [{"id": "m1", "question": "Q1?"}])

        mock_llm = self._run_tag(local_bucket, {"manifold": {}}, return_value="Other")

        meta = _read_metadata(local_bucket)
        ids = set(meta["id"].astype(str))
        assert ids == {"m1"}  # the orphan row was pruned
        assert mock_llm.call_count == 0  # m1 already tagged → no LLM call at all

    def test_other_category_persists_across_a_rerun(self, local_bucket):
        # "Other" is a real member of QUESTION_CATEGORIES, so it must not be re-tagged.
        local_bucket.seed_metadata([_meta_row("manifold", "m1", "Other", True)])
        _seed_bank(local_bucket, "manifold", [{"id": "m1", "question": "Q1?"}])

        mock_llm = self._run_tag(local_bucket, {"manifold": {}}, return_value="Science & Tech")

        meta = _read_metadata(local_bucket)
        assert dict(zip(meta["id"].astype(str), meta["category"]))["m1"] == "Other"
        assert mock_llm.call_count == 0


class TestValidateDriverStatefulBehavior:
    """The validate driver is likewise incremental: an existing verdict is never re-validated."""

    def test_existing_verdicts_kept_only_new_questions_hit_the_llm(self, local_bucket):
        # "good" already has a verdict (and a category from the tag pass); "fresh" is new.
        local_bucket.seed_metadata([_meta_row("manifold", "good", "Science & Tech", True)])
        _seed_bank(
            local_bucket,
            "manifold",
            [{"id": "good", "question": "Q1?"}, {"id": "fresh", "question": "Q2?"}],
        )

        with patch.object(
            validate.question_curation, "FREEZE_QUESTION_SOURCES", {"manifold": {}}
        ), patch.object(
            validate.model_eval, "get_response_from_model", return_value="Classification: ok"
        ) as mock_llm, patch.object(
            validate.time, "sleep"
        ):
            validate.driver(None)

        meta = _read_metadata(local_bucket)
        valid = dict(zip(meta["id"].astype(str), meta["valid_question"]))
        assert valid["good"] is True and valid["fresh"] is True
        assert mock_llm.call_count == 1  # only the unvalidated "fresh" was sent
        # The validate pass preserves the category the tag pass wrote.
        assert dict(zip(meta["id"].astype(str), meta["category"]))["good"] == "Science & Tech"
