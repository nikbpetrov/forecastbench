"""Contract test for the dbnomics source stub.

dbnomics is not yet refactored: ``fetch()``/``update()`` are intentional ``NotImplementedError``
stubs. This pins that contract so the gap is explicit and a future implementation replaces a
failing-by-design test rather than silently filling a hole.
"""

import pytest

from sources.dbnomics import DbnomicsSource


def test_fetch_not_implemented():
    """dbnomics.fetch() is a stub until the source is refactored."""
    with pytest.raises(NotImplementedError):
        DbnomicsSource().fetch()


def test_update_not_implemented():
    """dbnomics.update() is a stub until the source is refactored."""
    with pytest.raises(NotImplementedError):
        DbnomicsSource().update(dfq=None, dff=None)
