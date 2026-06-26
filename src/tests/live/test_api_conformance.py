"""Live API conformance — opt-in drift detection (NOT run in PR CI).

Every test here is marked ``@pytest.mark.live``, so it is excluded by the default
``addopts = -m 'not live'`` and the no-network / fake-secrets guards are lifted. Run it on a
schedule or manually::

    make test ARGS="-m live"

These assert a *permissive field contract* — that the fields our source code actually consumes
are still present — rather than byte equality (live data changes daily). A failure means an
external API dropped or renamed a field we depend on. Live tests only read; they never write.

Currently covers the keyless Polymarket Gamma endpoint. Keyed sources (infer, metaculus) and the
Manifold search endpoint can be added the same way, guarded to skip when credentials/params are
unavailable.
"""

import pytest
import requests

pytestmark = pytest.mark.live

# The fields polymarket.py reads off each Gamma market (conditionId/question/outcomes/
# clobTokenIds/endDate); see sources/polymarket.py transform + _build_resolution_df.
_POLYMARKET_CONSUMED_FIELDS = ("conditionId", "question", "outcomes", "clobTokenIds")


def test_polymarket_gamma_markets_contract():
    """The Polymarket Gamma /markets payload still carries the fields we parse."""
    resp = requests.get("https://gamma-api.polymarket.com/markets?limit=20", timeout=30)
    resp.raise_for_status()
    markets = resp.json()
    assert isinstance(markets, list) and markets, "expected a non-empty list of markets"

    for market in markets:
        for field in _POLYMARKET_CONSUMED_FIELDS:
            assert field in market, f"Polymarket dropped consumed field {field!r}"
        # endDate is read with a documented fallback to events[0].endDate.
        assert "endDate" in market or market.get("events"), "no endDate or events fallback"
