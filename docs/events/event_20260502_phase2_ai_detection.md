# Event 2026-05-02 — Phase 2 AI Detection

## 需求

After Phase 1 Grafana email alerting is approved for go-live, track Phase 2 AI detection.

## Scope IN

- Plan AI-assisted anomaly detection as a signal producer.
- Keep Grafana Alerting as alert lifecycle and notification authority.
- Define feature extraction, baseline scoring, anomaly event schema, and stop gates.

## Scope OUT

- No custom email/LINE notifier.
- No automatic response.
- No LLM as primary detector or severity authority.

## Decisions

- Phase 1 is live after user-confirmed email receipt.
- Phase 2 AI detection will emit `anomaly_alert` events to Loki; Grafana will evaluate and notify.
- Download alerting must include freshness/cursor guard because File Station evidence may be re-ingested with historical `observed_at`.
- User requested Phase 2 be brought online with Warroom directly calling Ollama when available.
- Live MVP keeps deterministic rules as the detector and uses Ollama only for triage enrichment.

## Validation

- Plan artifacts created under `plans/20260502_phase2_ai_detection/`.
- `idef0.json` and `grafcet.json` parse as valid JSON.
- `docker compose config` still validates after Phase 1/Phase 2 documentation and provisioning changes.
- Architecture sync completed in `specs/architecture.md`: Phase 1 email alerting is marked live, and Phase 2 AI detection is documented as a signal-producer path that hands alert lifecycle back to Grafana Alerting.
- Runtime service added and started: `warroom-ai-anomaly-scorer`.
- Service health check passed: `/healthz` returned `{"status":"ok"}`.
- Metrics exposed and scraped by Prometheus: `up{job="warroom-ai-anomaly-scorer"}=1` and `warroom_ai_anomaly_scorer_up=1`.
- Grafana alert provisioning reloaded successfully after adding scorer-health and `anomaly_alert` rules.
- Current `anomaly_alert` count in the validation window is 0, meaning no candidate crossed threshold during validation.
- Direct Ollama endpoint is configured as `http://host.docker.internal:11434/api/chat`, but `/api/version` currently returns connection refused from the scorer container. LLM triage will mark `llm_status="unavailable"` until the parent-system Ollama endpoint is reachable.

## Remaining

- Complete `observed_at` freshness/cursor guard for download rules.
- Add rolling baseline state under `/<server>/data/ai_state`.
- Make parent-system Ollama reachable from the scorer container and validate `llm_status="ok"`.
- Add dashboard panels for AI scorer metrics and `anomaly_alert` event details.
