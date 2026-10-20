from app.schemas.metrics import MetricDelta, MetricPoint


WEIGHTED_METRICS = {"ctr", "average_position", "position", "engagement_rate", "invite_conversion_rate"}


def _validate_window(points: list[MetricPoint], label: str) -> int:
    days = {point.date for point in points}
    if not days:
        return 0
    first, last = min(days), max(days)
    expected_days = (last - first).days + 1
    if len(days) != expected_days:
        raise ValueError(f"{label} period must contain one point date for every day")
    return expected_days


def _aggregate(points: list[MetricPoint], metric: str) -> float:
    metric_points = [point for point in points if point.metric == metric]
    if metric in WEIGHTED_METRICS:
        total_weight = sum(max(point.weight, 0.0) for point in metric_points)
        if total_weight == 0:
            return 0.0
        return sum(point.value * max(point.weight, 0.0) for point in metric_points) / total_weight
    return sum(point.value for point in metric_points)


def compare_periods(current: list[MetricPoint], previous: list[MetricPoint]) -> list[MetricDelta]:
    current_days = _validate_window(current, "Current")
    previous_days = _validate_window(previous, "Previous")
    if current_days != previous_days:
        raise ValueError("Current and previous periods must be equal-length windows")
    metrics = sorted({point.metric for point in current} | {point.metric for point in previous})
    deltas: list[MetricDelta] = []
    for metric in metrics:
        current_value = _aggregate(current, metric)
        previous_value = _aggregate(previous, metric)
        absolute_change = current_value - previous_value
        has_baseline = previous_value != 0
        deltas.append(MetricDelta(
            metric=metric,
            current_value=current_value,
            previous_value=previous_value,
            absolute_change=absolute_change,
            percent_change=(absolute_change / previous_value * 100) if has_baseline else None,
            status="comparable" if has_baseline else "no_baseline",
        ))
    return deltas
