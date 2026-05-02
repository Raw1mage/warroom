# Event 2026-05-01 — DLP File Evidence Collection

## 需求

讓 Grafana dashboard `DLP 檔案證據總覽` 不再只依賴手動 CLI dry-run；需要有可由 Docker Compose 啟動的常駐/定時 collector，持續把 Drive / File Station 檔案證據推送到 Loki，並讓 Prometheus 觀察 collector 健康度。

## 範圍(IN)

- 新增 DLP file evidence collector 服務。
- 接線 Docker Compose 與 Prometheus scrape target。
- 保留 metadata-first、防止讀取檔案內容。
- 使用 rawdb 真實 NAS metadata sources 或 capability gaps 作為 dashboard evidence；runtime 不再使用 fixture/placeholder source。
- 記錄 capability gap，而不是在 NAS 設定不足時猜測或 fallback。

## 範圍(OUT)

- 不加入真實 NAS 憑證或私人主機資訊。
- 不讀取檔案內容。
- 不自動推測 Drive DB / File Station DB 路徑。
- 不修改 Grafana dashboard 查詢語意，除非證據顯示查詢錯誤。

## 任務清單

- [x] 建立 scoped plan artifacts。
- [x] 盤點 dashboard 查詢與現有 collector tooling。
- [x] 實作常駐/定時 collector service。
- [x] 接線 Compose / Prometheus / env example。
- [x] 驗證 Loki 與 Prometheus evidence path。
- [x] 同步 `specs/architecture.md`。

## Debug Checkpoints

### Baseline

- Dashboard `DLP 檔案證據總覽` 查詢 `job="warroom-dlp-event-collector"` 與 `source_app=~"synology_drive|file_station"`。
- 既有 repo 只有 CLI tooling 與 fixtures，沒有 Compose-managed long-running collector。
- 因此 dashboard 是否有資料取決於是否有人手動推送事件。

### Instrumentation Plan

- Service boundary: collector `/healthz` 與 `/metrics`。
- Loki boundary: label `job="warroom-dlp-event-collector"`、`source_app`、`action`、`source_channel`。
- Prometheus boundary: scrape target `warroom-dlp-file-collector:8010` 與 metric `warroom_dlp_file_collector_events_pushed_total`。
- Config boundary: `.env.example` 僅提供非秘密、明確 opt-in 的 source 設定。

### Execution

- Added `services/warroom-dlp-file-collector/app.py` and `services/warroom-dlp-file-collector/Dockerfile`.
- Added `warroom-dlp-file-collector` to `docker-compose.yml`, with read-only `./tools`, `./config`, and optional `./geoip` mounts.
- Added Prometheus scrape job for `warroom-dlp-file-collector:8010`.
- Added `.env.example` knobs for interval, explicit source selection, NAS target config, GeoIP MMDB, and File Station remote connection values.

### Root Cause

Dashboard queries were already aligned with the normalized DLP event label contract. The missing piece was runtime ingestion: evidence producers were CLI-only, so no always-on Compose service continuously pushed dashboard-compatible Loki streams. The fix adds a small scheduler service that reuses existing collector tooling instead of duplicating parsing logic.

## Key Decisions

- Default source mode is rawdb `file_station_remote`; fixture and placeholder runtime sources are removed.
- Optional `file_station_remote` and `nas_home_log_remote` sources require explicit host/config values; incomplete or inaccessible configuration emits a capability gap event and does not silently fallback.
- Collector mounts existing `tools/` read-only and shells out to established adapters to avoid a second implementation of normalization logic.
- Metrics are bounded and service-focused; file/user/IP/path dimensions remain in Loki JSON payloads, not labels.

## Verification

