# Event 2026-05-02 — Dashboard 資料查詢逐一稽核

## 需求

使用者要求逐一檢查每個 dashboard 撈資料是否正常，並補上 gap。

## 範圍

IN:
- 檢查 `grafana/dashboards/*.json` 內所有 Loki / Prometheus target queries。
- 分類 query 狀態：OK、有資料、合法但目前無資料、語法/資料源錯誤、panel 設計 gap。
- 修正可由 dashboard query/panel 設定補上的 gap。

OUT:
- 不重啟服務。
- 不修改 NAS credentials。
- 不新增 NAS-side agent/exporter/container。

## Debug Checkpoints

### Baseline

- 已確認 collector / Loki / Prometheus 服務活著，但 Grafana panel 可能因 query/panel 設定顯示 `No data`。

### Instrumentation Plan

- Boundary 1: dashboard JSON parse。
- Boundary 2: 對 Loki `/loki/api/v1/query` 與 Prometheus `/api/v1/query` 執行每個 target expression。
- Boundary 3: 針對錯誤 query 修正語法；針對合法無資料 panel 判斷是否需要 `or vector(0)` 或更合理分類。

### Execution

- Pending.

## Verification

- Pending.

## Architecture Sync

- Pending.
