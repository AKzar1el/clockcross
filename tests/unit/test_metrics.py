import numpy as np
import pytest

from clockcross.research.metrics import summarize_returns


def test_metrics_report_leave_one_out_outlier_sensitivity() -> None:
    summary = summarize_returns(np.array([0.01, 0.01, 0.01, 0.50]))
    assert summary.count == 4
    assert summary.best == pytest.approx(0.50)
    assert summary.worst == pytest.approx(0.01)
    assert summary.mean > summary.median
    assert summary.leave_one_out_max_mean_impact > 0.10
