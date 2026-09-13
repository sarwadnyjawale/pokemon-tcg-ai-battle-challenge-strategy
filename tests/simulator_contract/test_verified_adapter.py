import pytest

from ptcgabc.simulator.verified_adapter import (BattleStepError, EngineUnavailable,
                                                RealCabtBattle, engine_capability,
                                                translate_raw)

# Known-legal 60-card deck (public reference: AnishGharat/pokemon-kaggle, dragapult_ex).
_LEGAL = [119]*4 + [120]*4 + [121]*3 + [140, 184] + [235]*2 + [1071] + [1079]*2 + [1080] \
    + [1086]*4 + [1097]*2 + [1120]*4 + [1121]*4 + [1152]*3 + [1156] + [1182]*3 + [1198]*4 \
    + [1210]*2 + [1227]*4 + [1256]*2 + [2]*4 + [5]*4

assert len(_LEGAL) == 60


def _engine_or_skip():
    cap = engine_capability()
    if not cap["available"]:
        pytest.skip(f"real engine unavailable: {cap.get('reason')}")
    return cap


def test_capability_probe():
    cap = engine_capability()
    assert "available" in cap
    if cap["available"]:
        assert cap["environment_type"] == "VERIFIED_REAL"
        RealCabtBattle()  # constructs without raising
    else:
        with pytest.raises(EngineUnavailable):
            RealCabtBattle()


def test_real_start_accepts_legal_deck():
    _engine_or_skip()
    battle = RealCabtBattle()
    start = battle.start(list(_LEGAL), list(_LEGAL))
    assert start.errorPlayer == -1
    assert start.errorType == 0
    obs = battle.observation()
    assert obs.current is not None
    assert obs.current.turn == 0
    assert obs.current.result == -1
    # first decision is the go-first coin flip
    if obs.select is not None:
        assert obs.select.type == 9
        assert obs.select.context == 41
    battle.finish()


def test_invalid_deck_rejected_without_battle():
    _engine_or_skip()
    battle = RealCabtBattle()
    start = battle.start([3] * 60, [3] * 60)
    assert start.errorPlayer == 0
    assert start.errorType != 0
    battle.finish()


def test_out_of_range_select_raises_battlesteperror_without_crashing():
    _engine_or_skip()
    battle = RealCabtBattle()
    battle.start(list(_LEGAL), list(_LEGAL))
    n = battle._option_count()
    assert n is not None and n > 0
    with pytest.raises(BattleStepError):
        battle.select([n + 1000])


def test_legal_first_moves_do_not_crash():
    _engine_or_skip()
    battle = RealCabtBattle()
    battle.start(list(_LEGAL), list(_LEGAL))
    # IS_FIRST yes
    for choice in ([0],):
        obs = battle.select(choice)
        assert obs.current is not None
    battle.finish()


def test_translate_raw_to_canonical_observation():
    _engine_or_skip()
    battle = RealCabtBattle()
    battle.start(list(_LEGAL), list(_LEGAL))
    raw = dict(battle._last_raw)
    obs = translate_raw(raw)
    assert obs.visible_state is not None
    assert len(obs.visible_state.players) == 2
    assert obs.legal_actions
    battle.finish()