from __future__ import annotations

import json
from typing import Protocol

from app.models import CrowdSignal, ZoneStatus


class SignalPublisher(Protocol):
    def publish_signal(self, signal: CrowdSignal, zone: ZoneStatus) -> None:
        ...


class NoopPublisher:
    def publish_signal(self, signal: CrowdSignal, zone: ZoneStatus) -> None:
        return None


class PubSubPublisher:
    def __init__(self, topic_path: str) -> None:
        from google.cloud import pubsub_v1

        self._client = pubsub_v1.PublisherClient()
        self._topic_path = topic_path

    def publish_signal(self, signal: CrowdSignal, zone: ZoneStatus) -> None:
        payload = json.dumps(
            {
                "signal": signal.model_dump(mode="json"),
                "zone_status": zone.model_dump(mode="json"),
            }
        ).encode("utf-8")
        future = self._client.publish(
            self._topic_path,
            payload,
            tenant_id=signal.tenant_id,
            stadium_id=signal.stadium_id,
            zone_id=signal.zone_id,
        )
        future.result(timeout=5)