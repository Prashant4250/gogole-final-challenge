from __future__ import annotations

from app.models import Recommendation, Severity, ZoneStatus


def get_recommendations(zone: ZoneStatus) -> list[Recommendation]:
    recs: list[Recommendation] = []

    if zone.occupancy_ratio >= 0.95:
        recs.append(
            Recommendation(
                action="soft_close_entry",
                reason="Zone occupancy is near safe capacity.",
                target_zone=zone.zone_id,
                severity=Severity.high,
            )
        )

    if zone.net_flow_per_min > 80:
        recs.append(
            Recommendation(
                action="reroute_inbound",
                reason="Inbound flow significantly exceeds outbound flow.",
                target_zone=zone.zone_id,
                severity=Severity.high,
            )
        )

    if zone.risk_score >= 0.8:
        recs.append(
            Recommendation(
                action="activate_incident_command",
                reason="Critical crowd risk detected.",
                target_zone=zone.zone_id,
                severity=Severity.critical,
            )
        )

    if zone.risk_score < 0.3:
        recs.append(
            Recommendation(
                action="normal_monitoring",
                reason="Risk is low. Continue monitoring.",
                target_zone=zone.zone_id,
                severity=Severity.low,
            )
        )

    return recs
