"""Tests for Attack Semantics Phase C Fixes."""

import pytest
from ptcgabc.policy.attack_value import AttackEvaluator, AttackContext, DamageModel

def _make_context(bench=0, max_hp=100, dmg=0):
    return AttackContext({
        "our_bench_count": bench,
        "opp_active_maxhp": max_hp,
        "opp_active_damage": dmg,
    })

def test_guaranteed_ko():
    ev = AttackEvaluator()
    ctx = _make_context(max_hp=100, dmg=20) # 80 remaining
    atk = {"damage": "80", "name": "Standard Attack"}
    res = ev.evaluate(atk, ctx)
    assert res.expected_damage == 80
    assert res.min_damage == 80
    assert res.ko_status == "GUARANTEED_KO"

def test_no_ko():
    ev = AttackEvaluator()
    ctx = _make_context(max_hp=100, dmg=0)
    atk = {"damage": "50", "name": "Weak Attack"}
    res = ev.evaluate(atk, ctx)
    assert res.ko_status == "NO_KO"

def test_circle_circuit_0_bench():
    ev = AttackEvaluator()
    ctx = _make_context(bench=0, max_hp=100)
    atk = {"damage": "50x", "name": "Circle Circuit"}
    res = ev.evaluate(atk, ctx)
    assert res.expected_damage == 0
    assert res.ko_status == "NO_KO"

def test_circle_circuit_2_bench():
    ev = AttackEvaluator()
    ctx = _make_context(bench=2, max_hp=100)
    atk = {"damage": "50x", "name": "Circle Circuit"}
    res = ev.evaluate(atk, ctx)
    assert res.expected_damage == 100
    assert res.ko_status == "GUARANTEED_KO"

def test_circle_circuit_5_bench():
    ev = AttackEvaluator()
    ctx = _make_context(bench=5, max_hp=300)
    atk = {"damage": "50x", "name": "Circle Circuit"}
    res = ev.evaluate(atk, ctx)
    assert res.expected_damage == 250
    assert res.ko_status == "NO_KO"

def test_coin_flip_variable_damage():
    ev = AttackEvaluator()
    ctx = _make_context(max_hp=100)
    atk = {"damage": "30x", "name": "Coin Attack", "effect": "Flip 2 coins. This attack does 30 damage for each heads."}
    res = ev.evaluate(atk, ctx)
    assert res.expected_damage == 30.0  # 2 coins * 50% * 30
    assert res.min_damage == 0
    assert res.max_damage == 60
    assert res.ko_status == "NO_KO"

def test_conditional_attack():
    ev = AttackEvaluator()
    ctx = _make_context(max_hp=50)
    atk = {"damage": "30+", "name": "Cond Attack", "effect": "If your opponent's Active Pokémon is a Pokémon ex, this attack does 30 more damage."}
    res = ev.evaluate(atk, ctx)
    assert res.base_damage == 30
    assert res.min_damage == 30
    assert res.expected_damage == 45.0
    assert res.max_damage == 60
    assert res.ko_status == "CONDITIONAL_KO"

def test_effect_only_attack():
    ev = AttackEvaluator()
    ctx = _make_context(max_hp=100)
    atk = {"damage": "", "name": "Healing Song", "effect": "Heal 30 damage from 1 of your Pokémon."}
    res = ev.evaluate(atk, ctx)
    assert res.expected_damage == 0
    assert res.ko_status == "NO_KO"
    assert "heal" in res.effects

def test_bench_damage():
    ev = AttackEvaluator()
    ctx = _make_context()
    atk = {"damage": "200", "name": "Phantom Dive", "effect": "Put 6 damage counters on your opponent's Benched Pokémon in any way you like."}
    res = ev.evaluate(atk, ctx)
    assert "bench_damage" in res.effects
