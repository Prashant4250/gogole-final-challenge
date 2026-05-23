from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from redis import Redis

from app.models import CrowdSignal, StadiumStatusResponse, ZoneStatus, AppliedIntervention
from app.services.state_store import build_zone_status, zone_from_json, zone_storage_key, zone_to_json


class RedisStateStore:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    def upsert_signal(self, signal: CrowdSignal) -> ZoneStatus:
        zone = build_zone_status(signal)
        zone.applied_interventions = self.get_applied_interventions(signal.tenant_id, signal.stadium_id, signal.zone_id)
        
        zone_key = zone_storage_key(signal.tenant_id, signal.stadium_id, signal.zone_id)
        stadium_key = f"crowdflow:stadium:{signal.tenant_id}:{signal.stadium_id}:zones"
        hot_zones_key = "crowdflow:hot-zones"

        pipeline = self._redis.pipeline()
        pipeline.set(zone_key, zone_to_json(zone))
        pipeline.sadd(stadium_key, zone_key)
        pipeline.zadd(hot_zones_key, {zone_key: zone.risk_score})
        pipeline.execute()
        return zone

    def get_stadium_status(self, tenant_id: str, stadium_id: str) -> StadiumStatusResponse:
        stadium_key = f"crowdflow:stadium:{tenant_id}:{stadium_id}:zones"
        zone_keys = [
            key.decode("utf-8") if isinstance(key, bytes) else key
            for key in self._redis.smembers(stadium_key)
        ]
        payloads = self._redis.mget(zone_keys) if zone_keys else []
        zones = []
        for payload in payloads:
            if not payload:
                continue
            zone = zone_from_json(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
            zone.applied_interventions = self.get_applied_interventions(tenant_id, stadium_id, zone.zone_id)
            zones.append(zone)
        zones.sort(key=lambda zone: (zone.risk_score, zone.zone_id), reverse=True)
        return StadiumStatusResponse(
            tenant_id=tenant_id,
            stadium_id=stadium_id,
            generated_at=datetime.utcnow(),
            zones=zones,
        )

    def hot_zones(self, threshold: float = 0.8) -> dict[str, list[ZoneStatus]]:
        zone_keys = [
            key.decode("utf-8") if isinstance(key, bytes) else key
            for key in self._redis.zrangebyscore("crowdflow:hot-zones", threshold, 1.0)
        ]
        payloads = self._redis.mget(zone_keys) if zone_keys else []
        result: dict[str, list[ZoneStatus]] = defaultdict(list)
        for payload in payloads:
            if not payload:
                continue
            zone = zone_from_json(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
            zone.applied_interventions = self.get_applied_interventions(zone.tenant_id, zone.stadium_id, zone.zone_id)
            result[f"{zone.tenant_id}:{zone.stadium_id}"].append(zone)
        return result

    def apply_intervention(self, tenant_id: str, stadium_id: str, zone_id: str, action: str, reason: str) -> None:
        intervention = AppliedIntervention(
            action=action,
            reason=reason,
            applied_at=datetime.utcnow()
        )
        key = f"crowdflow:interventions:{tenant_id}:{stadium_id}:{zone_id}"
        self._redis.rpush(key, json.dumps(intervention.model_dump(), default=str))

        zone_key = zone_storage_key(tenant_id, stadium_id, zone_id)
        zone_payload = self._redis.get(zone_key)
        if zone_payload:
            zone = zone_from_json(zone_payload.decode("utf-8") if isinstance(zone_payload, bytes) else zone_payload)
            zone.applied_interventions = self.get_applied_interventions(tenant_id, stadium_id, zone_id)
            self._redis.set(zone_key, zone_to_json(zone))

    def get_applied_interventions(self, tenant_id: str, stadium_id: str, zone_id: str) -> list[AppliedIntervention]:
        key = f"crowdflow:interventions:{tenant_id}:{stadium_id}:{zone_id}"
        raw_interventions = self._redis.lrange(key, 0, -1)
        interventions = []
        for r in raw_interventions:
            if not r:
                continue
            try:
                data = json.loads(r.decode("utf-8") if isinstance(r, bytes) else r)
                if isinstance(data.get("applied_at"), str):
                    dt_str = data["applied_at"].replace("Z", "+00:00")
                    data["applied_at"] = datetime.fromisoformat(dt_str)
                interventions.append(AppliedIntervention.model_validate(data))
            except Exception:
                continue
        return interventions