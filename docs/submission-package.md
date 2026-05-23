# Submission Package

## Problem framing

CrowdFlow Command is designed for venues where crowd risk evolves faster than human operators can reconcile fragmented inputs. The system turns live telemetry into a single operational picture, ranks risk by zone, and suggests interventions before localized congestion becomes a safety incident.

## What is implemented in this repo

- Multi-tenant ingest and query API.
- Deterministic risk scoring and intervention recommendation engine.
- Operator dashboard for live viewing and demo-mode validation.
- Configurable local backend with in-memory or Redis storage.
- Optional Google Pub/Sub publishing for downstream services.

## How this maps to a Google-scale deployment

- Cloud Run for stateless API scale-out.
- Pub/Sub for resilient event fan-out.
- Dataflow for streaming transforms and anomaly windows.
- Memorystore for low-latency venue state.
- BigQuery for after-action reporting, forecasting, and product analytics.
- Vertex AI for predictive signals layered on top of the rules engine.

## Evaluation talking points

- Fast operational feedback with explainable recommendations.
- Designed for concurrent tenants and many simultaneous live events.
- Clear path from demo mode to production infrastructure.
- UI and APIs are already aligned around a command-center workflow.

## Demo script

1. Open the dashboard at `/`.
2. Click `Load demo surge`.
3. Show the highest-risk zone, hot-zone rail, and action feed.
4. Explain how the same ingest call can publish to Pub/Sub and update Redis-backed state.
5. Walk through the production architecture diagram and tradeoff notes.