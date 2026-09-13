import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ptcgabc.data import canonical as canonical_mod
from ptcgabc.data.csv_ingest import ingest_csv
from scripts.phase1_pipeline import OUT_PHASE1, run


def test_phase1_pipeline_end_to_end():
    report = run()

    assert report["passes"]["csv_parsed"] is True
    assert report["passes"]["card_ids_valid"] is True
    assert report["passes"]["canonical_cards_gt_1200"] is True

    for rel in report["links"].values():
        assert (ROOT / rel).exists(), f"missing {rel}"

    phase1 = json.loads((OUT_PHASE1 / "phase1_report.json").read_text(encoding="utf-8"))
    assert phase1["canonical_cards"]["n_cards"] == 1267


def test_canonical_is_lossless_preserved():
    ing = ingest_csv(ROOT / "data" / "EN_Card_Data (1).csv", primary=True)
    cards = canonical_mod.build_canonical_cards(ing)
    n_rows_in_raw = sum(len(c.raw_rows) for c in cards)
    assert n_rows_in_raw == ing.n_rows == 2022