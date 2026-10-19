"""The archive: every program the search has produced, with its lineage.

Every proposal becomes a ``Program`` record, whether it worked or not. Keeping the
failures matters: they are how we report honest valid/invalid rates, and the
lineage (``parent_id``) is what the web UI will draw as a tree.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

VALID = "valid"
INVALID = "invalid"
DUPLICATE = "duplicate"  # same normalized source as an earlier program; not re-evaluated


@dataclass
class Program:
    id: str
    parent_id: str | None
    iteration: int  # 0 for the seed; proposals are numbered 1..budget
    source: str
    status: str  # VALID, INVALID or DUPLICATE
    fitness: float | None = None  # dev-set fitness; None unless valid (or a duplicate of a valid one)
    by_size: dict[str, float] = field(default_factory=dict)  # mean ratio per instance size
    mean_seconds: float | None = None
    error: str | None = None
    description: str = ""  # what the proposer says it changed
    proposer: str = ""
    duplicate_of: str | None = None
    info: dict = field(default_factory=dict)  # proposer extras (e.g. token counts)

    @property
    def is_valid(self) -> bool:
        return self.status == VALID

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Program":
        return cls(**data)


class Archive:
    def __init__(self) -> None:
        self._programs: list[Program] = []
        self._by_id: dict[str, Program] = {}
        self._by_key: dict[str, Program] = {}

    def __len__(self) -> int:
        return len(self._programs)

    def __iter__(self):
        return iter(self._programs)

    def next_id(self) -> str:
        return f"p{len(self._programs):04d}"

    def add(self, program: Program, key: str | None = None) -> None:
        """Store a program. Pass ``key`` (a source fingerprint) so later duplicates can be found."""
        if program.id in self._by_id:
            raise ValueError(f"duplicate program id {program.id}")
        self._programs.append(program)
        self._by_id[program.id] = program
        if key is not None and program.status != DUPLICATE:
            self._by_key.setdefault(key, program)

    def get(self, program_id: str) -> Program:
        return self._by_id[program_id]

    def lookup(self, key: str) -> Program | None:
        """The earlier program with this source fingerprint, if any."""
        return self._by_key.get(key)

    def valid(self) -> list[Program]:
        """Programs that can be chosen as parents."""
        return [p for p in self._programs if p.is_valid]

    def best(self) -> Program | None:
        """Lowest-fitness valid program; the earliest one wins ties."""
        best: Program | None = None
        for p in self._programs:
            if p.is_valid and (best is None or p.fitness < best.fitness):  # type: ignore[operator]
                best = p
        return best

    def children(self, program_id: str) -> list[Program]:
        return [p for p in self._programs if p.parent_id == program_id]

    def lineage(self, program_id: str) -> list[Program]:
        """The chain of ancestors from the seed down to this program."""
        chain = [self.get(program_id)]
        while chain[-1].parent_id is not None:
            chain.append(self.get(chain[-1].parent_id))  # type: ignore[arg-type]
        return chain[::-1]

    def counts(self) -> dict[str, int]:
        out = {VALID: 0, INVALID: 0, DUPLICATE: 0}
        for p in self._programs:
            out[p.status] += 1
        return out
