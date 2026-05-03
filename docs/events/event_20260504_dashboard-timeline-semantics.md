# Event 2026-05-04 — Dashboard Timeline Semantics

## 需求

- 使用者指出 `thesmart-dlp-insights` 中凡與時間軸有關的資訊都應以 timeline 表達。
- 使用者也指出 table 內大量相同 entry 重複顯示沒有管理意義。
- No data/空白 panel 需要能區分「目前無事件」與「欄位/資料源尚未覆蓋」。

## 範圍

IN:
- `grafana/dashboards/thesmart-dlp-insights.json`
- `grafana/dashboards/thesmart-recent-file-access-table.json`
- `grafana/dashboards/thesmart-dlp-file-evidence.json`
- `grafana/dashboards/thesmart-anomaly-alert-center.json`
- `specs/architecture.md`

OUT:
- 不新增 placeholder 或 synthetic data。
- 不更動 collector/scorer 偵測規則。
- 不推測缺失欄位。

## Debug Checkpoints

### Baseline

- `demo.mp4` 來自真實 File Station transfer DB evidence，但同一下載活動會產生多筆 DB rows，raw table 逐筆列出會造成管理者看到大量重複 entry。
- `thesmart-dlp-insights` 中時間趨勢 panel 雖是 timeseries，但以 bars 表達，不符合「時間相關資訊用 timeline」的 UX 語意。
- 部分空白 panel 是查詢範圍內沒有事件，部分是欄位 coverage 不存在；需要明確文案。

### Execution

- 將 `thesmart-dlp-insights` 的 `活動時間分布 / action 趨勢` 改為 `事件 Timeline / action 趨勢`，timeseries draw style 改為 line。
- 保留 actor/IP/protocol/file/folder/GeoIP/source/capability gap 等非時間軸視圖為 table/ranking，但補充說明其為 selected range aggregate。
- 將最近檔案表格改為依 `file_name + actor + source_app + source_ip` 去重彙總，顯示 `證據筆數`。
- 排除 `file_activity` 進入最近檔案彙總，避免 NAS service log 將帳號/目錄片段誤顯示成檔名。
- 將大檔下載候選改為去重彙總表。
- AI 告警與 capability gap 空表文案改為「目前無事件時空白」，避免被誤解為未完成。

### Validation

- `jq empty` 驗證四個 dashboard JSON 通過。
- Loki timeline query `sum by (action) (count_over_time(...[5m]))` 回傳 `status=success`。
- Loki 去重最近檔案 query 回傳 `status=success`，`demo.mp4` 聚合為單一 row 並顯示 evidence count。
- `docker compose up -d grafana` 後 `warroom-grafana` healthy。
- Architecture Sync: Updated `specs/architecture.md` to document timeline semantics and deduplicated recent-file rows.

## Remaining

- 若需要更高階 UX，可再加一個 true event timeline/table panel 顯示最近 N 筆重要事件，但不應取代目前的 aggregated rankings。
