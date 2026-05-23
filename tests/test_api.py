from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ingest_and_status() -> None:
    payload = {
        "signals": [
            {
                "tenant_id": "league-x",
                "stadium_id": "stadium-1",
                "zone_id": "north-gate",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "occupancy": 1900,
                "safe_capacity": 2000,
                "ingress_per_min": 250,
                "egress_per_min": 110,
                "incident_count": 1,
                "weather_risk": 0.6,
                "source": "camera",
                "confidence": 0.9,
            }
        ]
    }

    ingest = client.post("/v1/signals", json=payload)
    assert ingest.status_code == 200
    body = ingest.json()
    assert body[0]["zone_id"] == "north-gate"
    assert body[0]["risk_score"] > 0

    status = client.get("/v1/stadiums/stadium-1/status", params={"tenant_id": "league-x"})
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["stadium_id"] == "stadium-1"
    assert len(status_body["zones"]) == 1


def test_404_when_no_stadium_data() -> None:
    response = client.get("/v1/stadiums/unknown/status", params={"tenant_id": "league-x"})
    assert response.status_code == 404


def test_dashboard_and_config_routes() -> None:
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "CrowdFlow Command" in dashboard.text

    config = client.get("/v1/config")
    assert config.status_code == 200
    body = config.json()
    assert body["store_backend"] in {"memory", "redis"}


def test_discovery_suggestions() -> None:
    tenant = client.get("/v1/discovery/tenants", params={"q": "league"})
    assert tenant.status_code == 200
    tenant_body = tenant.json()
    assert "items" in tenant_body
    assert isinstance(tenant_body["items"], list)

    stadium = client.get(
        "/v1/discovery/stadiums",
        params={"q": "stadium", "tenant_id": "league-x"},
    )
    assert stadium.status_code == 200
    stadium_body = stadium.json()
    assert "items" in stadium_body
    assert isinstance(stadium_body["items"], list)


def test_demo_dataset_available() -> None:
    response = client.get("/v1/demo/signals")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["signals"]) >= 3


def test_weather_endpoint_returns_snapshot() -> None:
    response = client.get(
        "/v1/weather/current",
        params={"tenant_id": "league-x", "stadium_id": "stadium-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stadium_id"] == "stadium-1"
    assert body["source"] in {"open-meteo", "fallback"}
    assert isinstance(body.get("city_name"), str)
    assert body["city_name"].strip()
    assert isinstance(body["temperature_c"], (int, float))
    assert 0 <= body["precipitation_probability"] <= 100


def test_weather_endpoint_accepts_location_coordinates() -> None:
    response = client.get(
        "/v1/weather/current",
        params={
            "tenant_id": "league-x",
            "stadium_id": "stadium-1",
            "latitude": 28.6139,
            "longitude": 77.2090,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stadium_id"] == "stadium-1"
    assert body["source"] in {"open-meteo", "fallback"}
    assert isinstance(body["temperature_c"], (int, float))
    assert 0 <= body["precipitation_probability"] <= 100


def test_chat_endpoint_answers_from_live_status() -> None:
    demo_payload = client.get("/v1/demo/signals").json()
    client.post("/v1/signals", json=demo_payload)

    response = client.post(
        "/v1/chat",
        json={
            "tenant_id": "league-x",
            "stadium_id": "stadium-1",
            "message": "What is the highest risk zone?",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "Highest current risk" in body["answer"]
    assert len(body["suggested_questions"]) >= 1


def test_signup_login_and_persisted_user_state() -> None:
    email = f"ops-{uuid.uuid4().hex[:8]}@example.com"
    signup = client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "VeryStrong123",
            "full_name": "Ops User",
        },
    )
    assert signup.status_code == 200
    auth_body = signup.json()
    token = auth_body["token"]

    pref_update = client.put(
        "/v1/user/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"tenant_id": "league-z", "stadium_id": "stadium-9"},
    )
    assert pref_update.status_code == 200

    demo_payload = client.get("/v1/demo/signals").json()
    client.post("/v1/signals", json=demo_payload)
    chat = client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tenant_id": "league-x",
            "stadium_id": "stadium-1",
            "message": "Give me a stadium summary.",
        },
    )
    assert chat.status_code == 200

    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    state = me.json()
    assert state["user"]["email"] == email
    assert state["preferences"]["tenant_id"] == "league-z"
    assert len(state["chat_history"]) >= 2


def test_manual_interventions() -> None:
    demo_payload = client.get("/v1/demo/signals").json()
    client.post("/v1/signals", json=demo_payload)

    intervention_payload = {
        "action": "soft_close_entry",
        "reason": "Test intervention reason"
    }
    response = client.post(
        "/v1/stadiums/stadium-1/zones/north-gate/interventions",
        params={"tenant_id": "league-x"},
        json=intervention_payload
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    status = client.get("/v1/stadiums/stadium-1/status", params={"tenant_id": "league-x"})
    assert status.status_code == 200
    status_body = status.json()
    
    north_gate = next(z for z in status_body["zones"] if z["zone_id"] == "north-gate")
    assert len(north_gate["applied_interventions"]) == 1
    assert north_gate["applied_interventions"][0]["action"] == "soft_close_entry"
    assert north_gate["applied_interventions"][0]["reason"] == "Test intervention reason"
