"""Canonical card construction: group raw rows by verified Card ID (lossless).

Blueprint §3, §8: preserve complete data; never assume a max attack count.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from ..contracts import Attack, Card, ContractValidationError
from ..reproduce import write_json
from .csv_ingest import IngestedFile, RawRow


def _clean(v: str) -> str:
    v = v.strip()
    return "" if v.lower() in ("n/a", "") else v


def is_move_row(row: RawRow) -> bool:
    return bool(_clean(row.values.get("Move Name", "")))


def build_canonical_cards(
    ing: IngestedFile,
    transformation_version: str = "1.0",
) -> list[Card]:
    by_id: "OrderedDict[str, list[RawRow]]" = OrderedDict()
    for r in ing.rows:
        card_id = r.values["Card ID"]
        by_id.setdefault(card_id, []).append(r)

    cards: list[Card] = []
    for card_id, card_rows in by_id.items():
        names = {r.values["Card Name"] for r in card_rows}
        if len(names) != 1:
            raise ContractValidationError(
                f"card {card_id} has inconsistent Card Name across rows: {sorted(names)}"
            )
        first = card_rows[0]
        fields: dict[str, Any] = {}
        _CARD_LEVEL = [
            "Card Name", "Expansion", "Collection No.",
            "Stage (Pok\u00e9mon)/Type (Energy and Trainer)", "Rule", "Category",
            "Previous stage", "HP", "Type", "Weakness", "Resistance (Type)", "Retreat",
        ]
        for f in _CARD_LEVEL:
            vals = {_clean(r.values[f]) for r in card_rows if _clean(r.values[f])}
            if len(vals) > 1:
                raise ContractValidationError(
                    f"card {card_id} has inconsistent {f!r} across rows: {sorted(vals)}"
                )
            fields[f] = next(iter(vals), "")

        attacks: list[Attack] = []
        move_rows = [r for r in card_rows if is_move_row(r)]
        for idx, mr in enumerate(move_rows):
            attacks.append(
                Attack(
                    name=mr.values["Move Name"],
                    cost=mr.values.get("Cost", ""),
                    damage=mr.values.get("Damage", ""),
                    effect=mr.values.get("Effect Explanation", ""),
                    move_row_index=idx,
                    source_rows=[mr.row_index],
                ).validate()
            )

        cards.append(
            Card(
                card_id=card_id,
                card_name=names.pop(),
                category=fields.get("Category", ""),
                source_file=str(ing.path),
                source_row_indices=[r.row_index for r in card_rows],
                raw_rows=[dict(r.values) for r in card_rows],
                fields=fields,
                attacks=attacks,
                transformation_version=transformation_version,
            ).validate()
        )
    return cards


def summary(cards: list[Card]) -> dict[str, Any]:
    n_attacks = [len(c.attacks) for c in cards]
    from collections import Counter

    categories = Counter(c.category for c in cards)
    return {
        "n_cards": len(cards),
        "attacks_per_card_max": max(n_attacks, default=0),
        "attacks_per_card_counter": dict(Counter(n_attacks)),
        "cards_with_zero_attacks": sum(1 for n in n_attacks if n == 0),
        "categories": {k: v for k, v in sorted(categories.items(), key=lambda x: -x[1])},
    }


def write_canonical(cards: list[Card], out_path) -> None:
    payload = {
        "schema_version": "canonical_card/1.0",
        "cards": [c.to_dict(full=True) for c in cards],
    }
    write_json(out_path, payload)