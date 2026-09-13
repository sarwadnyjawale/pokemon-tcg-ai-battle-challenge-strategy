"""Action Safety Gate for CABT decisions.

Before selecting PASS/END, checks whether productive actions remain.
Does NOT make actions illegal — only adjusts scores.

RULES:
  - Never introduces hidden information
  - Never produces invalid action indices
  - Only adjusts END/PASS scoring based on remaining alternatives
"""

from __future__ import annotations

from typing import Any

from ..environment.enriched_adapter import (
    OPT_ATTACK, OPT_EVOLVE, OPT_ATTACH, OPT_PLAY, OPT_ABILITY,
    OPT_RETREAT, OPT_END,
)


class ActionSafetyGate:
    """Adjusts scores to prevent premature passing.

    If productive actions exist, END/PASS gets a large penalty.
    If no productive actions exist, END/PASS is acceptable.
    """

    # Action types considered "productive"
    PRODUCTIVE_TYPES = {OPT_ATTACK, OPT_EVOLVE, OPT_ATTACH, OPT_PLAY, OPT_ABILITY}

    def adjust_scores(
        self,
        scored: list[tuple[int, float]],
        actions: list[dict],
        state: dict,
    ) -> list[tuple[int, float]]:
        """Adjust scored actions to penalize premature END.

        scored: list of (index, score) tuples
        actions: the legal action dicts
        state: current game state

        Returns adjusted (index, score) list.
        """
        if not scored or not actions:
            return scored

        # Check if any productive actions exist
        has_productive = False
        has_attack = False
        has_evolve = False
        has_attach = False

        for a in actions:
            opt_type = a.get("cabt_option_type", -1)
            if opt_type in self.PRODUCTIVE_TYPES:
                has_productive = True
            if opt_type == OPT_ATTACK:
                has_attack = True
            if opt_type == OPT_EVOLVE:
                has_evolve = True
            if opt_type == OPT_ATTACH:
                has_attach = True

        adjusted = []
        for idx, score in scored:
            opt_type = actions[idx].get("cabt_option_type", -1)

            if opt_type == OPT_END and has_productive:
                # Strong penalty: don't end turn while useful actions remain
                penalty = -40.0
                if has_attack:
                    penalty -= 20.0  # extra penalty if attack available
                if has_evolve:
                    penalty -= 10.0
                score += penalty

            adjusted.append((idx, score))

        return adjusted

    def should_pass(self, actions: list[dict], state: dict) -> bool:
        """Check if passing is the only reasonable option."""
        for a in actions:
            opt_type = a.get("cabt_option_type", -1)
            if opt_type in self.PRODUCTIVE_TYPES:
                return False
        return True
