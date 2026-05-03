# Event: Dashboard data coverage repair

## 需求

- 修正 Grafana dashboard 出現不合理 `No data` 的問題。
- 不得用 fixture、placeholder、預設值或推測值假裝 File Station、Drive、nginx ingress、GeoIP/source IP 已有活動資料。
- 能從 collector 實際狀態表達的覆蓋訊號，要明確呈現為 coverage/gap，而非活動量。

## 範圍(IN)

- `services/warroom-dlp-file-collector/app.py`
  - 每個 configured source 週期性輸出 `coverage_status`。
  - 每個關鍵 payload field 輸出 `field_coverage_status`。
  - 新增 `coverage_value`: `1=active`, `0=no_events`, `-1=gap`，供 Grafana 聚合。
- `grafana/dashboards/thesmart-dlp-web-ingress.json`
  - 活動面板改查實際 non-collector DLP evidence。
  - 覆蓋面板改查 `collector_coverage` 的 `coverage_value`。
- `specs/architecture.md`
  - 記錄 coverage metadata 與 dashboard 邊界。

## 範圍(OUT)

- 不新增 Synology Drive/File Station/nginx ingestion adapter。
- 不啟用 `synology-nginx-logs` Compose profile。
- 不新增任何 fallback 或合成活動資料。
- 不提交 secrets 或 NAS-side agent。

## 任務清單

- [x] 盤點 Loki/Prometheus 與 dashboard no-data 成因。
- [x] 補 collector source/field coverage event。
- [x] 調整 web-ingress dashboard 查詢與文案。
- [x] 驗證 Python syntax、dashboard JSON、collector dry-run。
- [x] 重啟本專案 collector/Grafana，使 bind-mounted 程式與 provisioned dashboard 生效。
- [x] 驗證 Loki coverage 與 evidence count 查詢。

## Debug checkpoints

### Baseline

- Docker Compose services healthy；Prometheus `warroom_dlp_file_collector_up=1`。
- Loki 近期有 `nas_file_service`、`nas_auth`、`nas_host_health`、`nas_network` 等 evidence。
- `file_station`、`synology_drive`、nginx ingress、GeoIP/source IP 類 panel 的 no-data 主要是資料源/欄位未覆蓋，不是整體收集失敗。

### Instrumentation Plan

- Collector boundary: 每個 configured source 產生 source-level coverage event。
- Field boundary: 對 `actor/source_ip/source_country/source_region/file_name/folder_path/display_path/size_bytes/network_protocol` 產生 field coverage event。
- Dashboard boundary: 活動查詢只計 actual evidence；覆蓋狀態查 `collector_coverage`。

### Execution

- `app.py` 已輸出：
  - `action="coverage_status"`, `source_channel="collector_coverage"`, `coverage_status`, `coverage_value`, `event_count`, `gap_count`。
  - `action="field_coverage_status"`, `coverage_value`, `present_count`, `event_count`。
- Dashboard source coverage panel 查詢 `unwrap coverage_value`。

### Root Cause

- Dashboard 把尚未穩定覆蓋的資料源/欄位當成主活動資料查詢，造成 No data 被誤解為 collector 沒收資料。
- 真實狀態應拆成兩個訊號：
  - observed evidence activity。
  - collector source/field coverage metadata。

### Validation

- `python3 -m py_compile services/warroom-dlp-file-collector/app.py`：pass。
- `jq empty grafana/dashboards/thesmart-dlp-web-ingress.json grafana/dashboards/thesmart-dlp-insights.json grafana/dashboards/thesmart-dlp-file-evidence.json`：pass。
- `python3 services/warroom-dlp-file-collector/app.py --once --dry-run`：pass，輸出 `coverage_value` 與 field coverage events。
- `docker compose restart warroom-dlp-file-collector grafana`：pass；兩服務 healthy。
- Loki coverage query：回傳 `covered_source_app` + `coverage_status` + numeric values。
- Loki evidence count query：回傳最近 15m non-collector evidence count `3907`。
- Architecture Sync: Updated `specs/architecture.md` with coverage metadata and dashboard boundary.

