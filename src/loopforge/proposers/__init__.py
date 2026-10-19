"""Proposers turn a parent program into a new candidate program."""

from .base import Proposal, ProposalError, Proposer
from .llm import LLMProposer, build_llm_proposer
from .mutation import MutationProposer
from .scripted import ScriptedProposer

PROPOSERS = {"mutation": MutationProposer}  # "llm" is built separately: it needs configuration


def get_proposer(name: str, options: dict | None = None) -> Proposer:
    if name == "llm":
        return build_llm_proposer(options)
    try:
        return PROPOSERS[name]()
    except KeyError:
        available = sorted([*PROPOSERS, "llm"])
        raise ValueError(f"unknown proposer {name!r}; available: {available}") from None


__all__ = [
    "LLMProposer", "MutationProposer", "PROPOSERS", "Proposal", "ProposalError", "Proposer",
    "ScriptedProposer", "build_llm_proposer", "get_proposer",
]
