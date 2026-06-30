"""Contract: every implemented source's ``update()`` output conforms to the data schemas.

Registry-parametrized over sources with an implemented ``update()`` (see ``tests/_sources.py``).
``update()`` reaches the network in four of five sources, so the offline adapter
(``offline_update_case``) patches the resolution-building seam (``_build_resolution_df``); this
test asserts update()'s *assembly* contract, not its resolution *content*.

The two assertions are of unequal strength — read them that way:

- **dfq columns (load-bearing).** ``update()`` assembles the question frame and chooses its
  columns, so pinning it to exactly ``QUESTION_FILE_COLUMNS`` catches real column leaks/drift.
  Schemas are ``strict=False`` (see ``_schemas.py``), so ``validate()`` alone won't catch a leaked
  column — hence the explicit column-set assertion alongside it.
- **resolution files (packaging check only).** ``_build_resolution_df`` is stubbed to return a
  frame that *already* conforms, so this half does not validate real resolution construction — it
  only proves ``update()`` keys the resolution dict and passes the frame through without mangling
  its columns. Resolution *content* (the real ``_build_resolution_df`` logic) is covered in
  ``unit/sources/``.
"""

from contextlib import ExitStack

import pytest

from _schemas import QuestionFrame, ResolutionFrame
from helpers import constants
from tests._sources import IMPLEMENTED_SOURCES


@pytest.mark.parametrize("name", IMPLEMENTED_SOURCES)
def test_update_output_conforms(name, offline_update_case):
    """update() returns a QuestionFrame (exact columns) and ResolutionFrame resolution files."""
    with ExitStack() as stack:
        source, dfq, dff = offline_update_case(name, stack)
        result = source.update(dfq, dff)

    QuestionFrame.validate(result.dfq)
    # strict=False -> schema misses extra/leaked columns; pin the persisted column set exactly.
    assert list(result.dfq.columns) == constants.QUESTION_FILE_COLUMNS

    # Non-empty so the resolution-file validation below can't be silently skipped.
    assert result.resolution_files, f"{name} update() produced no resolution files"
    for question_id, df in result.resolution_files.items():
        ResolutionFrame.validate(df)
        assert list(df.columns) == ["id", "date", "value"], question_id
