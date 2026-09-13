import pytest

from ptcgabc.simulator.mock import MockSimulator


def _deck(n=60):
    return [3] * n


def test_mock_label_is_mock():
    assert MockSimulator.ENVIRONMENT_TYPE == "MOCK"


def test_mock_start_select_finish():
    sim = MockSimulator(_deck(), _deck(), seed=1)
    obs, start = sim.start()
    assert start.errorPlayer == -1
    assert obs["select"] is not None
    n = len(obs["select"]["option"])
    obs2 = sim.select([0])
    assert obs2["current"]["yourIndex"] in (0, 1)
    sim.finish()


def test_mock_rejects_bad_length_deck():
    with pytest.raises(ValueError):
        MockSimulator(_deck(59), _deck(60))


def test_mock_rejects_out_of_range_index():
    sim = MockSimulator(_deck(), _deck(), seed=2)
    sim.start()
    n = len(sim._obs["select"]["option"])
    with pytest.raises(IndexError):
        sim.select([n + 5])