- `python3 -m py_compile services/warroom-dlp-file-collector/app.py tools/dlp_event_collector.py tools/file_station_transfer_adapter.py tools/drive_event_enricher.py tools/drive_file_resolver.py` passed.
- `docker compose -f docker-compose.yml config` passed.
- `WARROOM_NAS_TARGETS_CONFIG=/home/pkcs12/projects/warroom/config/nas-targets.json WARROOM_DLP_TOOLS_DIR=/home/pkcs12/projects/warroom/tools python3 services/warroom-dlp-file-collector/app.py --once --dry-run` produced rawdb capability gaps for inaccessible `file_station_remote` and `nas_home_log_remote`, with no fixture fallback.
- `docker compose -f docker-compose.yml up -d --build warroom-dlp-file-collector` built and started the service.
- Loki labels include `job="warroom-dlp-event-collector"` and `source_app` values `synology_drive` / `file_station`.
- Loki `query_range` returns dashboard-compatible streams for Drive preview and File Station download evidence.
- Prometheus target `warroom-dlp-file-collector:8010` is `up` and exposes `warroom_dlp_file_collector_events_pushed_total`.
- Architecture Sync: Updated `specs/architecture.md` to include the long-running DLP file collector service, ingestion flow, and validation signals.

## Remaining

- For real NAS ingestion, fix rawdb SSH/sudo/log/DB permissions for the configured `file_station_remote` and `nas_home_log_remote` sources in `config/nas-targets.json`.

## Dashboard Presentation Update — 2026-05-01

- Updated `DLP 檔案證據總覽` logs panels `Drive DB / 開檔與預覽證據`, `File Station DB / 下載與匯出證據`, and `檔案層級證據流` to render collector JSON payloads through Loki `| json | line_format`.
- Chosen output is human-readable one-event-per-line text focused on who/when/what/how/where: ISO time, source IP, username, app, action, file path/name, file size, protocol, and NAS host. Collector/ingest timestamps and raw log reconstruction are intentionally excluded.
- Follow-up: disabled labels and log details for the three human-readable evidence panels so parsed fields such as `collected_at` / `ingested_at` do not appear in the dashboard view.
- Follow-up: changed file size rendering from raw bytes to adaptive `###.### KB`, `###.### MB`, or `###.### GB` via Loki template math.
- Follow-up: changed the last dashboard column from `where=<nas>` to country/region text or `-`; source IP remains the second column.
- Added optional local-MMDB GeoIP enrichment in `warroom-dlp-file-collector`: `WARROOM_GEOIP_MMDB_PATH` reads a mounted MaxMind-compatible database and writes payload fields `source_country` / `source_region`; missing/unreadable DB configuration emits `capability_gap` and does not call external APIs.
- Added `network_protocol` enrichment so Synology web evidence renders as raw protocol `http`; future FTP/SMB/NFS/WebDAV sources can provide their concrete network protocol directly.
- Configured NAS targets through `config/nas-targets.json`; `rawdb` is now the default enabled target with `file_station_remote` source. Future NAS targets can be added as additional objects in the same config file.
- Updated `DLP 檔案證據總覽` with a `$nas` Loki template variable and `nas_host` filters so one dashboard can switch between rawdb and future NAS targets.
- Updated runtime defaults from fixture mode to rawdb `file_station_remote`; dashboard queries exclude `fixture_smoke=true` events so old demo streams do not appear in file evidence panels.
- Validation: `jq empty grafana/dashboards/warroom-dlp-file-evidence.json` passed.
- Validation: Loki `query_range` returned non-JSON one-event-per-line output for Drive preview, File Station download, and combined file evidence queries; File Station fixture renders `120.562 KB`.
- Validation: local dry-run emits `network_protocol=http`; missing `WARROOM_GEOIP_MMDB_PATH` file emits `capability_gap`; helper validation maps MaxMind-style `{country, subdivisions}` records to `source_country/source_region`.
- Validation: Docker Compose config passed. Docker image rebuild was blocked by Docker Hub TLS metadata timeout for `python:3.12-slim`; code-level and compose-level validation passed.
- Validation: rawdb config dry-run emits `capability_gap` with `nas_host=rawdb` and no fixture fallback; pushed one rawdb capability-gap event to Loki for dashboard visibility.
- Architecture Sync: Updated `specs/architecture.md` for local-MMDB GeoIP enrichment and protocol normalization.

## Rawdb Real-Source Cutover — 2026-05-01

