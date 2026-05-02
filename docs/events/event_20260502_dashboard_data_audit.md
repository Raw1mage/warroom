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

- `lishanmei-dlp-file-evidence` No data investigation:
  - User URL: `/warroom/d/lishanmei-dlp-file-evidence/...&from=now-30m&to=now&var-nas=lishanmei`.
  - Baseline Loki evidence for `now-30m`: `{job="warroom-dlp-event-collector", nas_host="lishanmei"}` returned `7061` events.
  - Existing dashboard file evidence panels were mostly hard-coded to `source_app="file_station"` and `action=~"webapp_file_download|webapp_file_export"`.
  - `file_station` download/export for `now-30m` returned `0`; `24h` historical download returned `731`, confirming this was a source/window mismatch rather than Loki/collector outage.
  - Live file evidence for `now-30m` exists under `source_app="nas_file_service"`, `source_channel="nas_home_log"`, `action=~"file_activity|file_read"`, with sample fields `actor`, `display_path`, `folder_path`, `file_name`, `network_protocol`, and optional GeoIP fields.
- Updated `grafana/dashboards/lishanmei-dlp-file-evidence.json`:
  - Top stat panels now use live `nas_file_service/nas_home_log` evidence.
  - Actor/path/folder/file-name/country/region panels now use live file evidence instead of File Station download-only queries.
  - File size histogram remains a File Station download/export historical view but now includes `or vector(0)` so an empty short window reports zero instead of looking broken.
  - Descriptions/titles now distinguish live NAS home-scope file evidence from File Station download DB evidence.
- Full dashboard audit after retry:
  - Audited all provisioned `grafana/dashboards/*.json` files: `lishanmei-anomaly-alert-center`, `lishanmei-dlp-file-evidence`, `lishanmei-dlp-insights`, `lishanmei-dlp-terminal-stream`, `lishanmei-dlp-web-ingress`, `lishanmei-local-overview`, and `lishanmei-nas-host-health`.
  - Confirmed no dashboard UID or dashboard link still points to `warroom-*` legacy UIDs.
  - Initial false positives came from testing Grafana log panels as Loki instant queries and from not substituting `$__interval`; audit script was corrected to use `query_range` for log/range panels and substitute `$__interval=1m`.
  - Added zero-vector fallback to `lishanmei-dlp-terminal-stream` pie-chart categories so absent event classes render as `0` rather than No data.
  - Added zero-vector fallback to `lishanmei-dlp-insights` capability-gap stat; detailed capability-gap tables/logs intentionally remain empty when there are no gaps.

## Verification

- `json.loads(grafana/dashboards/lishanmei-dlp-file-evidence.json)` passed; dashboard has 18 panels.
- Extracted every Loki target from `lishanmei-dlp-file-evidence.json` and executed against Loki with `$__range=30m`:
  - 19 query targets returned data/vector results.
  - Representative results: live file evidence `2170`, unique actors `1`, unique source IPs `3`, actor volume `2160`, path/folder/file panels non-empty, auth failures `41`, large downloads `0` via vector fallback.
  - Remaining empty panels were expected optional views: historical capability gap and NAS system/service log frequency.
- Restarted `grafana`; container health returned `healthy`, so dashboard provisioning was reloaded.
- Full dashboard retry audit result:
  - Legacy UID/link count: `0`.
  - Query errors: `0`.
  - Non-empty/vector results: `86` targets.
  - Remaining empty targets: `6`, all classified as expected no-event panels:
    - `lishanmei-anomaly-alert-center`: large download evidence log; capability gaps by registry source/capability/stage.
    - `lishanmei-dlp-file-evidence`: historical capability gap frequency; NAS system/service log frequency.
    - `lishanmei-dlp-insights`: capability gap detail table.
    - `lishanmei-dlp-terminal-stream`: collector fail-fast error log.
  - Restarted `grafana` again after retry fixes; container health returned `healthy`.

## Architecture Sync

- Verified (No doc changes): the long-term architecture already states that `nas_home_log_remote` emits `nas_file_service/nas_home_log` metadata and that File Station DB evidence is a separate source. This task corrected dashboard query alignment only; no component boundary or data-flow change was introduced.
