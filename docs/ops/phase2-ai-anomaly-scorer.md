# Phase 2 AI Anomaly Scorer

`warroom-ai-anomaly-scorer` is the Phase 2 signal producer. It does not own alert lifecycle or notifications; Grafana Alerting remains the alert system.

## Runtime

- Compose service: `warroom-ai-anomaly-scorer`
- Container: `warroom-ai-anomaly-scorer`
- Runtime image: `python:3.9` from the local image cache
- App: `services/warroom-ai-anomaly-scorer/app.py`
- Metrics: `/metrics` on port `8020`
- Health: `/healthz`
- Prometheus job: `warroom-ai-anomaly-scorer`

## Data flow

```text
Loki evidence
  -> warroom-ai-anomaly-scorer feature queries
  -> deterministic rule candidates
  -> optional direct Ollama triage over HTTP
  -> Loki action="anomaly_alert"
  -> Grafana Alerting email rules
```

## Ollama

The scorer calls Ollama directly through:

```env
WARROOM_AI_OLLAMA_URL=http://host.docker.internal:11434/api/chat
WARROOM_AI_OLLAMA_MODEL=qwen2.5:14b-instruct
```

If Ollama is unavailable, the scorer still emits deterministic `anomaly_alert` events and marks the event with `llm_status="unavailable"`. LLM triage is never the primary detector.

## Current rule candidates

- `AUTH_FAILURE_SPIKE_V1`
- `COLLECTOR_ACTIVE_GAP_V1`
- `NETWORK_CONNECTION_SPIKE_V1`
- `DOWNLOAD_LARGE_FILE_INGESTED_V1`

## Guardrails

- No automatic blocking or destructive response.
- No raw usernames, IPs, or paths in Loki labels.
- Grafana owns grouping, deduplication, alert state, and email delivery.
- Download rule remains ingestion-based until `observed_at` freshness/cursor guard is complete.