- Removed runtime/dashboard dependency on `warroom-placeholder` and synthetic metrics/logs.
- Removed `services/warroom-placeholder/app.py` dead code so it cannot be accidentally reintroduced by Compose/dashboard drift.
- Removed collector fixture source support (`fixtures`, `WARROOM_DLP_FIXTURE_GLOB`, `fixture_smoke`) from runtime code and dashboard LogQL.
- Updated `warroom-local-overview` to use `warroom-dlp-file-collector` metrics and `job="warroom-dlp-event-collector"` Loki streams instead of placeholder streams.
- Added `tools/nas_home_log_adapter.py` for rawdb NAS home-scope metadata evidence. It tails configured NAS log files over SSH stdin and normalizes only lines referencing `/home`, `/homes`, or `/volume*/homes` paths.
- Extended `config/nas-targets.json` rawdb target to include `sources=["file_station_remote", "nas_home_log_remote"]`.
- Updated `DLP 檔案證據總覽` to include `source_app="nas_file_service"` and home-scope actions `file_activity`, `file_read`, `file_write`, `file_delete`, and `file_rename`.
- Validation: `python3 -m py_compile services/warroom-dlp-file-collector/app.py tools/nas_home_log_adapter.py tools/file_station_transfer_adapter.py tools/dlp_event_collector.py` passed.
- Validation: `jq empty config/nas-targets.json`, `jq empty grafana/dashboards/warroom-dlp-file-evidence.json`, and `jq empty grafana/dashboards/warroom-local-overview.json` passed.
- Validation: `docker compose config` passed.
- Validation: collector dry-run emitted only rawdb capability gaps for inaccessible real sources; no placeholder, fixture, or synthetic event was produced.
- Architecture Sync: Updated `specs/architecture.md` for placeholder removal, rawdb multi-source config, and NAS home-scope log evidence flow.

## Terminal Stream Presentation Update — 2026-05-01

- Updated `grafana/dashboards/warroom-dlp-terminal-stream.json` panel `Collector / 正規化 Drive 與 File Station 事件` to render normalized collector JSON as one-line plain text via Loki `| json | line_format`.
- Disabled log labels/details/time column for that collector panel so parsed JSON fields do not appear as raw JSON or duplicate metadata.
- Disabled log labels/details/time column for `Terminal / DLP 綜合證據流` and `Terminal / 檔案動作候選事件` so Grafana no longer adds duplicate timestamp or label chips such as `method=GET/POST` on top of nginx log content.
- Validation: `jq empty grafana/dashboards/warroom-dlp-terminal-stream.json` passed.
- Follow-up: disabled the remaining Grafana log time columns across `warroom-dlp-file-evidence`, `warroom-dlp-terminal-stream`, `warroom-local-overview`, and `warroom-dlp-web-ingress` so event payload/log-line timestamps are the only timestamps shown.
- Validation: no dashboard JSON under `grafana/dashboards/` contains `"showTime": true`; all four dashboard JSON files validate with `jq empty`.

## Webalizer-style Insights Dashboard — 2026-05-01

- Added `grafana/dashboards/warroom-dlp-insights.json` with uid `warroom-dlp-insights` and title `DLP 行為統計與 Webalizer-style Insights`.
- First panel batch covers: total normalized events, capability-gap count, action trend, login user activity ranking, source IP ranking, network protocol ranking, folder ranking, file ranking, download/export ranking, source country ranking, source region ranking, source channel ranking, and capability-gap ranking.
- Dashboard queries aggregate only existing Loki evidence and payload fields (`actor`, `source_ip`, `network_protocol`, `folder_path`, `file_name`, `source_country`, `source_region`, `source_channel`, `gap_stage`). Missing values are excluded rather than inferred.
- GeoIP country/region panels depend on local-MMDB enrichment already written into Loki payloads; the dashboard does not call external geolocation APIs and does not guess private/unknown locations.
- Added navigation links from `warroom-dlp-file-evidence`, `warroom-dlp-terminal-stream`, `warroom-dlp-web-ingress`, and `warroom-local-overview` to the insights dashboard, and links back from insights to file evidence, terminal stream, and web ingress.
- Validation: `jq empty grafana/dashboards/*.json` passed.
- Validation: `docker compose config --quiet` passed.
- Validation: `warroom-dlp-insights` contains 13 panels and 13 query expressions; all query expressions are non-empty and contain no `fixture` / `placeholder` references.
- Architecture Sync: Updated `specs/architecture.md` to include the insights dashboard, its observed-evidence-only aggregation boundary, and validation signal.
