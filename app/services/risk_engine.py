from __future__ import annotations

from app.models import CrowdSignal, Severity


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def calculate_risk(signal: CrowdSignal) -> tuple[float, Severity]:
    occupancy_ratio = signal.occupancy / signal.safe_capacity
    occupancy_component = clamp(occupancy_ratio / 1.2)

    net_flow = signal.ingress_per_min - signal.egress_per_min
    pressure_component = clamp((net_flow + 100) / 250)

    incident_component = clamp(signal.incident_count / 5)
    weather_component = clamp(signal.weather_risk)
    confidence_penalty = 1 - signal.confidence

    score = (
        0.38 * occupancy_component
        + 0.24 * pressure_component
        + 0.20 * incident_component
        + 0.12 * weather_component
        + 0.06 * confidence_penalty
    )
    score = round(clamp(score), 4)

    if score < 0.3:
        severity = Severity.low
    elif score < 0.55:
        severity = Severity.medium
    elif score < 0.8:
        severity = Severity.high
    else:
        severity = Severity.critical

    return score, severity
