"""The offline proposer: random mutations of the program's syntax tree.

This is the "no intelligence" baseline. It knows nothing about TSP or about what
the code means; it just makes small random edits that are always syntactically
valid (change a constant, flip a comparison, swap two statements, ...). Most
edits break the program or change nothing. Whatever the LLM achieves has to be
measured against this.

Every mutation is deterministic given the ``random.Random`` it is handed.
"""

from __future__ import annotations

import ast
import copy
import random

from ..sourcetools import source_key
from .base import Proposal, ProposalError

MAX_ATTEMPTS = 20

_SYMBOLS = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//",
    ast.Mod: "%", ast.Pow: "**", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">",
    ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=", ast.In: "in", ast.NotIn: "not in",
    ast.Is: "is", ast.IsNot: "is not", ast.And: "and", ast.Or: "or",
}
_ARITH = [ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow]
_CMP_GROUPS = [
    [ast.Lt, ast.LtE, ast.Gt, ast.GtE],
    [ast.Eq, ast.NotEq],
    [ast.In, ast.NotIn],
    [ast.Is, ast.IsNot],
]
_NAME_SWAPS = {"min": "max", "max": "min", "any": "all", "all": "any"}


def _sym(op: ast.AST) -> str:
    return _SYMBOLS.get(type(op), type(op).__name__)


def _line(node: ast.AST) -> object:
    return getattr(node, "lineno", "?")


