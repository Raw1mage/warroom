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

## Data Flow

```text
Loki evidence
  -> warroom-ai-anomaly-scorer feature queries
  -> deterministic rule candidates
  -> bounded evidence compression and salted entity hashing
  -> optional rawbase OpenAI-compatible LLM triage
  -> Loki action="anomaly_alert"
  -> Prometheus scorer/rawbase metrics
  -> Grafana Alerting email rules
```

## rawbase LLM

The scorer calls rawbase through an OpenAI-compatible chat completions endpoint:

```env
WARROOM_AI_LLM_ENABLED=true
WARROOM_AI_LLM_PROVIDER=openai_compatible
WARROOM_AI_LLM_PROVIDER_ID=rawbase
WARROOM_AI_LLM_BASE_URL=http://host.docker.internal:7731/v1
WARROOM_AI_LLM_CHAT_COMPLETIONS_PATH=/chat/completions
WARROOM_AI_LLM_MODEL=Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf
WARROOM_AI_LLM_MODEL_SPEC=rawbase/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf
WARROOM_AI_LLM_API_KEY=local
WARROOM_AI_LLM_CONNECT_TIMEOUT_SECONDS=5
WARROOM_AI_LLM_READ_TIMEOUT_SECONDS=45
WARROOM_AI_LLM_TEMPERATURE=0.1
WARROOM_AI_LLM_MAX_EVIDENCE_EVENTS=20
WARROOM_AI_LLM_RESPONSE_FORMAT=json_object
WARROOM_AI_ENTITY_HASH_SALT=<deployment-secret-salt>
```

Linux compose deployments must keep `extra_hosts: ["host.docker.internal:host-gateway"]` unless an explicit rawbase LAN endpoint is approved. The scorer never falls back to another provider or model.

## Failure Status

- `ok`: rawbase returned valid JSON matching the expected triage shape.
- `disabled`: `WARROOM_AI_LLM_ENABLED=false`; deterministic alerts continue.
- `unavailable`: rawbase HTTP service is unavailable or reports transient server failure.
- `timeout`: connect/read exceeded configured timeouts.
- `transport_error`: non-timeout HTTP/network failure.
- `invalid_json`: rawbase or message content was not parseable JSON.
- `schema_error`: rawbase JSON missed required triage fields or had invalid types.

## Current Rule Candidates

- `AUTH_FAILURE_SPIKE_V1`
- `AUTH_SUCCESS_AFTER_FAILURE_V1`
- `COLLECTOR_ACTIVE_GAP_V1`
- `NETWORK_CONNECTION_SPIKE_V1`
- `DOWNLOAD_LARGE_FILE_INGESTED_V1`

## Metrics

- `warroom_ai_anomaly_candidates_total{nas_host,rule_id,severity}`
- `warroom_ai_anomaly_alerts_total{nas_host,rule_id,severity,llm_status}`
- `warroom_ai_llm_requests_total{provider_id,model,status}`
- `warroom_ai_llm_request_duration_seconds_bucket{provider_id,model,le}`
- `warroom_ai_llm_json_parse_failures_total{provider_id,model}`
- `warroom_ai_llm_unavailable{provider_id,model}`
- `warroom_ai_llm_last_success_timestamp_seconds{provider_id,model}`

## Privacy Contract

- LLM prompts contain bounded aggregate evidence only: rule ID, severity, deterministic score, summary, coarse counts/windows, guard status, and salted hashes.
- Raw usernames, IP addresses, full paths, filenames, tokens, cookies, session IDs, and file content are not sent to rawbase.
- Loki/Grafana/Prometheus labels remain bounded to non-sensitive fields such as NAS host, rule ID, severity, and LLM status.

## Guardrails

- No automatic blocking or destructive response.
- No provider/model fallback.
- Grafana owns grouping, deduplication, alert state, and email delivery.
- Download rules include freshness/cursor guard metadata and are deduplicated by rule/entity/min-repeat window.

## Validation

- Static config: `docker compose -f docker-compose.yml config`
- Python syntax: `python3 -m py_compile services/warroom-ai-anomaly-scorer/app.py`
- Runtime smoke: run one dry cycle with `WARROOM_AI_LLM_ENABLED=false python3 services/warroom-ai-anomaly-scorer/app.py --once --dry-run` when Loki is reachable.
- Rawbase smoke: from scorer network namespace, POST a minimal JSON-only prompt to `http://host.docker.internal:7731/v1/chat/completions`.
