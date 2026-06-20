# Verifies: REQ-d00254-C
"""Config fields for coverage/result assertion crediting (CUR-1533)."""

import pytest
from pydantic import ValidationError

from elspais.config.schema import CoverageScanningConfig, ResultScanningConfig


def test_result_unmatched_credit_default_off():
    assert ResultScanningConfig().unmatched_credit == "off"


def test_result_unmatched_credit_accepts_verified():
    assert ResultScanningConfig(unmatched_credit="verified").unmatched_credit == "verified"


def test_result_unmatched_credit_rejects_unknown():
    with pytest.raises(ValidationError):
        ResultScanningConfig(unmatched_credit="bogus")


def test_coverage_assertion_credit_defaults_and_range():
    cfg = CoverageScanningConfig()
    assert cfg.assertion_credit == "off"
    assert cfg.min_coverage_fraction == 0.0


@pytest.mark.parametrize("val", ["off", "tested", "verified"])
def test_coverage_assertion_credit_accepts_values(val):
    cfg = CoverageScanningConfig(assertion_credit=val, min_coverage_fraction=0.8)
    assert cfg.assertion_credit == val
    assert cfg.min_coverage_fraction == 0.8


def test_coverage_min_fraction_out_of_range_rejected():
    with pytest.raises(ValidationError):
        CoverageScanningConfig(min_coverage_fraction=1.5)
    with pytest.raises(ValidationError):
        CoverageScanningConfig(min_coverage_fraction=-0.1)


def test_coverage_assertion_credit_rejects_unknown():
    with pytest.raises(ValidationError):
        CoverageScanningConfig(assertion_credit="bogus")
