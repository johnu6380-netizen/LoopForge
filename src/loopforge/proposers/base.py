"""The proposer interface: anything that can turn a parent program into a new candidate.

The search loop only knows this interface. The offline mutation proposer and the
LLM proposer (Stage 4) are interchangeable implementations of it, which is what
lets us compare them fairly.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..archive import Archive, Program


class ProposalError(Exception):
    """The proposer could not produce a candidate this time (counts against the budget)."""


@dataclass
class Proposal:
    source: str
    description: str = ""  # human-readable summary of the change
    info: dict = field(default_factory=dict)  # extras to log, e.g. token usage


class Proposer(Protocol):
    name: str

    def propose(self, parent: "Program", archive: "Archive", rng: random.Random) -> Proposal:
        """Return a new program derived from ``parent``. Raise ProposalError on failure."""
        ...
