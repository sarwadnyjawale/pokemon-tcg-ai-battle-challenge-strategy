"""Evolution graph resolution (blueprint §3/PROBLEM 7).

If the evolution parent is ambiguous -> AMBIGUOUS. Never "pick first candidate".
Resolution order:
  1. exact validated relationship (name + stage-chain consistent, single candidate)
  2. otherwise AMBIGUOUS (multiple candidates) or UNRESOLVED (no candidate)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..contracts import Card, ContractValidationError
from ..reproduce import write_json

STAGE_ORDER = {"Basic Pok\u00e9mon": 0, "Stage 1 Pok\u00e9mon": 1, "Stage 2 Pok\u00e9mon": 2}


def _clean(v: str) -> str:
    return v.strip() if v and v.strip().lower() != "n/a" else ""


def resolve_evolution(cards: list[Card]) -> dict[str, Any]:
    by_name: dict[str, list[Card]] = defaultdict(list)
    by_id = {c.card_id: c for c in cards}
    for c in cards:
        by_name[c.card_name].append(c)

    resolutions: dict[str, Any] = {}
    stats = {"VERIFIED": 0, "AMBIGUOUS": 0, "UNRESOLVED": 0, "NONE": 0, "INVALID_STAGE": 0}

    for c in cards:
        stage_field = c.fields.get("Stage (Pok\u00e9mon)/Type (Energy and Trainer)", "")
        prev = _clean(c.fields.get("Previous stage", ""))
        if not prev:
            resolutions[c.card_id] = {
                "card": c.card_name,
                "previous_stage_raw": "",
                "parent_candidates": [],
                "status": "NONE",
                "reason": "no previous stage listed (Basic Pokemon or non-Pokemon)",
            }
            stats["NONE"] += 1
            continue

        candidates = by_name.get(prev, [])
        child_stage = STAGE_ORDER.get(stage_field, -1)
        viable = []
        for cand in candidates:
            cand_stage_field = cand.fields.get("Stage (Pok\u00e9mon)/Type (Energy and Trainer)", "")
            cand_stage = STAGE_ORDER.get(cand_stage_field, -1)
            if cand_stage == child_stage - 1:
                viable.append(cand.card_id)
            else:
                viable.append({"id": cand.card_id, "stage_mismatch": True})
        exact = [v for v in viable if not (isinstance(v, dict) and v["stage_mismatch"])]

        if len(exact) == 1:
            status = "VERIFIED"
            reason = "single exact name+stage match"
        elif len(exact) > 1:
            status = "AMBIGUOUS"
            reason = f"{len(exact)} candidates with exact name match; no disambiguation supported"
        elif (child_stage - 1) not in (0, 1):
            status = "INVALID_STAGE"
            reason = f"child stage {stage_field!r} cannot have an evolution parent per stage order"
        elif viable:
            status = "AMBIGUOUS"
            reason = "candidate(s) exist but fail stage-chain validation"
        else:
            status = "UNRESOLVED"
            reason = f"no card named {prev!r} found in the pool"

        stats[status] += 1
        resolutions[c.card_id] = {
            "card": c.card_name,
            "previous_stage_raw": prev,
            "parent_candidates": [v if isinstance(v, str) else v for v in viable],
            "status": status,
            "reason": reason,
        }

    return {"resolutions": resolutions, "stats": dict(stats)}


def write_evolution(cards: list[Card], out_path) -> None:
    write_json(out_path, resolve_evolution(cards))