def _stmt_lists(tree: ast.AST) -> list[list[ast.stmt]]:
    """Every list of statements below module level (function, loop and branch bodies)."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            continue
        for fld in ("body", "orelse", "finalbody"):
            lst = getattr(node, fld, None)
            if isinstance(lst, list) and lst and isinstance(lst[0], ast.stmt):
                out.append(lst)
    return out


# Each operator takes (tree, rng), edits the tree in place, and returns a short
# description of the edit, or None if the tree has nothing it can edit.


def _op_const(tree, rng):
    sites = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) in (int, float)]
    if not sites:
        return None
    node = rng.choice(sites)
    old = node.value
    if isinstance(old, int):
        options = {old + 1, old - 1, old + 2, old * 2, old // 2, 0, 1, -old}
        options.discard(old)
        new = rng.choice(sorted(options))
    else:
        new = round(rng.choice([old * 0.5, old * 0.9, old * 1.1, old * 2.0, old + 0.1, old - 0.1]), 6)
        if new == old:
            new = old + 1.0
    node.value = new
    return f"const: {old} -> {new} (line {_line(node)})"


def _op_binop(tree, rng):
    sites = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.BinOp, ast.AugAssign)) and type(n.op) in _ARITH
    ]
    if not sites:
        return None
    node = rng.choice(sites)
    old = node.op
    new = rng.choice([o for o in _ARITH if o is not type(old)])()
    node.op = new
    return f"operator: {_sym(old)} -> {_sym(new)} (line {_line(node)})"


def _op_compare(tree, rng):
    sites = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare):
            for idx, op in enumerate(n.ops):
                for group in _CMP_GROUPS:
                    if type(op) in group:
                        sites.append((n, idx, group))
    if not sites:
        return None
    node, idx, group = rng.choice(sites)
    old = node.ops[idx]
    new = rng.choice([c for c in group if c is not type(old)])()
    node.ops[idx] = new
    return f"comparison: {_sym(old)} -> {_sym(new)} (line {_line(node)})"


def _op_boolop(tree, rng):
    sites = [n for n in ast.walk(tree) if isinstance(n, ast.BoolOp)]
    if not sites:
        return None
    node = rng.choice(sites)
    old = node.op
    node.op = ast.Or() if isinstance(old, ast.And) else ast.And()
    return f"boolean: {_sym(old)} -> {_sym(node.op)} (line {_line(node)})"


def _op_negate(tree, rng):
    sites = [n for n in ast.walk(tree) if isinstance(n, (ast.If, ast.IfExp))]
    if not sites:
        return None
    node = rng.choice(sites)
    if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
        node.test = node.test.operand
    else:
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    return f"negate condition (line {_line(node)})"


def _op_minmax(tree, rng):
    sites = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in _NAME_SWAPS
    ]
    if not sites:
        return None
    node = rng.choice(sites)
    old = node.id
    node.id = _NAME_SWAPS[old]
    return f"function: {old} -> {node.id} (line {_line(node)})"


def _op_swap_stmts(tree, rng):
    sites = [lst for lst in _stmt_lists(tree) if len(lst) >= 2]
    if not sites:
        return None
    lst = rng.choice(sites)
    i = rng.randrange(len(lst) - 1)
    a, b = _line(lst[i]), _line(lst[i + 1])
    lst[i], lst[i + 1] = lst[i + 1], lst[i]
    return f"swap statements (lines {a} and {b})"


def _op_delete_stmt(tree, rng):
    sites = [lst for lst in _stmt_lists(tree) if len(lst) >= 2]
    if not sites:
        return None
    lst = rng.choice(sites)
    i = rng.randrange(len(lst))
    line = _line(lst[i])
    del lst[i]
    return f"delete statement (line {line})"


def _op_dup_stmt(tree, rng):
    sites = _stmt_lists(tree)
    if not sites:
        return None
    lst = rng.choice(sites)
    i = rng.randrange(len(lst))
    lst.insert(i + 1, copy.deepcopy(lst[i]))
    return f"duplicate statement (line {_line(lst[i])})"


def _op_name_swap(tree, rng):
    sites = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        bound = {a.arg for a in ast.walk(fn) if isinstance(a, ast.arg)}
        bound |= {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        if len(bound) < 2:
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in bound:
                sites.append((n, bound))
    if not sites:
        return None
    node, bound = rng.choice(sites)
    old = node.id
    node.id = rng.choice(sorted(bound - {old}))
    return f"variable: {old} -> {node.id} (line {_line(node)})"


def _op_args_swap(tree, rng):
    sites = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and len(n.args) >= 2 and not any(isinstance(a, ast.Starred) for a in n.args)
    ]
    if not sites:
        return None
    node = rng.choice(sites)
    i = rng.randrange(len(node.args) - 1)
    node.args[i], node.args[i + 1] = node.args[i + 1], node.args[i]
    return f"swap call arguments (line {_line(node)})"


# (name, weight, function)
OPERATORS = [
    ("const", 3, _op_const),
    ("binop", 2, _op_binop),
    ("compare", 2, _op_compare),
    ("boolop", 1, _op_boolop),
    ("negate", 1, _op_negate),
    ("minmax", 1, _op_minmax),
    ("swap_stmts", 2, _op_swap_stmts),
    ("delete_stmt", 2, _op_delete_stmt),
    ("dup_stmt", 1, _op_dup_stmt),
    ("name_swap", 3, _op_name_swap),
    ("args_swap", 1, _op_args_swap),
]


def apply_random_operator(tree: ast.AST, rng: random.Random) -> str | None:
    """Apply one randomly chosen operator that has something to edit; return its description."""
    pool = list(OPERATORS)
    while pool:
        idx = rng.choices(range(len(pool)), weights=[w for _, w, _ in pool])[0]
        _, _, fn = pool.pop(idx)
        description = fn(tree, rng)
        if description:
            return description
    return None


class MutationProposer:
    name = "mutation"

    def propose(self, parent, archive, rng: random.Random) -> Proposal:
        try:
            parent_tree = ast.parse(parent.source)
        except SyntaxError as exc:
            raise ProposalError(f"parent does not parse: {exc}") from exc
        parent_key = source_key(parent.source)

        for _ in range(MAX_ATTEMPTS):
            tree = copy.deepcopy(parent_tree)
            steps = 1 + (rng.random() < 0.3)  # usually one edit, sometimes two
            descriptions = []
            for _ in range(steps):
                d = apply_random_operator(tree, rng)
                if d:
                    descriptions.append(d)
            if not descriptions:
                continue
            ast.fix_missing_locations(tree)
            source = ast.unparse(tree)
            if source_key(source) != parent_key:  # skip edits that changed nothing
                return Proposal(source, "; ".join(descriptions))
        raise ProposalError("could not produce a program different from its parent")
