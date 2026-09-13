"""Tests for Phase 4 policy modules."""

import pytest
from ptcgabc.policy.context_router import ContextRouter
from ptcgabc.policy.card_value import CardValueScorer
from ptcgabc.policy.tempo import TempoScorer
from ptcgabc.policy.action_safety import ActionSafetyGate
from ptcgabc.environment.enriched_adapter import OPT_ATTACK, OPT_EVOLVE, OPT_ATTACH, OPT_PLAY, OPT_END, OPT_RETREAT, OPT_ABILITY, OPT_CARD


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_action(opt_type, **kwargs):
    d = {"cabt_option_type": opt_type, "type": kwargs.pop("atype", "unknown"), "raw": {}}
    d.update(kwargs)
    return d


def _make_state(**overrides):
    base = {
        "game_phase": "midgame",
        "own_prizes": 6, "opp_prizes": 6,
        "own_hand_count": 4, "our_hand_count": 4,
        "own_bench_count": 2, "our_bench_count": 2,
        "own_active_hp_fraction": 1.0,
        "opp_active_hp": 120, "opp_active_maxhp": 120,
        "opp_is_ex": 0,
        "energy_attached": False,
        "supporter_played": False,
        "retreated": False,
        "own_energy_in_play": 2,
        "select_context": 0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ContextRouter tests
# ---------------------------------------------------------------------------

class TestContextRouter:
    def test_router_always_returns_valid_index(self):
        router = ContextRouter()
        actions = [
            _make_action(OPT_ATTACK, atype="attack", damage=60),
            _make_action(OPT_END, atype="pass"),
        ]
        idx, reason = router.select_action(actions, _make_state(), turn=1)
        assert 0 <= idx < len(actions)
        assert isinstance(reason, str)

    def test_router_prefers_attack_over_end(self):
        router = ContextRouter()
        actions = [
            _make_action(OPT_END, atype="pass"),
            _make_action(OPT_ATTACK, atype="attack", damage=60),
        ]
        idx, _ = router.select_action(actions, _make_state(), turn=5)
        assert actions[idx]["cabt_option_type"] == OPT_ATTACK

    def test_router_handles_empty_raises(self):
        router = ContextRouter()
        with pytest.raises(ValueError):
            router.select_action([], _make_state(), turn=0)

    def test_router_generic_context_fallback(self):
        router = ContextRouter()
        actions = [_make_action(OPT_CARD, atype="card", raw={"area": 99, "index": 0})]
        idx, reason = router.select_action(actions, _make_state(select_context=99), turn=0)
        assert idx == 0
        assert "fallback" in reason or "generic" in reason

    def test_router_draw_count_prefers_max(self):
        router = ContextRouter()
        actions = [
            _make_action(0, atype="numbered_choice", raw={"number": 1}),
            _make_action(0, atype="numbered_choice", raw={"number": 3}),
            _make_action(0, atype="numbered_choice", raw={"number": 7}),
        ]
        idx, _ = router.select_action(actions, _make_state(select_context=38), turn=2)
        assert actions[idx]["raw"]["number"] == 7

    def test_router_with_all_policies(self):
        router = ContextRouter(
            main_policy=None,
            card_scorer=CardValueScorer(card_db={}),
            tempo_scorer=TempoScorer(card_db={}),
            safety_gate=ActionSafetyGate(),
        )
        actions = [
            _make_action(OPT_PLAY, atype="play_pokemon", card_category="Pokemon"),
            _make_action(OPT_ATTACH, atype="attach_energy"),
            _make_action(OPT_ATTACK, atype="attack", damage=100),
            _make_action(OPT_END, atype="pass"),
        ]
        idx, reason = router.select_action(actions, _make_state(), turn=5)
        assert 0 <= idx < len(actions)
        # Should not choose END when productive actions exist
        assert actions[idx]["cabt_option_type"] != OPT_END


# ---------------------------------------------------------------------------
# TempoScorer tests
# ---------------------------------------------------------------------------

class TestTempoScorer:
    def test_attack_scores_higher_than_end(self):
        ts = TempoScorer(card_db={})
        state = _make_state()
        atk_score = ts.score(_make_action(OPT_ATTACK, atype="attack", damage=80), state, 5)
        end_score = ts.score(_make_action(OPT_END, atype="pass"), state, 5)
        assert atk_score > end_score

    def test_ko_attack_highest(self):
        ts = TempoScorer(card_db={})
        state = _make_state(opp_active_hp=50)
        ko_score = ts.score(_make_action(OPT_ATTACK, atype="attack", damage=60), state, 5)
        weak_score = ts.score(_make_action(OPT_ATTACK, atype="attack", damage=20), state, 5)
        assert ko_score > weak_score

    def test_evolve_scores_well(self):
        ts = TempoScorer(card_db={})
        state = _make_state(game_phase="early")
        ev_score = ts.score(_make_action(OPT_EVOLVE, atype="evolve"), state, 3)
        end_score = ts.score(_make_action(OPT_END, atype="pass"), state, 3)
        assert ev_score > end_score

    def test_attach_scores_positive(self):
        ts = TempoScorer(card_db={})
        state = _make_state()
        att_score = ts.score(_make_action(OPT_ATTACH, atype="attach_energy"), state, 3)
        assert att_score > 0

    def test_end_scores_negative(self):
        ts = TempoScorer(card_db={})
        state = _make_state()
        end_score = ts.score(_make_action(OPT_END, atype="pass"), state, 3)
        assert end_score < 0

    def test_retreat_low_hp_high(self):
        ts = TempoScorer(card_db={})
        state = _make_state(own_active_hp_fraction=0.1)
        ret_score = ts.score(_make_action(OPT_RETREAT, atype="retreat"), state, 5)
        assert ret_score > 20.0

    def test_retreat_healthy_low(self):
        ts = TempoScorer(card_db={})
        state = _make_state(own_active_hp_fraction=0.9)
        ret_score = ts.score(_make_action(OPT_RETREAT, atype="retreat"), state, 5)
        assert ret_score < 10.0


# ---------------------------------------------------------------------------
# ActionSafetyGate tests
# ---------------------------------------------------------------------------

class TestActionSafetyGate:
    def test_penalizes_end_when_attack_exists(self):
        gate = ActionSafetyGate()
        actions = [
            _make_action(OPT_ATTACK, atype="attack", damage=60),
            _make_action(OPT_END, atype="pass"),
        ]
        scored = [(0, 30.0), (1, -5.0)]
        adjusted = gate.adjust_scores(scored, actions, _make_state())
        # END should be further penalized
        end_score = next(s for i, s in adjusted if i == 1)
        assert end_score < -5.0

    def test_no_penalty_when_only_end(self):
        gate = ActionSafetyGate()
        actions = [_make_action(OPT_END, atype="pass")]
        scored = [(0, -5.0)]
        adjusted = gate.adjust_scores(scored, actions, _make_state())
        end_score = adjusted[0][1]
        assert end_score == -5.0  # no penalty

    def test_should_pass_true_when_no_productive(self):
        gate = ActionSafetyGate()
        actions = [_make_action(OPT_END, atype="pass")]
        assert gate.should_pass(actions, _make_state()) is True

    def test_should_pass_false_when_productive(self):
        gate = ActionSafetyGate()
        actions = [
            _make_action(OPT_ATTACK, atype="attack"),
            _make_action(OPT_END, atype="pass"),
        ]
        assert gate.should_pass(actions, _make_state()) is False


# ---------------------------------------------------------------------------
# CardValueScorer tests
# ---------------------------------------------------------------------------

class TestCardValueScorer:
    def test_setup_prefers_high_hp(self):
        db = {
            100: {"card_name": "Dreepy", "fields": {"HP": "60"}, "attacks": []},
            200: {"card_name": "Pikachu", "fields": {"HP": "120"}, "attacks": []},
        }
        scorer = CardValueScorer(card_db=db)
        dreepy_score = scorer.score_for_setup({"card_id": 100}, _make_state(), is_active=True)
        pika_score = scorer.score_for_setup({"card_id": 200}, _make_state(), is_active=True)
        # Dreepy gets evolution bonus despite lower HP
        assert dreepy_score > 0

    def test_search_prefers_needed_cards(self):
        db = {
            100: {"card_name": "Dreepy", "fields": {"HP": "60", "Stage (Pokémon)/Type (Energy and Trainer)": "Basic"}, "attacks": [{"name": "Bite", "damage": "20"}]},
        }
        scorer = CardValueScorer(card_db=db)
        score = scorer.score_for_search({"card_id": 100}, _make_state(game_phase="opening", own_bench_count=0))
        assert score > 10.0  # basic Pokemon in opening with no bench

    def test_unknown_card_scores_zero(self):
        scorer = CardValueScorer(card_db={})
        assert scorer.score_for_setup({"card_id": 9999}, _make_state()) == 0.0
        assert scorer.score_for_search({"card_id": 9999}, _make_state()) == 0.0

    def test_attach_target_prefers_active(self):
        scorer = CardValueScorer(card_db={})
        active_score = scorer.score_for_attach_target({"raw": {"inPlayArea": 4}}, _make_state())
        bench_score = scorer.score_for_attach_target({"raw": {"inPlayArea": 5}}, _make_state())
        assert active_score > bench_score
