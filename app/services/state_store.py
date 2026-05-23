from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from threading import Lock
from typing import Protocol

from app.models import CrowdSignal, StadiumStatusResponse, ZoneStatus, AppliedIntervention
from app.services.recommender import get_recommendations
from app.services.risk_engine import calculate_risk


class StateStore(Protocol):
    def upsert_signal(self, signal: CrowdSignal) -> ZoneStatus:
        ...

    def get_stadium_status(self, tenant_id: str, stadium_id: str) -> StadiumStatusResponse:
        ...

    def hot_zones(self, threshold: float = 0.8) -> dict[str, list[ZoneStatus]]:
        ...

    def apply_intervention(self, tenant_id: str, stadium_id: str, zone_id: str, action: str, reason: str) -> None:
        ...

    def get_applied_interventions(self, tenant_id: str, stadium_id: str, zone_id: str) -> list[AppliedIntervention]:
        ...


def build_zone_status(signal: CrowdSignal) -> ZoneStatus:
    score, severity = calculate_risk(signal)
    occupancy_ratio = round(signal.occupancy / signal.safe_capacity, 4)
    net_flow_per_min = round(signal.ingress_per_min - signal.egress_per_min, 2)

    zone = ZoneStatus(
        tenant_id=signal.tenant_id,
        stadium_id=signal.stadium_id,
        zone_id=signal.zone_id,
        occupancy=signal.occupancy,
        safe_capacity=signal.safe_capacity,
        occupancy_ratio=occupancy_ratio,
        net_flow_per_min=net_flow_per_min,
        risk_score=score,
        weather_risk=round(signal.weather_risk, 4),
        severity=severity,
        recommendations=[],
        applied_interventions=[],
        last_update=signal.timestamp,
    )
    zone.recommendations = get_recommendations(zone)
    return zone


def zone_storage_key(tenant_id: str, stadium_id: str, zone_id: str) -> str:
    return f"crowdflow:zone:{tenant_id}:{stadium_id}:{zone_id}"


def zone_to_json(zone: ZoneStatus) -> str:
    return zone.model_dump_json()


def zone_from_json(payload: str) -> ZoneStatus:
    return ZoneStatus.model_validate(json.loads(payload))


class InMemoryStateStore:
    """Thread-safe in-memory store for local development and demos."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._zones: dict[tuple[str, str, str], ZoneStatus] = {}
        self._interventions: dict[tuple[str, str, str], list[AppliedIntervention]] = {}

    def upsert_signal(self, signal: CrowdSignal) -> ZoneStatus:
        zone = build_zone_status(signal)

        with self._lock:
            key = (signal.tenant_id, signal.stadium_id, signal.zone_id)
            self._zones[key] = zone
            zone.applied_interventions = self._interventions.get(key, [])

        return zone

    def get_stadium_status(self, tenant_id: str, stadium_id: str) -> StadiumStatusResponse:
        with self._lock:
            zones = [
                z
                for (t_id, s_id, _), z in self._zones.items()
                if t_id == tenant_id and s_id == stadium_id
            ]
            # Refresh applied interventions
            for z in zones:
                key = (tenant_id, stadium_id, z.zone_id)
                z.applied_interventions = self._interventions.get(key, [])

        zones.sort(key=lambda z: (z.risk_score, z.zone_id), reverse=True)

        return StadiumStatusResponse(
            tenant_id=tenant_id,
            stadium_id=stadium_id,
            generated_at=datetime.utcnow(),
            zones=zones,
        )

    def hot_zones(self, threshold: float = 0.8) -> dict[str, list[ZoneStatus]]:
        result: dict[str, list[ZoneStatus]] = defaultdict(list)
        with self._lock:
            for zone in self._zones.values():
                key = (zone.tenant_id, zone.stadium_id, zone.zone_id)
                zone.applied_interventions = self._interventions.get(key, [])
                if zone.risk_score >= threshold:
                    map_key = f"{zone.tenant_id}:{zone.stadium_id}"
                    result[map_key].append(zone)
        return result

    def apply_intervention(self, tenant_id: str, stadium_id: str, zone_id: str, action: str, reason: str) -> None:
        intervention = AppliedIntervention(
            action=action,
            reason=reason,
            applied_at=datetime.utcnow()
        )
        with self._lock:
            key = (tenant_id, stadium_id, zone_id)
            if key not in self._interventions:
                self._interventions[key] = []
            self._interventions[key].append(intervention)
            if key in self._zones:
                self._zones[key].applied_interventions = self._interventions[key]

    def get_applied_interventions(self, tenant_id: str, stadium_id: str, zone_id: str) -> list[AppliedIntervention]:
        with self._lock:
            return self._interventions.get((tenant_id, stadium_id, zone_id), [])
