# Event 2026-05-02 — Lishanmei Anomaly Improvements

## 需求

將 `docs/ops/lishanmei-anomaly-readiness.md` 的改進建議正式寫成 plan 並執行，集中強化利善美智能 dashboard 與資料收集能力，讓後續可做超大流量、異常登入、登入錯誤、異常時間下載等偵測。

## Scope IN

- Active/historical capability gap dashboard semantics.
- Auth log adapter.
- Network socket adapter.
- Collector/source config integration.
- Collector source registry abstraction for future multi-source expansion.
- Anomaly readiness dashboard panels.
- Bounded SSH execution-plan runner design.

## Scope OUT

- No NAS persistent agent/container/exporter.
- No destructive response automation.
- No Grafana direct file reads from `/<server>/data`.

## Baseline Evidence

- Prior audit: `docs/ops/lishanmei-anomaly-readiness.md`.
- Active capability gaps in 15m/1h were zero at audit time.
- Existing data is enough for total traffic and File Station download signals, but insufficient for structured auth outcomes and connection anomaly detection.

## Tasks

See `plans/20260502_lishanmei_anomaly_improvements/tasks.md`.

## Validation

- `python3 -m py_compile tools/auth_log_adapter.py tools/network_socket_adapter.py services/warroom-dlp-file-collector/app.py`: pass.
- `python3 -m json.tool lishanmei/config/sources.json`: pass.
- `python3 -m json.tool grafana/dashboards/lishanmei-dlp-file-evidence.json`: pass.
- `docker compose config`: pass.
- Local `auth_log_adapter.py` smoke test normalized `auth_failure` and `auth_success` with actor/source_ip/outcome fields.
- Local `network_socket_adapter.py` smoke test emitted `network_socket_snapshot` with connection/listen/top remote IP summaries.
- Collector source registry separates internal `source_key` (`auth_log_remote`, `network_socket_remote`) from evidence labels (`source_app="nas_auth"` / `source_channel="auth_log"`, `source_app="nas_network"` / `source_channel="network_socket"`).
- Collector restarted; Loki confirmed `source_channel="auth_log"` events (`auth_failure`, `session_opened`, `session_closed`) and `source_channel="network_socket"` `network_socket_snapshot` events for `nas_host="lishanmei"`.
- Active capability gap dashboard uses a 2m registry gap window (`source_channel="collector_capability_gap"`) to avoid restart-transition pollution.
- Dashboard LogQL smoke tests cover active gaps, auth failures, TCP established, and large downloads panels.
- Retry validation after registry rebuild:
  - `sum(count_over_time({nas_host="lishanmei", source_channel="auth_log"} | json | source_key="auth_log_remote" [5m]))`: 800.
  - `sum(count_over_time({nas_host="lishanmei", source_channel="network_socket"} | json | source_key="network_socket_remote" [5m]))`: 8.
  - `sum(count_over_time({job="warroom-dlp-event-collector", nas_host="lishanmei", action="capability_gap", source_channel="collector_capability_gap"}[2m])) or vector(0)`: 0.

## Deferred / Partial

- Latest remediation-oriented gap table remains deferred until the gap taxonomy has stable operator remediation mappings.
- Off-hours download panel remains deferred; current Phase 1 covers active gaps, auth failures, TCP established, and large downloads.

## Architecture Sync

Updated `specs/architecture.md` with source registry semantics, `auth_log_remote`, `network_socket_remote`, and bounded SSH execution-plan runner boundaries. Added `docs/ops/bounded-ssh-execution-plan-runner.md`.
