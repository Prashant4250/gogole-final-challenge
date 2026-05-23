from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CrowdSignal(BaseModel):
    tenant_id: str = Field(..., description="Operator or league tenant identifier")
    stadium_id: str = Field(..., description="Stadium identifier")
    zone_id: str = Field(..., description="Zone within stadium")
    timestamp: datetime
    occupancy: int = Field(..., ge=0, description="People currently in zone")
    safe_capacity: int = Field(..., gt=0, description="Configured safe max capacity")
    ingress_per_min: float = Field(..., ge=0)
    egress_per_min: float = Field(..., ge=0)
    incident_count: int = Field(0, ge=0)
    weather_risk: float = Field(0.0, ge=0.0, le=1.0)
    source: Literal["camera", "ticketing", "iot", "manual"] = "camera"
    confidence: float = Field(0.7, ge=0.0, le=1.0)


class SignalIngestRequest(BaseModel):
    signals: list[CrowdSignal] = Field(..., min_length=1, max_length=1000)


class Recommendation(BaseModel):
    action: str
    reason: str
    target_zone: str
    severity: Severity


class AppliedIntervention(BaseModel):
    action: str
    reason: str
    applied_at: datetime


class ApplyInterventionRequest(BaseModel):
    action: str
    reason: str


class ZoneStatus(BaseModel):
    tenant_id: str
    stadium_id: str
    zone_id: str
    occupancy: int
    safe_capacity: int
    occupancy_ratio: float
    net_flow_per_min: float
    risk_score: float
    weather_risk: float = Field(0.0, ge=0.0, le=1.0)
    severity: Severity
    recommendations: list[Recommendation]
    applied_interventions: list[AppliedIntervention] = Field(default_factory=list)
    last_update: datetime


class StadiumStatusResponse(BaseModel):
    tenant_id: str
    stadium_id: str
    generated_at: datetime
    zones: list[ZoneStatus]


class StadiumWeatherResponse(BaseModel):
    tenant_id: str
    stadium_id: str
    city_name: Optional[str] = None
    source: str
    condition: str
    temperature_c: float
    precipitation_probability: int = Field(..., ge=0, le=100)
    wind_kph: float
    updated_at: datetime


class ChatRequest(BaseModel):
    tenant_id: str
    stadium_id: str
    message: str = Field(..., min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    answer: str
    suggested_questions: list[str] = Field(default_factory=list)
    thoughts: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    id: int
    email: str
    full_name: str


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=255)
    full_name: str = Field(..., min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=255)


class AuthResponse(BaseModel):
    token: str
    user: UserProfile


class UserPreferences(BaseModel):
    tenant_id: str
    stadium_id: str


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    message: str
    created_at: datetime


class UserStateResponse(BaseModel):
    user: UserProfile
    preferences: UserPreferences
    chat_history: list[ChatHistoryItem]
