from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.deps import get_auth_service, get_publisher, get_store
from app.demo_data import demo_signal_request
from app.models import (
    AuthResponse,
    ChatRequest,
    ChatResponse,
    LoginRequest,
    SignalIngestRequest,
    SignupRequest,
    StadiumStatusResponse,
    UserPreferences,
    UserStateResponse,
    ZoneStatus,
    ApplyInterventionRequest,
    StadiumWeatherResponse,
)
from app.services.chat_assistant import answer_question
from app.services.discovery_service import DiscoveryService
from app.services.weather_service import WeatherService

app = FastAPI(
    title="CrowdFlow Command API",
    description="Real-time crowd risk scoring and routing recommendations.",
    version="0.1.0",
)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

store = get_store()
publisher = get_publisher()
auth_service = get_auth_service()
discovery_service = DiscoveryService()
weather_service = WeatherService(store)


def bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization token is required.")
    return authorization.removeprefix("Bearer ").strip()


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(
        static_dir / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/v1/signals", response_model=list[ZoneStatus])
def ingest_signals(payload: SignalIngestRequest) -> list[ZoneStatus]:
    updated = []
    for signal in payload.signals:
        zone = store.upsert_signal(signal)
        publisher.publish_signal(signal, zone)
        updated.append(zone)
    return updated


@app.get("/v1/stadiums/{stadium_id}/status", response_model=StadiumStatusResponse)
def stadium_status(
    stadium_id: str,
    tenant_id: str = Query(..., description="Tenant id for multi-tenant isolation"),
) -> StadiumStatusResponse:
    status = store.get_stadium_status(tenant_id=tenant_id, stadium_id=stadium_id)
    if not status.zones:
        raise HTTPException(
            status_code=404,
            detail="No signals found for the given tenant and stadium.",
        )
    return status


@app.get("/v1/hot-zones")
def hot_zones(min_score: float = Query(0.8, ge=0.0, le=1.0)) -> dict[str, list[ZoneStatus]]:
    return store.hot_zones(threshold=min_score)


@app.get("/v1/config")
def runtime_config() -> dict[str, str]:
    return {
        "store_backend": settings.store_backend,
        "publisher_backend": settings.publisher_backend,
        "auth_backend": settings.auth_backend,
        "dashboard_default_tenant": settings.dashboard_default_tenant,
        "dashboard_default_stadium": settings.dashboard_default_stadium,
        "guest_mode_enabled": "true",
    }


def active_pairs() -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = {
        (settings.dashboard_default_tenant, settings.dashboard_default_stadium)
    }
    for key in store.hot_zones(threshold=0.0).keys():
        tenant_id, stadium_id = key.split(":", maxsplit=1)
        pairs.add((tenant_id, stadium_id))
    return sorted(pairs)


@app.get("/v1/discovery/tenants")
def tenant_suggestions(
    q: str = Query("", max_length=120),
    limit: int = Query(8, ge=1, le=20),
) -> dict[str, list[dict[str, str]]]:
    return {
        "items": discovery_service.suggestions(
            kind="tenant",
            query=q,
            active_pairs=active_pairs(),
            limit=limit,
        )
    }


@app.get("/v1/discovery/stadiums")
def stadium_suggestions(
    q: str = Query("", max_length=120),
    tenant_id: Optional[str] = Query(default=None),
    limit: int = Query(8, ge=1, le=20),
) -> dict[str, list[dict[str, str]]]:
    return {
        "items": discovery_service.suggestions(
            kind="stadium",
            query=q,
            tenant_id=tenant_id,
            active_pairs=active_pairs(),
            limit=limit,
        )
    }


@app.get("/v1/demo/signals", response_model=SignalIngestRequest)
def demo_signals() -> SignalIngestRequest:
    return demo_signal_request()


@app.get("/v1/weather/current", response_model=StadiumWeatherResponse)
def current_weather(
    stadium_id: str = Query(..., min_length=1),
    tenant_id: str = Query(settings.dashboard_default_tenant, min_length=1),
    latitude: Optional[float] = Query(default=None, ge=-90.0, le=90.0),
    longitude: Optional[float] = Query(default=None, ge=-180.0, le=180.0),
) -> StadiumWeatherResponse:
    return weather_service.current_weather(
        tenant_id=tenant_id,
        stadium_id=stadium_id,
        latitude=latitude,
        longitude=longitude,
    )


@app.post("/v1/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    authorization: Optional[str] = Header(default=None),
    x_gemini_api_key: Optional[str] = Header(default=None, alias="X-Gemini-API-Key"),
) -> ChatResponse:
    status = store.get_stadium_status(payload.tenant_id, payload.stadium_id)
    response = answer_question(payload.message, status, api_key=x_gemini_api_key)

    if authorization:
        token = bearer_token(authorization)
        user = auth_service.authenticate(token)
        auth_service.save_chat_exchange(user.id, payload.message, response.answer)

    return response


@app.post("/v1/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest) -> AuthResponse:
    token, user = auth_service.signup(payload.email, payload.password, payload.full_name)
    return AuthResponse(token=token, user=user)


@app.post("/v1/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    token, user = auth_service.login(payload.email, payload.password)
    return AuthResponse(token=token, user=user)


@app.get("/v1/auth/me", response_model=UserStateResponse)
def auth_me(authorization: Optional[str] = Header(default=None)) -> UserStateResponse:
    token = bearer_token(authorization)
    user = auth_service.authenticate(token)
    return auth_service.get_user_state(user.id)


@app.put("/v1/user/preferences", response_model=UserPreferences)
def update_preferences(
    payload: UserPreferences,
    authorization: Optional[str] = Header(default=None),
) -> UserPreferences:
    token = bearer_token(authorization)
    user = auth_service.authenticate(token)
    return auth_service.update_preferences(user.id, payload.tenant_id, payload.stadium_id)


@app.post("/v1/stadiums/{stadium_id}/zones/{zone_id}/interventions")
def apply_zone_intervention(
    stadium_id: str,
    zone_id: str,
    payload: ApplyInterventionRequest,
    tenant_id: str = Query(..., description="Tenant id for multi-tenant isolation"),
) -> dict[str, str]:
    # Normalize zone_id
    normalized_zone = zone_id.lower().replace(" ", "-").strip()
    store.apply_intervention(
        tenant_id=tenant_id,
        stadium_id=stadium_id,
        zone_id=normalized_zone,
        action=payload.action,
        reason=payload.reason
    )
    return {"status": "success", "message": f"Intervention '{payload.action}' applied to zone '{normalized_zone}'"}
