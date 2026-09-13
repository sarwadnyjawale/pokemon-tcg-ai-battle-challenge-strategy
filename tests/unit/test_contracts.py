from ptcgabc.contracts import (Action, Attack, Card, ContractValidationError, Deck,
                               EvaluationResult, GameState, PlayerState, Observation)
from ptcgabc.provenance import EnvironmentType, ResultSource


def _minimal_card() -> Card:
    return Card(
        card_id="1",
        card_name="Bulbasaur",
        category="Pok\u00e9mon",
        source_file="a.csv",
        source_row_indices=[2],
        raw_rows=[{"Card ID": "1", "Card Name": "Bulbasaur"}],
        fields={},
    )


def test_attack_require_name():
    a = Attack(name="Tackle")
    assert a.validate() is a


def test_card_requires_card_id_and_rows():
    _minimal_card().validate()
    c = _minimal_card()
    c.card_id = ""
    try:
        c.validate()
        raise AssertionError("expected ContractValidationError")
    except ContractValidationError:
        pass


def test_deck_must_be_60():
    try:
        Deck(decklist=["1"] * 59).validate()
        raise AssertionError("expected ContractValidationError")
    except ContractValidationError:
        pass
    Deck(decklist=["1"] * 60).validate()


def test_evaluation_result_environment_whitelist():
    ok = EvaluationResult(
        experiment_id="E1", model="m", deck="d", opponents=["o"],
        games=10, wins=5, environment=EnvironmentType.VERIFIED_REAL.value,
        source=ResultSource.LOCAL_EXPERIMENT,
    )
    ok.validate()
    bad = EvaluationResult(
        experiment_id="E2", model="m", deck="d", opponents=["o"],
        games=10, wins=5, environment="NOT_A_REAL_ENV",
        source=ResultSource.UNKNOWN,
    )
    try:
        bad.validate()
        raise AssertionError("expected ContractValidationError")
    except ContractValidationError:
        pass


def test_observation_carries_raw_and_actions():
    obs = Observation(raw={"x": 1}, visible_state=None, legal_actions=[Action(action_id="a0")])
    obs.validate()