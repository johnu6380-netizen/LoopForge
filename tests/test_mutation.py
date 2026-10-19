import ast
import random

import pytest

from loopforge.archive import Program
from loopforge.proposers import MutationProposer, ProposalError, get_proposer
from loopforge.proposers import mutation as mut
from loopforge.seeds import load_tsp_seed_source, tsp_seed_names
from loopforge.sourcetools import normalize_source, precheck, source_key


def parent_of(name):
    return Program("p0000", None, 0, normalize_source(load_tsp_seed_source(name)), "valid", 1.0)


def apply(op, source, seed=0):
    tree = ast.parse(source)
    desc = op(tree, random.Random(seed))
    ast.fix_missing_locations(tree)
    return desc, ast.unparse(tree)


# ---------- source tools ----------


def test_normalize_ignores_comments_and_formatting():
    a = "def solve(points):\n    return [0]  # hi\n"
    b = "def solve( points ):\n\n    return   [0]\n"
    assert source_key(a) == source_key(b)


def test_normalize_returns_none_for_garbage():
    assert normalize_source("def (") is None
    assert normalize_source("x = 1\x00") is None


def test_source_key_differs_for_different_programs():
    assert source_key("def solve(p):\n    return [0]") != source_key("def solve(p):\n    return [1]")


def test_precheck():
    assert precheck("def solve(points):\n    return []") is None
    assert precheck("solve = lambda points: []") is None
    assert "SyntaxError" in precheck("def solve(points) return []")
    assert "solve" in precheck("def other(points):\n    return []")


# ---------- individual operators ----------

SAMPLE = (
    "def solve(points):\n"
    "    a = 1\n"
    "    b = 2.5\n"
    "    c = a + b\n"
    "    if a < b and c > 0:\n"
    "        a = min(a, b)\n"
    "    return list(range(len(points)))\n"
)


@pytest.mark.parametrize(
    "op", [mut._op_const, mut._op_binop, mut._op_compare, mut._op_boolop, mut._op_negate,
           mut._op_minmax, mut._op_swap_stmts, mut._op_delete_stmt, mut._op_dup_stmt,
           mut._op_name_swap, mut._op_args_swap],
)
def test_every_operator_changes_the_sample_and_stays_parseable(op):
    for seed in range(10):
        desc, out = apply(op, SAMPLE, seed)
        assert desc, f"{op.__name__} found nothing to edit in the sample"
        ast.parse(out)
        if op is not mut._op_dup_stmt:  # duplicating is allowed to be a no-op semantically
            assert source_key(out) != source_key(SAMPLE) or op is mut._op_name_swap


def test_operator_returns_none_when_nothing_to_edit():
    assert mut._op_const(ast.parse("def solve(p):\n    return p"), random.Random(0)) is None
    assert mut._op_compare(ast.parse("x = 1"), random.Random(0)) is None


def test_constants_edits_skip_booleans_and_strings():
    src = "def solve(p):\n    flag = True\n    s = 'hi'\n    return p"
    assert mut._op_const(ast.parse(src), random.Random(0)) is None


def test_delete_never_empties_a_body():
    src = "def solve(p):\n    return p"
    assert mut._op_delete_stmt(ast.parse(src), random.Random(0)) is None


# ---------- the proposer ----------


def test_proposer_is_deterministic_for_a_seed():
    parent = parent_of("nearest_neighbor")
    a = [MutationProposer().propose(parent, None, random.Random(5)).source for _ in range(1)]
    b = [MutationProposer().propose(parent, None, random.Random(5)).source for _ in range(1)]
    assert a == b


def test_proposer_sequences_differ_across_seeds():
    parent = parent_of("two_opt")
    rng1, rng2 = random.Random(1), random.Random(2)
    s1 = [MutationProposer().propose(parent, None, rng1).source for _ in range(10)]
    s2 = [MutationProposer().propose(parent, None, rng2).source for _ in range(10)]
    assert s1 != s2


@pytest.mark.parametrize("name", [n for n in tsp_seed_names()])
def test_hundreds_of_mutants_always_parse_and_differ_from_parent(name):
    parent = parent_of(name)
    rng = random.Random(0)
    proposer = MutationProposer()
    for _ in range(150):
        proposal = proposer.propose(parent, None, rng)
        ast.parse(proposal.source)
        assert source_key(proposal.source) != source_key(parent.source)
        assert proposal.description


def test_proposer_fails_cleanly_when_nothing_can_change():
    parent = Program("p0", None, 0, "x = 'a'", "valid", 1.0)
    with pytest.raises(ProposalError):
        MutationProposer().propose(parent, None, random.Random(0))


def test_registry():
    assert get_proposer("mutation").name == "mutation"
    with pytest.raises(ValueError, match="unknown proposer"):
        get_proposer("nope")
