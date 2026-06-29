"""Layer 3: thin driver() wiring tests for orchestration entry points.

These run the real ``orchestration/func_*/main.py:driver()`` against a ``local_bucket`` mount
(no GCP), proving the IO wiring connects: read inputs -> call the source -> write outputs. The
*wiring* contract is uniform across the implemented sources, so it is **parametrized** over
``IMPLEMENTED_SOURCES`` (derived from the registry in ``tests/_sources.py``).

Source behaviour (parse/update logic) is NOT tested here — that lives in ``unit/sources/`` and
``contract/test_update_conformance.py``. ``fetch()``/``update()`` are mocked so these stay pure
wiring checks.

Divergences are handled with a narrower test *in this file* (see README "integration"):

- **Stateless fetch.** ``manifold``/``metaculus`` fetch drivers call ``fetch()`` with no args
  (they don't read the question bank), so the "passes the existing bank" assertion is scoped to
  ``BANK_READING_FETCH`` only.
- **Pure update.** Only ``polymarket.update()`` makes no network calls, so it is run *unmocked*
  in ``TestPolymarketUpdateRealChain`` to prove the whole read -> update -> write chain for real;
  the other four are covered by the mocked, parametrized wiring test.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from _fb_types import UpdateResult
from orchestration.func_infer_fetch.main import driver as infer_fetch
from orchestration.func_infer_update.main import driver as infer_update
from orchestration.func_manifold_fetch.main import driver as manifold_fetch
from orchestration.func_manifold_update.main import driver as manifold_update
from orchestration.func_metaculus_fetch.main import driver as metaculus_fetch
from orchestration.func_metaculus_update.main import driver as metaculus_update
from orchestration.func_polymarket_fetch.main import driver as polymarket_fetch
from orchestration.func_polymarket_update.main import driver as polymarket_update
from orchestration.func_yfinance_fetch.main import driver as yfinance_fetch
from orchestration.func_yfinance_update.main import driver as yfinance_update
from sources.registry import SOURCES
from tests._sources import IMPLEMENTED_SOURCES
from tests.factories import (
    make_polymarket_fetch_df,
    make_question_df,
    make_resolution_df,
)

FETCH_DRIVERS = {
    "infer": infer_fetch,
    "manifold": manifold_fetch,
    "metaculus": metaculus_fetch,
    "polymarket": polymarket_fetch,
    "yfinance": yfinance_fetch,
}
UPDATE_DRIVERS = {
    "infer": infer_update,
    "manifold": manifold_update,
    "metaculus": metaculus_update,
    "polymarket": polymarket_update,
    "yfinance": yfinance_update,
}
# Fetch drivers that read the existing bank and feed it to fetch(dfq=...). manifold/metaculus
# diverge: they fetch all IDs fresh via a stateless fetch() and are excluded from that assertion.
BANK_READING_FETCH = ["infer", "polymarket", "yfinance"]


class TestFetchDriverWiring:
    """Every fetch driver: read bank (if applicable) -> fetch() -> write <source>_fetch.jsonl."""

    @pytest.mark.parametrize("name", IMPLEMENTED_SOURCES)
    def test_writes_fetch_output(self, name, local_bucket):
        local_bucket.seed_questions(name, [])  # ignored by the stateless fetch drivers
        fetched = pd.DataFrame([{"id": "x1"}, {"id": "x2"}])

        with patch.object(type(SOURCES[name]), "fetch", return_value=fetched) as mock_fetch:
            FETCH_DRIVERS[name](None)

        assert mock_fetch.called
        out = local_bucket.read_fetch(name)
        assert sorted(out["id"].astype(str)) == ["x1", "x2"]

    @pytest.mark.parametrize("name", BANK_READING_FETCH)
    def test_passes_existing_bank_to_fetch(self, name, local_bucket):
        """Bank-reading drivers pass the existing question bank as fetch(dfq=...)."""
        local_bucket.seed_questions(name, [])
        with patch.object(
            type(SOURCES[name]), "fetch", return_value=pd.DataFrame([{"id": "x1"}])
        ) as mock_fetch:
            FETCH_DRIVERS[name](None)
        assert "dfq" in mock_fetch.call_args.kwargs


class TestUpdateDriverWiring:
    """Every update driver: read bank + fetch -> update() -> persist questions + resolution files.

    update() is mocked (it reaches the network in four of five sources); this asserts only that the
    driver persists what update() returns. update()'s assembly contract lives in
    contract/test_update_conformance.py.
    """

    @pytest.mark.parametrize("name", IMPLEMENTED_SOURCES)
    def test_persists_questions_and_resolution(self, name, local_bucket):
        local_bucket.seed_questions(name, [{"id": "existing"}])  # the bank the driver must read
        local_bucket.seed_fetch(name, [{"id": "m1"}])  # the fetch the driver must read
        canned = UpdateResult(
            dfq=make_question_df([{"id": "m1"}]),
            resolution_files={
                "m1": make_resolution_df([{"id": "m1", "date": "2025-01-01", "value": 0.5}])
            },
        )

        with patch.object(type(SOURCES[name]), "update", return_value=canned) as mock_update:
            UPDATE_DRIVERS[name](None)

        # The driver read the bucket inputs and fed them to update() positionally: dfq then dff —
        # a driver that ignored the bank/fetch would still persist, so assert the wiring both ways.
        dfq_arg, dff_arg = mock_update.call_args.args[0], mock_update.call_args.args[1]
        assert "existing" in dfq_arg["id"].astype(str).tolist()
        assert "m1" in dff_arg["id"].astype(str).tolist()
        # ...and it persisted what update() returned.
        questions = local_bucket.read_questions(name)
        assert "m1" in questions["id"].astype(str).tolist()
        res = local_bucket.read_resolution_file(name, "m1")
        assert list(res.columns) == ["id", "date", "value"]


class TestPolymarketUpdateRealChain:
    """Divergence: polymarket.update() is the only pure update, so run it unmocked.

    This proves the full read -> update -> write chain end to end (real update + real IO), which the
    mocked parametrized test above cannot. The other four sources fetch inside update(), so their
    update() behaviour is covered offline in contract/test_update_conformance.py instead.
    """

    def test_writes_questions_and_resolution_files(self, local_bucket):
        local_bucket.seed_questions("polymarket", [])
        fetched = make_polymarket_fetch_df(
            [
                {
                    "id": "m1",
                    "historical_prices": [
                        {"date": "2024-06-01", "value": 0.4},
                        {"date": "2024-06-02", "value": 0.6},
                    ],
                }
            ]
        )
        local_bucket.seed_fetch("polymarket", fetched.to_dict("records"))

        polymarket_update(None)

        # Question upserted into the bank.
        questions = local_bucket.read_questions("polymarket")
        assert "m1" in questions["id"].astype(str).tolist()
        # Transient fetch-only columns are stripped before persisting.
        assert "historical_prices" not in questions.columns
        assert "probability" not in questions.columns

        # Resolution file written with canonical columns and both dates.
        res = local_bucket.read_resolution_file("polymarket", "m1")
        assert list(res.columns) == ["id", "date", "value"]
        assert len(res) == 2

    def test_existing_question_is_upserted_not_duplicated(self, local_bucket):
        existing = make_question_df([{"id": "m1", "source": "polymarket", "question": "old?"}])
        local_bucket.seed_questions("polymarket", existing.to_dict("records"))
        fetched = make_polymarket_fetch_df(
            [
                {
                    "id": "m1",
                    "question": "new?",
                    "historical_prices": [{"date": "2024-06-01", "value": 0.5}],
                }
            ]
        )
        local_bucket.seed_fetch("polymarket", fetched.to_dict("records"))

        polymarket_update(None)

        questions = local_bucket.read_questions("polymarket")
        ids = questions["id"].astype(str).tolist()
        assert ids.count("m1") == 1  # upserted, not duplicated
        assert isinstance(questions, pd.DataFrame)
