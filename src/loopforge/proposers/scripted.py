"""A proposer that replays a fixed list of sources. Used by tests and demos."""

from __future__ import annotations

import random

from .base import Proposal, ProposalError


class ScriptedProposer:
    name = "scripted"

    def __init__(self, sources: list[str], descriptions: list[str] | None = None) -> None:
        self._sources = list(sources)
        self._descriptions = list(descriptions or [])
        self._next = 0
        self.parents_seen: list[str] = []  # ids of the parents the search handed us

    def propose(self, parent, archive, rng: random.Random) -> Proposal:
        self.parents_seen.append(parent.id)
        if self._next >= len(self._sources):
            raise ProposalError("scripted proposer ran out of sources")
        i = self._next
        self._next += 1
        desc = self._descriptions[i] if i < len(self._descriptions) else f"scripted #{i}"
        return Proposal(self._sources[i], desc)
