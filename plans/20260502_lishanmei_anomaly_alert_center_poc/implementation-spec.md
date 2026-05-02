# TheSmartAI Anomaly Alert Center POC

## Goal

用現有 Loki evidence 與 collector source registry，建立第一批可視化異常警訊中心，讓管理者能從 Grafana 直接看到登入異常、資料下載異常、連線異常與收集能力缺口。

## Scope IN

- 新增 `lishanmei-anomaly-alert-center` dashboard。
- 使用既有 Loki events，不新增 NAS-side agent/container/exporter。
- 視覺化常見 POC 情境：auth failures、large downloads、TCP connection spikes、capability gaps。
- 從既有 TheSmartAI（技術 label：`lishanmei`）檔案證據 dashboard 增加導覽連結。

## Scope OUT

- 不做自動封鎖、停帳、刪檔或通知發送。
- 不建立完整 alert lifecycle / acknowledge / owner workflow。
- 不將 Grafana 改為直接讀 `/<server>/data`。

## POC Scenarios

1. 暴力破解 / 密碼猜測：`auth_failure` 在短時間內增加。
2. 使用者登入異常：依 actor 統計登入失敗。
3. 大檔下載：`webapp_file_download` 且 `size_bytes >= 100MB`。
4. 大量下載來源：依 actor 統計下載容量。
5. 連線數突增：`network_socket` 的 `tcp_established_count`。
6. 觀測能力缺口：registry gap `collector_capability_gap` active/historical。

## Validation Plan

- Dashboard JSON parse。
- Loki LogQL smoke tests for every POC panel family。
- `docker compose config`。
