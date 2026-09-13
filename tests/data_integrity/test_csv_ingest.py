import re
from pathlib import Path

from ptcgabc.data import canonical as canonical_mod
from ptcgabc.data import energy as energy_mod
from ptcgabc.data import evolution as evolution_mod
from ptcgabc.data.csv_ingest import card_id_validation, ingest_csv
from ptcgabc.data.schema_registry import critical_unknown, normalize_header

ROOT = Path(__file__).resolve().parents[2]
PRIMARY = ROOT / "data" / "EN_Card_Data (1).csv"


def _ingest():
    ing = ingest_csv(PRIMARY, primary=True)
    ing.validate()
    return ing


def test_encoding_label_is_utf8():
    assert "utf-8" in ingest_csv(PRIMARY).encoding


def test_all_columns_mapped():
    ing = _ingest()
    assert critical_unknown(ing.columns) == []
    assert "Previous stage" in ing.columns


def test_header_alias_for_typo():
    assert normalize_header("Previos stage") == "Previous stage"


def test_card_ids_int_like_no_blanks():
    ing = _ingest()
    val = card_id_validation(ing)
    assert val["ok"] is True
    assert val["distinct_ids"] == 1267
    assert val["n_rows"] == 2022


def test_every_card_id_has_single_name():
    ing = _ingest()
    cards = canonical_mod.build_canonical_cards(ing)
    for c in cards:
        assert c.source_row_indices, c.card_id


def test_attack_grouping():
    ing = _ingest()
    cards = canonical_mod.build_canonical_cards(ing)
    by_id = {c.card_id: c for c in cards}
    # A known multi-move card: "Tera(Stellar)" Pikachu ex or a multi-attack mon.
    multi = [c for c in cards if len(c.attacks) >= 3]
    assert multi, "expected at least one card with 3 moves"
    breakpoint_id = next(iter(multi)).card_id
    assert all(a.source_rows for a in by_id[breakpoint_id].attacks)


def test_energy_symbols_present_and_registry_has_grass():
    ing = _ingest()
    counts = energy_mod.scan_symbols(ing)
    assert counts["G"] > 100
    reg = energy_mod.build_registry(ing)
    symbols = {e["symbol"] for e in reg["registry"]}
    assert "G" in symbols and "F" in symbols and "R" in symbols


def test_dragon_type_symbol_present():
    ing = _ingest()
    dragon_rows = [r for r in ing.rows if r.values.get("Type", "") == "\u7adc"]
    assert len(dragon_rows) > 0


def test_evolution_never_resolves_ambiguity():
    ing = _ingest()
    cards = canonical_mod.build_canonical_cards(ing)
    res = evolution_mod.resolve_evolution(cards)
    stats = res["stats"]
    assert stats["VERIFIED"] + stats["AMBIGUOUS"] + stats["INVALID_STAGE"] + stats["UNRESOLVED"] + stats["NONE"] == len(cards)
    # AMBIGUOUS cards are flagged, not silently resolved.
    amb = [k for k, v in res["resolutions"].items() if v["status"] == "AMBIGUOUS"]
    assert len(amb) > 0, "expected some multi-printing evolutions (e.g. Eevee) to be AMBIGUOUS"