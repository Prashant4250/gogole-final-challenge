# Tradeoffs and Rationale

## Why synchronous scoring at ingest time

Scoring risk during the ingest request gives operators immediate feedback and keeps the dashboard simple. The tradeoff is that request latency includes the scoring path. That is acceptable because the current scoring model is lightweight and deterministic.

## Why Redis for hot state

Redis is a strong fit for high-frequency operational reads, sorted hot-zone views, and predictable latency. The tradeoff is operational overhead and key-design discipline. For broad analytics, Redis is insufficient on its own, which is why it is paired with an event stream and warehouse.

## Why Pub/Sub for downstream fan-out

Publishing enriched events decouples command operations, notifications, analytics, and ML retraining. The tradeoff is eventual consistency for downstream consumers, but the command-center read path stays immediate because it is served from the state store.

## Why a deterministic rule engine first

Safety systems need explainable actions. Deterministic rules establish a reviewable baseline and make it easier to justify operator interventions. ML should assist the system with anomaly detection and forecasting, not become the sole decision-maker for high-risk actions.

## Why the local app still supports in-memory mode

The in-memory fallback keeps onboarding and judging friction low. It also protects local development from requiring infrastructure before the core workflow can be evaluated. The tradeoff is that this mode is not horizontally scalable and should be treated as demo-only.