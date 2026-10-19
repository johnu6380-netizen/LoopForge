import pytest

from loopforge.archive import DUPLICATE, INVALID, VALID, Archive, Program


def prog(pid, parent, status=VALID, fitness=None, iteration=0):
    return Program(pid, parent, iteration, f"# {pid}", status, fitness)


def build():
    a = Archive()
    a.add(prog("p0000", None, fitness=1.15))
    a.add(prog("p0001", "p0000", fitness=1.10, iteration=1))
    a.add(prog("p0002", "p0000", INVALID, iteration=2))
    a.add(prog("p0003", "p0001", fitness=1.12, iteration=3))
    a.add(prog("p0004", "p0003", DUPLICATE, 1.12, iteration=4))
    return a


def test_ids_are_sequential():
    a = Archive()
    assert a.next_id() == "p0000"
    a.add(prog("p0000", None, fitness=1.0))
    assert a.next_id() == "p0001"


def test_best_ignores_invalid_and_duplicates():
    a = build()
    a.add(prog("p0005", "p0001", DUPLICATE, 0.5, iteration=5))  # duplicate with a "better" copied score
    assert a.best().id == "p0001"


def test_best_tie_goes_to_earliest():
    a = Archive()
    a.add(prog("p0000", None, fitness=1.0))
    a.add(prog("p0001", "p0000", fitness=1.0, iteration=1))
    assert a.best().id == "p0000"


def test_valid_excludes_invalid_and_duplicates():
    assert [p.id for p in build().valid()] == ["p0000", "p0001", "p0003"]


def test_counts():
    assert build().counts() == {VALID: 3, INVALID: 1, DUPLICATE: 1}


def test_children_and_lineage():
    a = build()
    assert [p.id for p in a.children("p0000")] == ["p0001", "p0002"]
    assert [p.id for p in a.lineage("p0004")] == ["p0000", "p0001", "p0003", "p0004"]
    assert [p.id for p in a.lineage("p0000")] == ["p0000"]


def test_lookup_finds_first_program_with_a_key():
    a = Archive()
    first = prog("p0000", None, fitness=1.0)
    a.add(first, key="k")
    a.add(prog("p0001", "p0000", DUPLICATE, 1.0, iteration=1), key="k")
    assert a.lookup("k") is first
    assert a.lookup("missing") is None


def test_duplicate_ids_rejected():
    a = Archive()
    a.add(prog("p0000", None, fitness=1.0))
    with pytest.raises(ValueError):
        a.add(prog("p0000", None, fitness=1.0))


def test_program_round_trips_through_dict():
    p = Program("p1", "p0", 3, "x", VALID, 1.1, {"25": 1.1}, 0.01, None, "desc", "mutation", None, {"tokens": 5})
    assert Program.from_dict(p.to_dict()) == p
