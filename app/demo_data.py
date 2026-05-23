from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import CrowdSignal, SignalIngestRequest


def demo_signal_request() -> SignalIngestRequest:
    now = datetime.now(timezone.utc)
    signals = [
        CrowdSignal(
            tenant_id="league-x",
            stadium_id="stadium-1",
            zone_id="north-gate",
            timestamp=now,
            occupancy=1920,
            safe_capacity=2000,
            ingress_per_min=260,
            egress_per_min=105,
            incident_count=1,
            weather_risk=0.4,
            source="camera",
            confidence=0.94,
        ),
        CrowdSignal(
            tenant_id="league-x",
            stadium_id="stadium-1",
            zone_id="east-concourse",
            timestamp=now + timedelta(seconds=10),
            occupancy=1430,
            safe_capacity=1600,
            ingress_per_min=155,
            egress_per_min=88,
            incident_count=0,
            weather_risk=0.2,
            source="iot",
            confidence=0.9,
        ),
        CrowdSignal(
            tenant_id="league-x",
            stadium_id="stadium-1",
            zone_id="south-exit",
            timestamp=now + timedelta(seconds=20),
            occupancy=820,
            safe_capacity=1500,
            ingress_per_min=70,
            egress_per_min=140,
            incident_count=0,
            weather_risk=0.1,
            source="ticketing",
            confidence=0.88,
        ),
        CrowdSignal(
            tenant_id="league-x",
            stadium_id="stadium-1",
            zone_id="west-stand",
            timestamp=now + timedelta(seconds=30),
            occupancy=2110,
            safe_capacity=2200,
            ingress_per_min=230,
            egress_per_min=120,
            incident_count=2,
            weather_risk=0.6,
            source="manual",
            confidence=0.82,
        ),
    ]
    return SignalIngestRequest(signals=signals)