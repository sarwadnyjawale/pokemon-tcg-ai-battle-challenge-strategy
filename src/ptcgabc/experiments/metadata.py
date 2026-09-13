"""Experiment metadata + reproducibility schema (blueprint §15, §16 / PROBLEM 8).

The experiment_file JSON contract is the canonical record for every run.
Evaluation results must carry enough provenance to answer, with evidence:
  - whose deck, which model version, which gym/sim, which opponents, how many games,
  - the win/loss numbers, the seed, the fallback rate, the runtime, the git commit.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..contracts import EvaluationResult
from ..provenance import (EnvironmentType, ResultSource, UnsupportedEvidenceError,
                          assert_gameplay_evidence, describe_source)


@dataclass
class DeckRecord:
    agent_name: str
    deck_csv: str
    deck_sha256: str
    deck_cards: list[int] = field(default_factory=list)


@dataclass
class ExperimentFile:
    experiment_id: str
    created_at: str
    git_commit: str = ""
    python_version: str = ""
    platform: str = ""
    environment: str = EnvironmentType.MOCK.value
    source: str = ResultSource.LOCAL_EXPERIMENT.value
    phase: str = "phase1"
    model: str = ""                       # model variant name
    version: str = "0.0.1"
    deck: DeckRecord = field(default_factory=DeckRecord)
    opponents: list[str] = field(default_factory=list)
    games: int = 0
    wins: int = 0
    win_rate: float | None = None
    ci: dict[str, float] | None = None
    seed: int | None = None
    fallback_rate: float | None = None
    runtime_seconds: float | None = None
    notes: str = ""
    raw_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["deck"] = {
            "agent_name": self.deck.agent_name,
            "deck_csv": self.deck.deck_csv,
            "deck_sha256": self.deck.deck_sha256,
            "deck_cards": list(self.deck.deck_cards),
        }
        return d

    @staticmethod
    def from_evaluation(
        result: EvaluationResult,
        *,
        experiment_id: str,
        git_commit: str,
        phase: str = "phase1",
    ) -> "ExperimentFile":
        assert_gameplay_evidence(EnvironmentType(result.environment), result.source)
        return ExperimentFile(
            experiment_id=experiment_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            git_commit=git_commit,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            platform=socket.platform(),
            environment=result.environment,
            source=result.source,
            phase=phase,
            games=result.games,
            wins=result.wins,
            win_rate=result.win_rate,
            ci=result.ci,
            seed=result.seed,
            fallback_rate=result.fallback_rate,
            runtime_seconds=result.runtime_s,
        )

    def validate(self) -> "ExperimentFile":
        describe_source()  # confirms no official Simulation claims are on record
        if not self.experiment_id:
            raise ValueError("experiment_id required")
        if self.games > 0 and not (0 <= self.wins <= self.games):
            raise ValueError(f"wins {self.wins} inconsistent with games {self.games}")
        if self.environment not in ("MOCK", "VERIFIED_REAL", "REAL_SIMULATOR_UNAVAILABLE"):
            raise ValueError(f"unknown environment {self.environment!r}")
        return self


def write_experiment_file(exp: ExperimentFile, out_path: Path) -> Path:
    exp.validate()
    out_path.write_text(json.dumps(exp.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def experiment_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()