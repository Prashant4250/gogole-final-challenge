# API Contract

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Operator dashboard |
| GET | `/health` | Liveness and timestamp |
| POST | `/v1/signals` | Ingest one or more crowd signals |
| GET | `/v1/stadiums/{stadium_id}/status` | Query ranked zone status for a stadium |
| GET | `/v1/hot-zones` | Query hot zones above a score threshold |
| GET | `/v1/config` | Runtime backend config for the dashboard |
| GET | `/v1/demo/signals` | Demo dataset for local validation |

## POST /v1/signals

Request body:

```json
{
  "signals": [
    {
      "tenant_id": "league-x",
      "stadium_id": "stadium-1",
      "zone_id": "north-gate",
      "timestamp": "2026-05-23T09:30:00Z",
      "occupancy": 1900,
      "safe_capacity": 2000,
      "ingress_per_min": 250,
      "egress_per_min": 110,
      "incident_count": 1,
      "weather_risk": 0.6,
      "source": "camera",
      "confidence": 0.9
    }
  ]
}
```

Response body:

```json
[
  {
    "tenant_id": "league-x",
    "stadium_id": "stadium-1",
    "zone_id": "north-gate",
    "occupancy": 1900,
    "safe_capacity": 2000,
    "occupancy_ratio": 0.95,
    "net_flow_per_min": 140,
    "risk_score": 0.74,
    "severity": "high",
    "recommendations": [
      {
        "action": "soft_close_entry",
        "reason": "Zone occupancy is near safe capacity.",
        "target_zone": "north-gate",
        "severity": "high"
      }
    ],
    "last_update": "2026-05-23T09:30:00Z"
  }
]
```

## GET /v1/stadiums/{stadium_id}/status

Query params:

- `tenant_id`: required, enforces multi-tenant scope.

Behavior:

- Returns `404` when the tenant and stadium combination has no active data.
- Returns zones ordered by descending risk score.

## GET /v1/hot-zones

Query params:

- `min_score`: optional float from `0.0` to `1.0`, default `0.8`.

Response shape:

```json
{
  "league-x:stadium-1": [
    {
      "zone_id": "north-gate",
      "risk_score": 0.84,
      "severity": "critical"
    }
  ]
}
```

## Compatibility notes

- The local default backend is in-memory for zero-friction demos and tests.
- Set `CROWDFLOW_STORE_BACKEND=redis` to switch reads and writes to Redis.
- Set `CROWDFLOW_PUBLISHER_BACKEND=pubsub` and `CROWDFLOW_PUBSUB_TOPIC` to emit enriched events to Google Pub/Sub.