# Event 2026-05-02 — AI Anomaly Alerting Research

## 需求

研究 Warroom 如何擴充 AI 模組建立異常預警：一般 AI 異常偵測模型、需要的資料數據、如何與 Loki 串接，以及如何接 email / LINE Bot 警報機制。

## Scope IN

- AI/ML anomaly detection model families.
- Warroom Loki evidence feature mapping.
- Loki -> AI scoring module -> alert event -> email/LINE delivery architecture.

## Scope OUT

- No production model implementation in this research pass.
- No NAS-side agent.
- No committed secrets.

## Validation

- Research report created: `docs/ops/ai-anomaly-alerting-research.md`.
- Architecture alignment checked against `specs/architecture.md`.
- Data readiness gate checked against live TheSmartAI (`nas_host="thesmart"`) Loki/Prometheus evidence:
  - Grafana/Loki/Prometheus/collector services healthy; collector metrics showed `up=1`, no collection failures, and no capability gaps.
  - Host health fields are present and LogQL-aggregatable: `cpu_busy_percent`, `memory_used_percent`, `disk_max_use_percent`, `disk_volume1_use_percent`, `network_total_rx_bytes`, `network_total_tx_bytes`, and network byte rates.
  - Auth/network events are present for Phase 1 scoring: `source_channel="auth_log"` and `source_channel="network_socket"`.
  - Registry capability gaps are currently absent in the active window.
  - Download evidence exists for File Station, including `size_bytes`, `actor`, and `source_ip`, but latest evidence observed in the 24h Loki ingestion window carried historical `observed_at` timestamps. Phase 1 may use this for rule replay and dashboard proof, but real-time download alerting needs a cursor/freshness guard before production alerting.

## Architecture Sync

- Research-only pass; no runtime service changes. Updated `specs/architecture.md` Open Architecture Items to point to the proposed AI anomaly scorer roadmap and explicitly keep LLMs as triage assistants rather than primary detectors or response authority.
