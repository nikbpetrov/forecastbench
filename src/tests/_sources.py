"""Registry-derived source lists for parametrized contract/integration tests.

Sources whose ``fetch()`` / ``update()`` are still ``raise NotImplementedError`` stubs are
excluded from cross-source parametrization. Detection is static (AST), not runtime calls,
so importing this module never hits the network.

When every registry source is implemented, delete ``implemented_sources()`` and set
``IMPLEMENTED_SOURCES = sorted(SOURCES)`` instead.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Callable

from sources.registry import SOURCES


def _is_not_implemented_stub(method: Callable) -> bool:
    """Return True if ``method``'s body is only ``raise NotImplementedError``."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    except (OSError, TypeError, SyntaxError):
        return False

    func_def = tree.body[0]
    if not isinstance(func_def, ast.FunctionDef):
        return False

    stmts = func_def.body
    if (
        stmts
        and isinstance(stmts[0], ast.Expr)
        and isinstance(getattr(stmts[0], "value", None), ast.Constant)
        and isinstance(stmts[0].value.value, str)
    ):
        stmts = stmts[1:]

    if len(stmts) != 1 or not isinstance(stmts[0], ast.Raise):
        return False

    exc = stmts[0].exc
    if exc is None:
        return True
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id == "NotImplementedError"
    return False


def implemented_sources() -> list[str]:
    """Return registry sources with real ``fetch()`` and ``update()`` implementations."""
    return sorted(
        name
        for name, src in SOURCES.items()
        if not _is_not_implemented_stub(type(src).fetch)
        and not _is_not_implemented_stub(type(src).update)
    )


IMPLEMENTED_SOURCES = implemented_sources()
STUB_SOURCES = sorted(set(SOURCES) - set(IMPLEMENTED_SOURCES))
