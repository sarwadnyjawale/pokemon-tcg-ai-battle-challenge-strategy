"""ptcgabc — Pokémon TCG AI Battle Challenge, Phase-1 foundation codebase."""

__version__ = "0.1.0"

from . import agent, contracts, data, errors, experiments, provenance, reproduce, simulator

__all__ = [
    "contracts",
    "data",
    "errors",
    "experiments",
    "provenance",
    "reproduce",
    "simulator",
    "agent",
]