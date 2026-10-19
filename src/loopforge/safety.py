"""A static pre-check that runs BEFORE a hand-pasted AI program is ever executed.

The sandbox (see sandbox.py) already stops buggy code. This module adds a second,
cheaper layer for the manual-experiment workflow: it reads the program's syntax tree
and refuses anything that tries to reach outside the task. A rejected program is
recorded as an invalid proposal, exactly like a program that crashes, and is never run.

Honest limit: this is a filter for accidents and obvious tricks, not a security
boundary. Always skim the code yourself before ingesting it (docs/SANDBOX.md).
"""

from __future__ import annotations

import ast
import re

from .sandbox_runner import BLOCKED_IMPORTS

# Imported modules refused on top of the sandbox's own blocklist.
EXTRA_BLOCKED_IMPORTS = frozenset(
    {
        "platform", "getpass", "webbrowser", "zipfile", "tarfile", "pydoc", "pdb", "types",
        "site", "sysconfig", "zipimport", "ensurepip", "tkinter", "turtle", "cProfile",
        "profile", "trace", "tracemalloc", "dis", "symtable", "faulthandler", "traceback",
    }
)

# Builtins a TSP heuristic never needs, and which are the usual way out of a sandbox.
FORBIDDEN_NAMES = frozenset(
    {
        "open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr",
        "globals", "locals", "vars", "input", "breakpoint", "memoryview", "exit", "quit", "help",
    }
)

# Attribute / name tricks used to climb out of restricted Python.
DANGEROUS_DUNDERS = frozenset(
    {
        "__class__", "__bases__", "__base__", "__mro__", "__subclasses__", "__globals__",
        "__builtins__", "__code__", "__closure__", "__dict__", "__getattribute__", "__loader__",
        "__spec__", "__traceback__", "__func__", "__self__", "__module__", "__reduce__",
        "__reduce_ex__", "__file__", "__import__",
    }
)
FRAME_ATTRS = frozenset(
    {
        "tb_frame", "tb_next", "f_back", "f_globals", "f_locals", "f_builtins", "f_code",
        "gi_frame", "gi_code", "cr_frame", "cr_code", "ag_frame", "ag_code",
    }
)

_FORMAT_TRICK = re.compile(r"\{[^{}]*(\.__|\[__)")
MAX_REPORTED = 6


def _check_module(name: str, line: object, problems: list[str]) -> None:
    top = name.split(".")[0]
    if top in BLOCKED_IMPORTS or top in EXTRA_BLOCKED_IMPORTS:
        problems.append(f"line {line}: import of '{top}' is not allowed")


def lint_source(source: str) -> list[str]:
    """Return human-readable reasons this program must not be run (empty list = looks fine).

    Syntax errors are not reported here; ``sourcetools.precheck`` handles those.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []

    problems: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, line, problems)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                problems.append(f"line {line}: relative imports are not allowed")
            elif node.module:
                _check_module(node.module, line, problems)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in FORBIDDEN_NAMES:
                problems.append(f"line {line}: use of '{node.id}' is not allowed")
            elif node.id in DANGEROUS_DUNDERS:
                problems.append(f"line {line}: use of '{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute):
            if node.attr in DANGEROUS_DUNDERS or node.attr in FRAME_ATTRS:
                problems.append(f"line {line}: access to '.{node.attr}' is not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _FORMAT_TRICK.search(node.value):
                problems.append(f"line {line}: attribute access inside a format string is not allowed")

    unique = list(dict.fromkeys(problems))
    if len(unique) > MAX_REPORTED:
        unique = unique[:MAX_REPORTED] + [f"... and {len(unique) - MAX_REPORTED} more"]
    return unique
