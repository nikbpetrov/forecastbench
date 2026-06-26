"""Shared pytest fixtures for ForecastBench tests (builders live in factories.py)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from sources.acled import AcledSource
from sources.fred import FredSource
from sources.infer import InferSource
from sources.manifold import ManifoldSource
from sources.metaculus import MetaculusSource
from sources.polymarket import PolymarketSource
from sources.yfinance import YfinanceSource

# ---------------------------------------------------------------------------
# Time-freezing fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def freeze_today():
    """Patch dates.get_date_today() and get_date_yesterday() to return deterministic values.

    Usage:
        def test_something(freeze_today):
            freeze_today(date(2025, 1, 15))
            # Now dates.get_date_today() returns date(2025, 1, 15)
            # and dates.get_date_yesterday() returns date(2025, 1, 14)
    """
    patches = []

    def _freeze(target_date):
        target_datetime = datetime(
            target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc
        )
        p1 = patch("helpers.dates.get_date_today", return_value=target_date)
        p2 = patch("helpers.dates.get_date_yesterday", return_value=target_date - timedelta(days=1))
        p3 = patch("helpers.dates.get_datetime_today", return_value=target_datetime)
        patches.extend([p1, p2, p3])
        for p in [p1, p2, p3]:
            p.start()

    yield _freeze

    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# Source instance fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def market_source():
    """Return a concrete MarketSource instance."""
    return MetaculusSource()


@pytest.fixture()
def dataset_source():
    """Return a concrete DatasetSource instance."""
    return FredSource()


@pytest.fixture()
def acled_source():
    """Return an AcledSource instance."""
    return AcledSource()


@pytest.fixture()
def infer_source():
    """Return an InferSource instance with a fake API key."""
    src = InferSource()
    src.api_key = "test-key"
    return src


@pytest.fixture()
def manifold_source():
    """Return a ManifoldSource instance."""
    return ManifoldSource()


@pytest.fixture()
def metaculus_source():
    """Return a MetaculusSource instance with a fake API key."""
    src = MetaculusSource()
    src.api_key = "test-key"
    return src


@pytest.fixture()
def polymarket_source():
    """Return a PolymarketSource instance."""
    return PolymarketSource()


@pytest.fixture()
def yfinance_source():
    """Return a YfinanceSource instance."""
    return YfinanceSource()


# ---------------------------------------------------------------------------
# Offline harness: no-network guard, fake secrets, local bucket mount
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _guard_network(request):
    """Block non-local network access for every test unless marked ``live``.

    An accidentally-unmocked HTTP call should fail loudly and deterministically rather than
    reach a live API. Tests that truly need the network use ``@pytest.mark.live``.
    """
    from tests._harness import network

    if request.node.get_closest_marker("live"):
        yield
        return
    network.install()
    try:
        yield
    finally:
        network.uninstall()


@pytest.fixture(autouse=True)
def _fake_secrets(request):
    """Ensure secret access never hits Secret Manager during tests.

    ``helpers.keys`` resolves secrets lazily; here we patch the resolver to return a
    deterministic dummy and clear its cache, so any ``keys.API_KEY_*`` access is offline-safe
    even for code paths that read a key we didn't explicitly set. Skipped for ``@pytest.mark.live``
    tests, which need real secrets.
    """
    if request.node.get_closest_marker("live"):
        yield
        return

    from helpers import keys

    keys._cache.clear()
    with patch.object(keys, "get_secret", side_effect=lambda name, *a, **k: f"fake-{name}"):
        yield
    keys._cache.clear()


@pytest.fixture()
def local_bucket(tmp_path, monkeypatch):
    """Provide a temp-dir-backed stand-in for the project's GCS buckets.

    Sets ``BUCKET_MOUNT_POINT`` and the ``*_BUCKET`` env vars so that all
    ``utils.gcp.storage`` operations read/write the temp tree instead of GCS. Returns a
    ``LocalBucket`` with helpers to seed inputs and read outputs using the real filename
    conventions.
    """
    from tests._harness.buckets import LocalBucket, apply_env

    bucket = LocalBucket(tmp_path / "buckets")
    apply_env(monkeypatch, bucket.env())
    return bucket


# ---------------------------------------------------------------------------
# Source-contract helpers: fresh instances + offline update() adapter
# ---------------------------------------------------------------------------


def empty_question_bank():
    """Return an empty question bank with the canonical QuestionFrame columns (prod read shape)."""
    import pandas as pd

    from helpers import constants

    return pd.DataFrame(columns=constants.QUESTION_FILE_COLUMNS)


@pytest.fixture()
def fresh_source():
    """Build a fresh source instance (never the registry singleton) for mutating tests.

    Sources carry mutable state (``api_key``, ``ticker_renames``); registry singletons must not
    be mutated across tests.
    """
    from sources import registry

    classes = {s.name: type(s) for s in registry.SOURCES.values()}

    def _make(name):
        src = classes[name]()
        if name in ("metaculus", "infer"):
            src.api_key = "test-key"
        if name == "yfinance":
            src.ticker_renames = []  # else update() fetches replacement tickers
        return src

    return _make


@pytest.fixture()
def offline_update_case(fresh_source):
    """Return a builder ``_case(name, stack) -> (source, dfq, dff)`` for an offline update() call.

    ``update()`` builds resolution data via the network in four of five sources; patching the
    common ``_build_resolution_df`` seam (present in all five) plus ``_get_market``
    (manifold/metaculus) makes the call run offline. This exercises update()'s *assembly* contract
    (dfq schema + exact columns, resolution_files packaging); resolution *content* is stubbed and
    asserted elsewhere. The caller supplies a ``contextlib.ExitStack`` so patches unwind cleanly.
    """
    from tests import factories as f

    fetch_builders = {
        "polymarket": lambda: f.make_polymarket_fetch_df(
            [{"id": "m1", "historical_prices": [{"date": "2024-06-01", "value": 0.5}]}]
        ),
        "infer": lambda: f.make_infer_fetch_df([{"id": "i1"}]),
        "yfinance": lambda: f.make_yfinance_fetch_df([{"id": "AAPL"}]),
        "manifold": lambda: f.make_manifold_fetch_df([{"id": "mkt1"}]),
        "metaculus": lambda: f.make_metaculus_fetch_df(["mkt1"]),
    }

    def _case(name, stack):
        src = fresh_source(name)
        res = f.make_resolution_df([{"id": "x", "date": "2024-06-01", "value": 0.5}])
        stack.enter_context(patch.object(type(src), "_build_resolution_df", return_value=res))
        if name == "manifold":
            stack.enter_context(
                patch.object(
                    type(src), "_get_market", return_value=f.make_manifold_api_market(id="mkt1")
                )
            )
        if name == "metaculus":
            stack.enter_context(
                patch.object(
                    type(src), "_get_market", return_value=f.make_metaculus_market(id="mkt1")
                )
            )
        return src, empty_question_bank(), fetch_builders[name]()

    return _case
