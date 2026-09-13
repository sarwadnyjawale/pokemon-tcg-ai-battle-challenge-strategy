"""Schema registry: RAW_COLUMN -> CANONICAL_FIELD mapping with verified status.

Blueprint §4: schema mapping must never guess. Ambiguities stop canonicalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MappingStatus(str, Enum):
    VERIFIED = "VERIFIED"
    AMBIGUOUS = "AMBIGUOUS"
    UNUSED = "UNUSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ColumnMapping:
    raw_column: str
    canonical_field: str
    meaning: str
    validation_rule: str
    source: str
    status: MappingStatus


# Verified against the official Kaggle data description for both competitions
# (https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy/data).
OFFICIAL_DATA_DESCRIPTION = "OFFICIAL_KAGGLE_DATA_DESCRIPTION"

# Header-name aliases observed in local copies (typos / BOM / encoding variants).
HEADER_ALIASES: dict[str, str] = {
    "Card ID": "Card ID",
    "Card Name": "Card Name",
    "Expansion": "Expansion",
    "Collection No.": "Collection No.",
    "Stage (Pok\u00e9mon)/Type (Energy and Trainer)": "Stage (Pok\u00e9mon)/Type (Energy and Trainer)",
    "Rule": "Rule",
    "Category": "Category",
    "Previous stage": "Previous stage",
    "Previos stage": "Previous stage",  # observed typo in one local copy
    "HP": "HP",
    "Type": "Type",
    "Weakness": "Weakness",
    "Resistance (Type)": "Resistance (Type)",
    "Retreat": "Retreat",
    "Move Name": "Move Name",
    "Cost": "Cost",
    "Damage": "Damage",
    "Effect Explanation": "Effect Explanation",
}

_COLUMNS: dict[str, ColumnMapping] = {}


def _register(
    raw: str,
    canonical: str,
    meaning: str,
    rule: str,
    source: str = OFFICIAL_DATA_DESCRIPTION,
    status: MappingStatus = MappingStatus.VERIFIED,
) -> None:
    _COLUMNS[raw] = ColumnMapping(raw, canonical, meaning, rule, source, status)


_register("Card ID", "card_id", "Unique identifier used by the simulator.", "non-empty; unique per card; string form of int", OFFICIAL_DATA_DESCRIPTION)
_register("Card Name", "card_name", "The name of the card (may repeat across printings).", "non-empty", OFFICIAL_DATA_DESCRIPTION)
_register("Expansion", "expansion", "Expansion set the card belongs to.", "non-empty for Pokemon; may be empty for some energies", OFFICIAL_DATA_DESCRIPTION)
_register("Collection No.", "collection_no", "Card's collection number within the expansion.", "non-empty", OFFICIAL_DATA_DESCRIPTION)
_register(
    "Stage (Pok\u00e9mon)/Type (Energy and Trainer)",
    "stage_or_type",
    "Pokemon evolution stage (Basic/Stage 1/Stage 2) or card type (Item/Supporter/Tool/Stadium/Energy).",
    "one of observed values or AMBIGUOUS",
    OFFICIAL_DATA_DESCRIPTION,
)
_register("Rule", "rule", "Special rule text associated with the card, if applicable.", "free text; 'n/a' if none", OFFICIAL_DATA_DESCRIPTION)
_register("Category", "category", "Card category / sub-category marker (e.g. Trainer's Pokemon {N}, Tera(...)).", "free text; 'n/a' if none", OFFICIAL_DATA_DESCRIPTION)
_register("Previous stage", "previous_stage", "The previous evolution stage (card NAME) required for this Pokemon card.", "'n/a' for non-evolving Pokemon / non-Pokemon; else name ref", OFFICIAL_DATA_DESCRIPTION)
_register("HP", "hp", "Hit Points of the Pokemon.", "integer string; 'n/a' for non-Pokemon", OFFICIAL_DATA_DESCRIPTION)
_register(
    "Type",
    "type",
    "Pokemon type for Pokemon (energy symbol like {G}); for energy cards the energy symbol; for trainer/other 'n/a'.",
    "single/tuple of recognized symbols, 'n/a', or AMBIGUOUS symbol; Dragon uses '\\u7adc'",
    OFFICIAL_DATA_DESCRIPTION,
)
_register("Weakness", "weakness", "Pokemon type weakness.", "symbol, 'n/a', or empty", OFFICIAL_DATA_DESCRIPTION)
_register("Resistance (Type)", "resistance", "Pokemon type resistance.", "symbol, 'n/a', or empty", OFFICIAL_DATA_DESCRIPTION)
_register("Retreat", "retreat", "Retreat cost required to switch the Pokemon.", "energy symbols or 'n/a'", OFFICIAL_DATA_DESCRIPTION)
_register("Move Name", "move_name", "Name of the attack or move (abilities appear as [Ability] ...).", "non-empty for move rows", OFFICIAL_DATA_DESCRIPTION)
_register("Cost", "move_cost", "Energy cost required to use the move.", "symbols; 'n/a' for abilities", OFFICIAL_DATA_DESCRIPTION)
_register("Damage", "move_damage", "Damage dealt by the move.", "integer, expression ('+','x','?'), or 'n/a'", OFFICIAL_DATA_DESCRIPTION)
_register("Effect Explanation", "move_effect", "Description of the move effect or additional rule text.", "free text; may contain newlines", OFFICIAL_DATA_DESCRIPTION)


def normalize_header(raw_header: str) -> str:
    key = raw_header.strip().strip("\ufeff")
    if key in HEADER_ALIASES:
        return HEADER_ALIASES[key]
    return key


def mapping_for(normalized_header: str) -> ColumnMapping:
    if normalized_header in _COLUMNS:
        return _COLUMNS[normalized_header]
    return ColumnMapping(normalized_header, f"raw:{normalized_header}", "Unknown column.", "must be resolved before canonicalization", "LOCAL_OBSERVATION", MappingStatus.UNKNOWN)


def critical_unknown(columns: list[str]) -> list[str]:
    """Columns with UNKNOWN status block canonicalization (blueprint §4)."""
    return [c for c in columns if mapping_for(c).status == MappingStatus.UNKNOWN]


def all_mappings() -> list[ColumnMapping]:
    return list(_COLUMNS.values())


def report() -> list[dict]:
    return [
        {
            "raw_column": m.raw_column,
            "canonical_field": m.canonical_field,
            "meaning": m.meaning,
            "validation_rule": m.validation_rule,
            "source": m.source,
            "status": m.status.value,
        }
        for m in all_mappings()
    ]