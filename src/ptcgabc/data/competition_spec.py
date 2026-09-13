"""Competition specification — verified facts only (blueprint §1.2).

Everything here is sourced from the official Kaggle documentation for the
Pokémon TCG AI Battle Challenge — Strategy competition. No assumptions.

Verified weights (official rubric): model 70%, deck 20%, report 10%; word limit 2000.
Fixed constraint: the Simulation category was NOT entered, so no official
Simulation result/rating/ladder position ever exists. Any such claim is a lie.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..provenance import ResultSource


class ConstraintViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class CompetitionSpec:
    # Official scoring rubric
    model_score_weight: float = 0.70
    deck_score_weight: float = 0.20
    report_score_weight: float = 0.10
    word_limit: int = 2000

    # Official rubric criteria
    model_criteria: tuple = (
        "clear_approach",
        "rationale",
        "originality",
        "technical_soundness",
        "consistency",
        "robustness",
        "performance_alignment",
    )
    deck_criteria: tuple = (
        "clear_deck_concept",
        "strategic_alignment",
        "effective_key_card_selection",
    )
    report_criteria: tuple = (
        "logical_structure",
        "clear_writing",
        "effective_figures_charts_tables",
    )

    # Fixed constraints
    simulation_entered: bool = False
    official_simulation_result: str | None = None
    official_simulation_rating: float | None = None
    official_ladder_ranking: int | None = None
    local_results_label: str = ResultSource.LOCAL_EXPERIMENT.value

    def validate(self) -> bool:
        if abs(self.model_score_weight + self.deck_score_weight + self.report_score_weight - 1.0) > 1e-9:
            raise ConstraintViolation("weights must sum to 1.0")
        if self.simulation_entered:
            raise ConstraintViolation("simulation_entered must be False (never fabricated)")
        if self.official_simulation_result is not None or self.official_simulation_rating is not None \
                or self.official_ladder_ranking is not None:
            raise ConstraintViolation("no official Simulation result may be recorded")
        return True


SPEC = CompetitionSpec()
SPEC.validate()


def label_result(result_type: ResultSource, value, description: str = "") -> dict:
    """Every result must carry its provenance label; official vs local never mix."""
    return {
        "source": result_type.value,
        "value": value,
        "description": description,
        "is_official": result_type == ResultSource.OFFICIAL_KAGGLE_RESULT,
    }