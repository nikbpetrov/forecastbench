"""Contract: stub sources fail loudly; implemented sources are derived from the registry."""

import pytest

from sources.registry import SOURCES
from tests._sources import IMPLEMENTED_SOURCES, STUB_SOURCES


def test_implemented_and_stub_sources_partition_registry():
    """Every registry source is implemented or stubbed; none are both."""
    assert set(IMPLEMENTED_SOURCES) | set(STUB_SOURCES) == set(SOURCES)
    assert not (set(IMPLEMENTED_SOURCES) & set(STUB_SOURCES))


@pytest.mark.parametrize("name", STUB_SOURCES)
def test_stub_source_update_raises_not_implemented(name):
    """Stubbed sources fail loudly rather than silently producing empty output."""
    with pytest.raises(NotImplementedError):
        SOURCES[name].update(None, None)
