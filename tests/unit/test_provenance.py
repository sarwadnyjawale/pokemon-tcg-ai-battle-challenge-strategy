import pytest

from ptcgabc.provenance import (EnvironmentType, ResultSource, UnsupportedEvidenceError,
                                assert_gameplay_evidence, describe_source,
                                require_support)


def test_simulation_not_entered():
    assert describe_source()["simulation_entered"] is False
    assert describe_source()["official_simulation_rating"] is None


def test_gameplay_evidence_requires_verified_real_env():
    assert_gameplay_evidence(EnvironmentType.VERIFIED_REAL, ResultSource.LOCAL_EXPERIMENT)
    with pytest.raises(UnsupportedEvidenceError):
        assert_gameplay_evidence(EnvironmentType.MOCK, ResultSource.LOCAL_EXPERIMENT)
    with pytest.raises(UnsupportedEvidenceError):
        assert_gameplay_evidence(EnvironmentType.VERIFIED_REAL, ResultSource.HYPOTHESIS)


def test_require_support_whitelist():
    require_support("x", ResultSource.LOCAL_EXPERIMENT, (ResultSource.LOCAL_EXPERIMENT,))
    with pytest.raises(UnsupportedEvidenceError):
        require_support("official claim", ResultSource.LOCAL_EXPERIMENT, (ResultSource.OFFICIAL_KAGGLE_RESULT,))