"""Reproducibility: deterministic seeding + dependency/env snapshot (blueprint §17)."""

from __future__ import annotations

import hashlib
import json
import platform
import random
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy


@dataclass
class SeedSet:
    """Explicit record of every seed used in a run."""

    python_seed: int
    numpy_seed: int
    torch_seed: int | None = None
    simulator_seed: int | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "python_seed": self.python_seed,
            "numpy_seed": self.numpy_seed,
            "torch_seed": self.torch_seed,
            "simulator_seed": self.simulator_seed,
            "extra": dict(self.extra),
        }


def seed_everything(seed: int, simulator_seed: int | None = None) -> SeedSet:
    """Seed Python + NumPy (+ torch if importable) and return the explicit record."""
    random.seed(seed)
    numpy.random.seed(seed)
    torch_seed = None
    try:
        import torch  # type: ignore

        torch.manual_seed(seed)
        torch_seed = seed
    except ImportError:
        torch_seed = None
    return SeedSet(
        python_seed=seed,
        numpy_seed=seed,
        torch_seed=torch_seed,
        simulator_seed=simulator_seed,
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return out.stdout.strip()
    except Exception:
        return "NO_GIT"


def environment_snapshot() -> dict:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy_version": numpy.__version__,
        "git_commit": git_commit(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def hash_record(path: Path) -> dict:
    st = path.stat()
    return {
        "file": str(path),
        "sha256": sha256_file(path),
        "size_bytes": st.st_size,
    }


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")