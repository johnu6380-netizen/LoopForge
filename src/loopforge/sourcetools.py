"""Small helpers for treating program source code as data."""

from __future__ import annotations

import ast
import hashlib


def normalize_source(source: str) -> str | None:
    """Canonical text of a program (comments and formatting removed), or None if it won't parse.

    Two programs that differ only in whitespace, comments or quote style normalize
    to the same string, which is how the search loop spots duplicate proposals.
    """
    try:
        return ast.unparse(ast.parse(source))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def source_key(source: str) -> str:
    """A stable fingerprint of a program's normalized text."""
    text = normalize_source(source)
    if text is None:
        text = source
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def precheck(source: str) -> str | None:
    """Cheap checks before paying for a sandbox run. Returns an error message, or None if OK."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg} (line {exc.lineno})"
    except (ValueError, RecursionError, MemoryError) as exc:
        return f"{type(exc).__name__}: {exc}"
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "solve":
            return None
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "solve" for t in node.targets
        ):
            return None
    return "source does not define a function named 'solve'"
