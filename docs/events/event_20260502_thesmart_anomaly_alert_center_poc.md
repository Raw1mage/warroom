# Event 2026-05-02 — TheSmartAI Anomaly Alert Center POC

## 需求

使用者詢問是否能從 dashboard 視覺化看到各種型式的異常警訊，並要求基於現有框架設計第一批 POC。

## Scope IN

- 新增 Grafana dashboard：`thesmart-anomaly-alert-center`。
- 顯示名稱使用 `TheSmartAI`；既有技術 label / UID 中的 `thesmart` 維持不變，避免破壞 Loki 查詢與 dashboard links。
- 使用現有 Loki evidence / collector source registry。
- 視覺化登入異常、下載異常、網路連線異常、capability gap。

## Scope OUT

- 不新增 NAS persistent agent。
- 不新增 destructive response automation。
- 不做完整 incident lifecycle。

## Tasks

See `plans/20260502_thesmart_anomaly_alert_center_poc/tasks.md`.

## Validation

- `python3 -m json.tool grafana/dashboards/thesmart-anomaly-alert-center.json`: pass.
- `python3 -m json.tool grafana/dashboards/thesmart-dlp-file-evidence.json`: pass.
- `python3 -m json.tool thesmart/config/target.json`: pass.
- `docker compose config`: pass.
- Loki smoke queries passed for:
  - active registry capability gaps (`collector_capability_gap`, 2m)
  - auth failures (`auth_log`, 5m)
  - top failed login source IPs (`auth_log`, 1h)
  - TCP established max (`network_socket`, 15m)
  - large downloads (`webapp_file_download`, 1h)

## Architecture Sync

- Updated `specs/architecture.md` to mention the TheSmartAI Anomaly Alert Center POC while preserving `nas_host="thesmart"` as the stable technical selector.
