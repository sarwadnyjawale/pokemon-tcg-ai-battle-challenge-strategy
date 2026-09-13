"""Pocket/60-card format constants — VERIFIED against the live engine.

IMPORTANT (provenance): The competition's CSV ships with TWO files and the
engine is bundled under `cabt/cg`. We empirically verified (Phase 1 probes):

    errorType 2  -> too many copies of a NON-Energy card (cap = 4)
    errorType 3  -> illegal deck composition (e.g. 60x the same card)
    errorType 4  -> unrecognized card id
    errorType 0  -> deck accepted

We also confirmed:
    * basic Energy copies are NOT copy-limited (5x Basic {R} Energy was
      accepted, errorType=0, errorPlayer=-1)
    * opening hand size = 7, prize count = 6, deck size = 60

So ALL the "Pocket" assumptions in the blueprint (deck=20, prizes=3,
hand=5, max copies=2) are REJECTED — the live engine uses the real 60-card
TCG format, not Pocket. These constants are the true, engine-verified ones.
"""

from __future__ import annotations

DECK_SIZE_60 = 60
MAX_NON_ENERGY_COPIES = 4
BASIC_ENERGY_COPIES_UNLIMITED = True
PRIZE_COUNT = 6
OPENING_HAND_SIZE = 7

# Copy-limit is per CARD_ID (not per card type/category) — verified: 5x of a
# non-energy card was rejected regardless of whether it was a Pokemon or
# Trainer; 5x of a Basic Energy card was accepted.
COPY_LIMIT_APPLIES_TO = ("Pokemon", "Trainer")
ENERGY_NOT_COPY_LIMITED = True

# Engine-verified errorType legend (Phase 1 probe results)
ENGINE_ERRORTYPE_LEGEND = {
    0: "OK (deck accepted by engine)",
    2: "TOO_MANY_COPIES of a non-Energy card (>4)",
    3: "ILLEGAL_COMPOSITION (e.g. 60x the same card)",
    4: "UNRECOGNIZED_CARD_ID",
}
