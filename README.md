# CrowdFlow Command: Scalable Stadium Safety Orchestration

This solution addresses the challenge statement you shared:

- Threat: dangerous bottlenecks, security vulnerabilities, and chaotic crowd movement.
- Gap: fragmented/manual operations cannot react fast enough.
- Need: integrated real-time command platform to unify inputs, route crowds, and automate emergency response.

## What this package delivers

- Real-time crowd signal ingestion API.
- Zone-level risk scoring engine.
- Automated action recommendations (reroute, soft-close entry, incident command activation).
- Multi-tenant isolation (`tenant_id`) so multiple organizers can use one platform safely.
- Query APIs for command-center dashboards.
- A live operator dashboard at `/`.
- Submission-ready design, API, and tradeoff documents in `docs/`.
- Configurable Redis and Pub/Sub adapters for production-style infrastructure.

## Architecture and submission docs

- `docs/system-design.md`: high-level system design with diagrams.
- `docs/api-contract.md`: endpoint contract and example payloads.
- `docs/tradeoffs.md`: engineering tradeoffs and rationale.
- `docs/submission-package.md`: concise pitch and demo script.

## Why this is scalable

The code in this repository is a production-aligned starter. For million-user scale, run it with this architecture:

1. Ingestion: API Gateway -> Cloud Run ingest service.
2. Streaming backbone: Pub/Sub topics partitioned by `tenant_id:stadium_id`.
3. Stateful processing: Dataflow (Apache Beam) for sliding windows and anomaly detection.
4. Hot state: Memorystore (Redis) for sub-second zone status reads.
5. Long-term analytics: BigQuery for historical trends and post-event analysis.
6. Rules/AI layer: Vertex AI endpoint + deterministic safety rules for explainable decisions.
7. Notification fanout: Pub/Sub + FCM/SMS/ops channels.
8. Operations: Cloud Monitoring + Error Reporting + SLO burn alerts.

## Reliability and security checklist

- Horizontal auto-scaling with Cloud Run concurrency limits.
- Idempotent event processing using `(tenant_id, stadium_id, zone_id, timestamp)` keys.
- Dead-letter topics for malformed/late events.
- Zero trust and IAM least privilege by service account.
- Data encryption in transit (TLS) and at rest.
- Multi-region failover for ingest and stream processing.
- Audit logs and tamper-evident event history.

## API quick start

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional local Redis stack:

```bash
docker compose up redis -d
export CROWDFLOW_STORE_BACKEND=redis
export CROWDFLOW_REDIS_URL=redis://127.0.0.1:6379/0
```

Optional Pub/Sub publishing:

```bash
export CROWDFLOW_PUBLISHER_BACKEND=pubsub
export CROWDFLOW_PUBSUB_TOPIC=projects/YOUR_PROJECT/topics/crowdflow-events
```

### Run

```bash
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/` for the operator dashboard.

## Authentication and guest mode

- Guest mode is available by default and does not store user data.
- Signed-in users can use email/password auth and get persisted preferences plus chat history.
- Authentication is token-based using `Authorization: Bearer <token>`.

### Store user details in Google Cloud (Firestore)

By default, auth data is stored in local SQLite. To store users, sessions, preferences, and chat history in Google Cloud:

1. Open Google Cloud Console and select your project.
2. Enable Firestore API.
3. Create a Firestore database (Native mode).
4. Create a service account with Firestore access (for example, `Cloud Datastore User`).
5. Download the JSON key and point `GOOGLE_APPLICATION_CREDENTIALS` to it.
6. Set backend environment variables:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/service-account.json"
export CROWDFLOW_AUTH_BACKEND=firestore
export CROWDFLOW_GCP_PROJECT_ID="your-gcp-project-id"
export CROWDFLOW_FIRESTORE_COLLECTION_PREFIX="crowdflow"
```

Then run the app normally:

```bash
uvicorn app.main:app --reload
```

When `CROWDFLOW_AUTH_BACKEND=firestore`, user details are persisted in Firestore instead of `crowdflow_auth.db`.

Auth endpoints:

- `POST /v1/auth/signup`
- `POST /v1/auth/login`
- `GET /v1/auth/me`
- `PUT /v1/user/preferences`

Example signup:

```bash
curl -X POST http://127.0.0.1:8000/v1/auth/signup \
  -H "content-type: application/json" \
  -d '{
    "email": "ops@example.com",
    "password": "VeryStrong123",
    "full_name": "Ops Commander"
  }'
```

### Example ingest

```bash
curl -X POST http://127.0.0.1:8000/v1/signals \
  -H "content-type: application/json" \
  -d '{
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
  }'
```

### Query stadium status

```bash
curl "http://127.0.0.1:8000/v1/stadiums/stadium-1/status?tenant_id=league-x"
```

### Load demo data

```bash
curl http://127.0.0.1:8000/v1/demo/signals | jq
```

## Running tests

```bash
pytest -q
```

## Suggested next upgrades for final submission

1. Add graph-based crowd routing so recommendations can name alternate paths instead of only affected zones.
2. Integrate live camera inference and ticket scanner telemetry adapters.
3. Add role-based dashboard views for incident command, stewards, and security operations.
4. Add load tests with k6 or Locust for ingress spikes and evacuation drills.
5. Add a durable event replay pipeline for post-incident forensic analysis.