## Follow-up: 最近被存取檔案表格

- 新增 `grafana/dashboards/thesmart-recent-file-access-table.json`，提供獨立 dashboard：`利善美智能 / 最近被存取檔案表格`。
- 在 `grafana/dashboards/thesmart-dlp-file-evidence.json` 同步新增 `最近被存取的檔案` table panel。
- 欄位：時間、檔名、使用者、途徑（app名）、IP。
- 查詢只使用 `source_app!="collector"` 且 action 屬於檔案存取/變更類 evidence，並從 Loki JSON payload 抽出欄位；缺 IP 或 actor 時不補猜。
- Validation:
  - `jq empty grafana/dashboards/thesmart-dlp-file-evidence.json grafana/dashboards/thesmart-recent-file-access-table.json`：pass。
  - Loki `query_range` sample 回傳 `file_name`、`actor`、`source_app` 欄位；sample 目前沒有 `source_ip`，表格將保留 IP 空值。
  - `docker compose restart grafana`：pass；Grafana healthy。
  - Architecture Sync: Updated `specs/architecture.md` with the recent file access table dashboard boundary.

## Follow-up: rename target label to thesmart

- Requirement: replace all `lishanmei` spellings with `thesmart` across repo content and filenames.
- Scope:
  - Renamed Grafana dashboard JSON files and dashboard `uid`/links/queries from `lishanmei-*` to `thesmart-*`.
  - Renamed server root from `lishanmei/` to `thesmart/` and changed target id to `thesmart`.
  - Changed `docker-compose.yml` defaults and healthcheck paths to `thesmart` dashboard/target values.
  - Updated docs, event logs, active plan artifacts, alert rules, scripts, service defaults, and architecture references.
- Validation:
  - `git grep -n lishanmei || true`: no tracked matches.
  - `jq empty grafana/dashboards/*.json config/nas-targets.json thesmart/config/target.json thesmart/config/sources.json`: pass.
  - `docker compose config`: pass.
  - `python3 -m py_compile services/warroom-dlp-file-collector/app.py services/warroom-ai-anomaly-scorer/app.py`: pass.
  - `docker compose up -d --force-recreate grafana warroom-dlp-file-collector warroom-ai-anomaly-scorer`: pass; services healthy.
  - Loki query for `nas_host="thesmart"` returned recent events (`1252` in 15m sample window after recreate).
- Note: old Loki history remains under old labels because Loki labels are immutable historical data; new collector/scorer output uses `nas_host="thesmart"`.

## Follow-up: terminal stream readability fix

- Requirement: the `thesmart-dlp-terminal-stream` dashboard was not human-readable because it exposed raw/terminal-style logs without a clear management question.
- Decision: keep the legacy dashboard uid for links, but change the dashboard purpose to `DLP 事件摘要`.
- Changes:
  - Replaced raw log stream panels with tables: `最近重要事件表`, `資料來源與欄位覆蓋狀態`, and `需要處理的收集問題`.
  - Broadened the 5-minute trend panel to all non-collector sources instead of only file/drive labels.
  - Kept the evidence-category pie chart as the top-level answer to "what kind of evidence is happening?".
- Validation:
  - `jq empty grafana/dashboards/thesmart-dlp-terminal-stream.json`: pass.
  - Loki query for important events returned auth, network, and file/service evidence.
  - Loki query for coverage table returned source/field coverage rows.
  - Loki query for actionable collection problems executed successfully and returned no rows, which is acceptable as a healthy state.
  - Trend query returned grouped values for `nas_auth`, `nas_file_service`, `nas_host_health`, and `nas_network`.
  - `docker compose restart grafana`: pass; Grafana healthy.
  - Architecture Sync: Updated `specs/architecture.md` with the management-facing terminal-stream contract.

## Remaining

- 若要讓 File Station/Drive/nginx 相關活動面板真的有資料，需另開 ingestion/adapter 工作；本次僅修正 coverage 呈現與 no-data 語意。
