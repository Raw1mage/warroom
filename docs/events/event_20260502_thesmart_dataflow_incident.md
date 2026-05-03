# Event 2026-05-02 — 利善美資料流中斷排查

## 需求

使用者回報 Grafana 畫面疑似沒有資料，要求自行排查目前資料流是否中斷。

## 範圍

IN:
- 檢查 Docker Compose 服務狀態。
- 檢查 `warroom-dlp-file-collector` metrics/logs。
- 直接查 Loki 是否收到 `thesmart` 與 `host_health` events。
- 判斷是資料流中斷、collector push 失敗、Loki 查詢空值，或 dashboard query 分類失效。

OUT:
- 不重啟服務，除非後續明確需要並獲得確認。
- 不修改 NAS credentials 或部署 NAS-side agent/exporter。

## Debug Checkpoints

### Baseline

- 使用者畫面顯示資料可能為空或不足，懷疑 dataflow 斷線。

### Instrumentation Plan

- Boundary 1: Docker Compose service health。
- Boundary 2: collector `/metrics` counters：up、cycles、events pushed、failures、last success。
- Boundary 3: Loki labels/query：`nas_host="thesmart"`、`source_channel="host_health"`。
- Boundary 4: Grafana dashboard query 是否因 pie insight 分類 matcher 太嚴格而空值。

### Execution

- Docker Compose service check: `warroom-dlp-file-collector`、Grafana、Loki、Prometheus 均為 Up。
- Collector Prometheus metrics:
  - `warroom_dlp_file_collector_up = 1`
  - `warroom_dlp_file_collector_cycles_total = 119`
  - `warroom_dlp_file_collector_events_pushed_total = 12220`
  - `warroom_dlp_file_collector_collection_failures_total = 0`
  - `warroom_dlp_file_collector_last_success_timestamp` 為檢查當下最新時間。
- Loki direct query:
  - 最近 10 分鐘 `nas_host="thesmart"` 事件數：816。
  - 最近 10 分鐘 `source_channel="host_health"` 事件數：17。
  - 最近 sample 能取回 `source_channel="nas_home_log"` / `action="file_activity"` 事件。
- Root cause: dataflow 未中斷；空白/低辨識度畫面來自 pie chart query 寫法。`label_format category="..."` 在 Loki API 可回傳，但 Grafana pie panel 仍顯示 `No data`，因此不能作為此 panel 的穩定呈現方式。
- Fix: `grafana/dashboards/thesmart-dlp-terminal-stream.json` 的 pie chart targets 改回 Grafana pie 最穩的 scalar instant query，每個分類用獨立 target + `legendFormat` 命名。
- Follow-up: 使用者回報不明黑色圖後，移除 pie chart 內的 `or vector(0)`，因為 0 值向量適合 stat 防 `No data`，但在 pie chart 會製造無意義的黑色/0 值 slice。

## Verification

- Dashboard JSON parse: pass。
- Dashboard panel check: pass；panel `id=10` 的所有 targets 都是 scalar instant query，不再使用 `label_format category=`，也不再使用 `or vector(0)` 製造 0 值 slice。
- Loki scalar query validation:
  - 最近 5 分鐘 `NAS 檔案服務活動` query 回傳 376。
  - 最近 5 分鐘 `主機健康/資源監測` query 回傳 8。

## Architecture Sync

- Verified (No doc changes). 本次為 dashboard query 修正與 dataflow incident 排查，未改變架構邊界或資料流模型。
