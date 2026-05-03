# Event 2026-05-04 — TheSmartAI Anomaly Alert Center Summary

## 需求

- 將 `thesmart-anomaly-alert-center` 從難讀的 raw/terminal-style 視圖改成管理者可行動的異常警訊摘要。
- Dashboard 應回答：目前有沒有異常、是哪一類、嚴重度/來源、需要處理什麼。

## 範圍

IN:
- 重設 `grafana/dashboards/thesmart-anomaly-alert-center.json` panel 語意。
- 移除 raw logs panel 型態，改用 stat / piechart / timeseries / barchart / table。
- 將 TCP socket readiness 查詢聚合成單一可讀序列。
- 同步 `specs/architecture.md`。

OUT:
- 不變更 collector/scorer 偵測規則。
- 不新增通知通道或自動處置。
- 不推測缺失 IP、使用者或檔案欄位。

## Debug Checkpoints

### Baseline

- 使用者指出畫面仍難讀；實際目標 dashboard 是 `thesmart-anomaly-alert-center`。
- 問題不是 Loki 無資料，而是 panel 語意與呈現方式仍接近 raw stream，不適合管理者判讀。

### Instrumentation Plan

- 檢查 dashboard JSON panel type，確認是否仍有 `logs` panel。
- 對核心 LogQL 直接查 Loki API，確認查詢可執行。
- 重啟本專案 Grafana 以載入 provisioned dashboard。

### Execution

- Dashboard 改成告警摘要結構：AI 告警數、登入失敗、TCP readiness、收集能力缺口、異常訊號組成、趨勢、AI 告警清單、登入失敗 actor/IP 排行、大檔下載候選與 capability gap 表格。
- TCP 趨勢查詢由多序列 `max_over_time(... unwrap tcp_established_count ...)` 改為 `max(max_over_time(...))`，避免每筆 snapshot 形成多條線。

### Root Cause

- Dashboard 原先呈現方式把事件流當成使用者介面，沒有整理成可行動的管理問題。
- TCP socket snapshot 是多筆 payload event；若不聚合 unwrapped value，Grafana 會顯示多條 series 或 stat 多值，降低 readability。

### Validation

- `jq empty grafana/dashboards/thesmart-anomaly-alert-center.json` pass。
- Panel type 檢查結果：`stat`, `piechart`, `timeseries`, `table`, `barchart`；無 `logs` panel。
- Loki API 驗證 anomaly count 與 TCP readiness 查詢皆回傳 `status=success`。
- `docker compose up -d grafana` 後 `warroom-grafana` healthy。
- Architecture Sync: Updated `specs/architecture.md` Grafana dashboard section to document `thesmart-anomaly-alert-center` as an actionable alert summary.

## Remaining

- 無本次 dashboard 重設剩餘項目。
- 未提交 commit；等待使用者明確要求。
