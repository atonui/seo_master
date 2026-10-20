from datetime import date, timedelta

import pytest

from app.schemas.metrics import MetricPoint
from app.services.metric_comparison import compare_periods


def points(start: date, values: list[float], metric: str = "clicks") -> list[MetricPoint]:
    return [MetricPoint(date=start + timedelta(days=index), metric=metric, value=value) for index, value in enumerate(values)]


def test_period_comparison_uses_equal_length_windows() -> None:
    current = points(date(2026, 10, 1), [1, 2, 3, 4, 5, 6, 7])
    previous = points(date(2026, 9, 24), [1, 1, 1, 1, 1, 1, 1])

    result = compare_periods(current, previous)

    assert len(result) == 1
    assert result[0].current_value == 28
    assert result[0].previous_value == 7
    assert result[0].absolute_change == 21
    assert result[0].percent_change == 300


def test_mismatched_period_lengths_are_rejected() -> None:
    current = points(date(2026, 10, 1), [1, 2, 3, 4, 5, 6, 7])
    previous = points(date(2026, 9, 24), [1, 1, 1])

    with pytest.raises(ValueError, match="equal-length"):
        compare_periods(current, previous)


def test_zero_baseline_has_defined_delta_state() -> None:
    current = points(date(2026, 10, 1), [2, 0, 0])
    previous = points(date(2026, 9, 28), [0, 0, 0])

    result = compare_periods(current, previous)[0]

    assert result.current_value == 2
    assert result.previous_value == 0
    assert result.absolute_change == 2
    assert result.percent_change is None
    assert result.status == "no_baseline"


def test_rates_use_their_weights_when_comparing_periods() -> None:
    current = [
        MetricPoint(date=date(2026, 10, 1), metric="ctr", value=0.1, weight=100),
        MetricPoint(date=date(2026, 10, 2), metric="ctr", value=0.5, weight=10),
    ]
    previous = [
        MetricPoint(date=date(2026, 9, 29), metric="ctr", value=0.1, weight=100),
        MetricPoint(date=date(2026, 9, 30), metric="ctr", value=0.1, weight=10),
    ]

    result = compare_periods(current, previous)[0]

    assert result.current_value == pytest.approx((0.1 * 100 + 0.5 * 10) / 110)
    assert result.previous_value == pytest.approx(0.1)
