# Dashboard Group Cleanup

## 需求

- 重新分類利善美智能 dashboard groups。
- 去除重複、無效或過度分散的群組。
- 主線聚焦 `{主機、服務}` 的 `{效能、健康、異常}`。
- AI 判斷異常獨立成一個目錄。
- 企業 Data 洩露監控獨立成一個目錄。

## 範圍

### IN

- 將 `grafana/dashboards/*.json` 改為分類子目錄管理。
- 移除 dashboard 根層 `title` 的 `[NN 分類]` 前綴。
- 保留 dashboard `uid`、panel、query、datasource 與跨 dashboard links。
- 維持總覽、資料品質、安全稽核作為輔助分類。

### OUT

- 不修改 Prometheus/Loki query。
- 不刪除 dashboard JSON 檔案。

## 任務清單

- [x] 盤點目前 dashboard titles 與 provisioning provider。
- [x] 將主機 dashboard 收斂到 `[10 主機監控]`。
- [x] 將服務 dashboard 收斂到 `[20 服務監控]`。
- [x] 將 AI 異常 dashboard 收斂到 `[30 AI 異常判斷]`。
- [x] 將 DLP / Insider Risk dashboard 收斂到 `[40 企業資料洩露監控]`。
- [x] 將資料品質與安全稽核 dashboard 改為 `[90]`、`[99]` 輔助分類。
- [x] 驗證 JSON 格式有效。

## Key Decisions

- 不再將主機效能、健康、異常拆成多個 dashboard group；統一使用 `[10 主機監控] 利善美智能 - 主機效能／健康／異常`。
- 不再將服務效能、健康、異常拆成多個 dashboard group；統一使用 `[20 服務監控] 利善美智能 - 服務效能／健康／異常`。
- AI 判斷異常不混入一般警示或 DLP，獨立為 `[30 AI 異常判斷]`。
- DLP、Web/File Evidence、事件摘要、行為統計與 Insider Baseline 統一收斂為 `[40 企業資料洩露監控]`。
- Follow-up: dashboard `title` 必須是 `[分類] 品牌 - 具體功能名稱`，不能只使用分類總稱；否則 Grafana 列表會出現多個同名 dashboard。
- Final: 分類改為 Grafana file-structure folders；dashboard `title` 移除 `[NN 分類]` 前綴，避免 sidebar 同時出現多個 `[40]`。

## Debug Checkpoints

- Checkpoint: Dashboard provisioning uses `foldersFromFilesStructure: true`; visible grouping is driven by category subdirectories under `/var/lib/grafana/dashboards`.
- Evidence: `grafana/provisioning/dashboards/dashboards.yml` provider `warroom-local` points to `/var/lib/grafana/dashboards` and imports subdirectories as folders.
- Decision: Move dashboard JSON files into category folders and remove category prefixes from root `title` fields while preserving UIDs and links.

## Verification

- JSON Validity: `jq empty` completed successfully for nested `grafana/dashboards/**/*.json`.
- Dashboard Group Scan: 13 local dashboard files now live under target folders `[00]`, `[10]`, `[20]`, `[30]`, `[40]`, `[90]`, `[99]`.
- Duplicate Title Fix: `[20 服務監控]` 與 `[40 企業資料洩露監控]` 內的 dashboards 使用共同 folder，但 root `title` 保留各自具體功能名稱。
- Folder Provisioning: `warroom-local` now uses `foldersFromFilesStructure: true`; dashboard JSON files live under category folders such as `[20 服務監控]` and `[40 企業資料洩露監控]`.
- Scope Control: Only dashboard folder placement, root `title` fields, provisioning folder behavior, and dependent Grafana default/healthcheck paths were changed for this classification cleanup; existing unrelated working tree changes were not modified.
- Architecture Sync: Verified (No doc changes). This task changes Grafana dashboard taxonomy only and does not alter collectors, data flow, provisioning topology, Prometheus/Loki queries, or runtime boundaries.
