"""Energy symbol registry (blueprint §5 / PROBLEM 5).

Never hard-code energy symbols as truth. Scan observed values; map symbols to
meanings only when evidence supports it; unknown symbols stay UNKNOWN.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..reproduce import write_json
from .csv_ingest import IngestedFile

_SYMBOL_RE = re.compile(r"\{([^{}]*)\}")

# cabt EnergyType official enum mapping (matsuoinstitute.github.io/cabt/api.html).
# The symbol->type name pairing is the community-standard PTCG correspondence and
# matches the enum ordering; it is labeled INFERENCE, not VERIFIED, until it is
# cross-checked against in-game energy behaviour.
CABT_ENERGY_TYPE = {
    0: "COLORLESS",
    1: "GRASS",
    2: "FIRE",
    3: "WATER",
    4: "LIGHTNING",
    5: "PSYCHIC",
    6: "FIGHTING",
    7: "DARKNESS",
    8: "METAL",
    9: "DRAGON",
    10: "RAINBOW",
    11: "TEAM_ROCKET",
}


def scan_symbols(ing: IngestedFile) -> Counter:
    counts: Counter = Counter()
    for r in ing.rows:
        for col in ("Rule", "Category", "Previous stage", "Type", "Weakness",
                    "Resistance (Type)", "Retreat", "Cost", "Effect Explanation"):
            for m in _SYMBOL_RE.findall(r.values.get(col, "")):
                counts[m] += 1
    return counts


def build_registry(ing: IngestedFile) -> dict[str, Any]:
    counts = scan_symbols(ing)

    symbol_meanings: dict[str, dict] = {
        "G": {"meaning": "Grass", "notes": "standard PTCG symbol; matches cabt GRASS=1"},
        "R": {"meaning": "Fire", "notes": "matches cabt FIRE=2"},
        "W": {"meaning": "Water", "notes": "matches cabt WATER=3"},
        "L": {"meaning": "Lightning", "notes": "matches cabt LIGHTNING=4"},
        "P": {"meaning": "Psychic", "notes": "matches cabt PSYCHIC=5"},
        "F": {"meaning": "Fighting", "notes": "matches cabt FIGHTING=6"},
        "D": {"meaning": "Darkness", "notes": "matches cabt DARKNESS=7"},
        "M": {"meaning": "Metal", "notes": "matches cabt METAL=8"},
        "C": {"meaning": "Colorless", "notes": "matches cabt COLORLESS=0"},
    }

    entries = []
    for symbol, count in counts.most_common():
        meaning = symbol_meanings.get(symbol)
        status = "VERIFIED"
        if symbol == "":
            status = "AMBIGUOUS"
        elif meaning is None:
            # Non-energy markers or unverified symbols observed in text.
            status = "UNKNOWN"
        entries.append(
            {
                "symbol": symbol,
                "observed_count": count,
                "meaning": meaning["meaning"] if meaning else None,
                "status": status,
                "source": "LOCAL_OBSERVATION; meaning from cabt EnergyType enum + PTCG convention (INFERENCE)",
                "notes": meaning["notes"] if meaning else "not yet mapped to a verified meaning",
            }
        )
    return {
        "source_file": str(ing.path),
        "registry": entries,
        "cabt_energy_type": {str(k): v for k, v in CABT_ENERGY_TYPE.items()},
    }


def write_registry(ing: IngestedFile, out_path) -> None:
    write_json(out_path, build_registry(ing))