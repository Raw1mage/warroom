# Event 2026-05-02 — Lishanmei Anomaly Readiness Audit

## 需求

集中強化利善美智能 dashboard 與 data collection 能力，盤點目前 capability gaps、SSH 腳本補齊可行性、長連線 execution-plan 框架，以及異常偵測所需的資料類型是否足夠。

## 範圍 IN

- 盤點 `thesmart` 現有 sources。
- 查 Loki 中 active/historical capability gaps。
- 評估 SSH transient scripts 與 bounded long-running execution plan。
- 整理 anomaly detection 的資料需求與 gaps。

## 範圍 OUT

- 本輪不直接新增 remote NAS persistent agent。
- 本輪不直接改 dashboard JSON 或部署新 adapter。

## Evidence

- 最近 1h / 15m `capability_gap`: 0 active gaps。
- 最近 24h historical gaps:
  - `file_station_remote/adapter_returned_failure/returncode=1`: 15
  - `nas_home_log_remote/adapter_returned_failure/remote_home_log_adapter_failed`: 12
  - `nas_home_log_remote/adapter_returned_failure/returncode=1`: 2
  - `host_health_remote/unsupported_source/source mode is not supported by this collector`: 5
  - `nas_system_log_remote/unsupported_source/source mode is not supported by this collector`: 2
- 最近 1h event mix includes host health, File Station downloads, NAS home log file activity, NAS system log auth/system events.

## Output

- `docs/ops/thesmart-anomaly-readiness.md`

## Architecture Sync

No code architecture changed in this audit. Recommended future architecture update if bounded SSH execution-plan runner is implemented.
