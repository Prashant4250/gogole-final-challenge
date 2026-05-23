from __future__ import annotations

from functools import lru_cache
from typing import Any

from redis import Redis

from app.config import settings
from app.services.auth_service import AuthService
from app.services.publishers import NoopPublisher, PubSubPublisher, SignalPublisher
from app.services.redis_store import RedisStateStore
from app.services.state_store import InMemoryStateStore, StateStore


@lru_cache
def get_store() -> StateStore:
    if settings.store_backend == "redis":
        return RedisStateStore(Redis.from_url(settings.redis_url, decode_responses=False))
    return InMemoryStateStore()


@lru_cache
def get_publisher() -> SignalPublisher:
    if settings.publisher_backend == "pubsub" and settings.pubsub_topic:
        return PubSubPublisher(settings.pubsub_topic)
    return NoopPublisher()


@lru_cache
def get_auth_service() -> Any:
    if settings.auth_backend == "firestore":
        from app.services.auth_firestore_service import FirestoreAuthService

        return FirestoreAuthService(
            project_id=settings.gcp_project_id,
            default_tenant=settings.dashboard_default_tenant,
            default_stadium=settings.dashboard_default_stadium,
            collection_prefix=settings.firestore_collection_prefix,
        )

    return AuthService(
        db_path=settings.auth_db_path,
        default_tenant=settings.dashboard_default_tenant,
        default_stadium=settings.dashboard_default_stadium,
    )