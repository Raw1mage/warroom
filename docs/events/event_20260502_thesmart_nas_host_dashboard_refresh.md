# Event 2026-05-02 — 利善美 NAS 主機基本數值監控 Dashboard 改版

## 需求

使用者希望在所有 dashboard 都已可外連編輯後，依照剛才要求重新改版：利善美 NAS 主機基本數值監控需能真的看到 CPU、Disk、網路等基本監測數值，並評估是否需要讓 NAS 跑 node_exporter。

## 範圍

IN:
- 改版利善美 Grafana dashboards 與 NAS Host Health dashboard。
- 優先使用現有 `host_health_remote` SSH transient payload 事件作為 CPU/Memory/Disk/Service/Network evidence。
- 讓利善美總覽、DLP 檔案證據、Web ingress、Insights、Terminal stream 都能導向 NAS Host Health。

OUT:
- 不新增 NAS-side node_exporter、container、Promtail 或 persistent Warroom agent。
- 不提交任何 SNMP credential、SSH key 或 NAS secret。

## 任務清單

- 1.1 Establish plan/event ledger for 利善美 NAS host monitoring dashboard refresh
- 1.2 Inventory current dashboards and host health data contract
- 1.3 Update dashboards to surface CPU, memory, disk, network/service health and host-health links
- 1.4 Validate JSON/YAML and update architecture/event evidence

## Key Decisions

- DD-1: 不在利善美 NAS 上部署 node_exporter。現有架構 `host_health_remote` 已用 SSH transient payload 取得 uptime/load/memory/CPU jiffies/disk/process/service status，符合 metadata-only、no persistent NAS-side agent 的邊界。
- DD-2: SNMP exporter 維持 optional/template-only；若未來需要 DSM/SNMP MIB 細節，需另外批准並設定 SNMP path。

## Debug Checkpoints

### Baseline

- 現有 `warroom-nas-host-health` 已有 host health snapshot log panels，但不夠像基本監控 dashboard。
- `specs/architecture.md` 明確記錄 NAS-side posture：不跑 persistent agent/exporter/container，Prometheus 不直接 scrape monitored NAS hosts。

### Instrumentation Plan

- Component boundary: `tools/host_health_adapter.py` payload fields → Loki labels/payload → Grafana dashboard LogQL/JSON panels。
- Validation: JSON parse dashboard files；YAML parse Compose/Prometheus provisioning；確認不新增 NAS-side exporter。

### Execution

- `grafana/dashboards/warroom-nas-host-health.json` 改成 NAS 基本監控 dashboard，預設利善美並使用 `source_channel="host_health"` / `source_app="nas_host_health"` Loki evidence。
- Host Health dashboard panels 覆蓋 CPU busy percent、memory used percent、disk max/volume use percent、uptime/load/process count、service/network-facing status 與 raw snapshot drill-down。
- `grafana/dashboards/thesmart-local-overview.json`、`thesmart-dlp-file-evidence.json`、`thesmart-dlp-web-ingress.json`、`thesmart-dlp-insights.json`、`thesmart-dlp-terminal-stream.json` 均新增 `開啟 NAS 主機監控` dashboard link。
- 依使用者後續要求，將 `grafana/dashboards/thesmart-dlp-terminal-stream.json` 的 `Terminal / DLP 綜合證據流` logs panel 改為 `DLP 綜合 evidence insight 比例` pie chart，不再直接依 raw `action` 分組，而是歸類成檔案外流/下載匯出、開檔/預覽/分享瀏覽、NAS 檔案服務活動、主機健康/資源監測、NAS 系統/服務事件、能力缺口/收集失敗與其他 evidence。
- 未新增 node_exporter、SNMP real target、NAS-side container 或 persistent agent。

## Verification

- Dashboard JSON parse: pass for `warroom-nas-host-health.json` and all five `thesmart-*.json` dashboards.
- Plan JSON parse: pass for `plans/20260502_thesmart_nas_host_dashboard_refresh/idef0.json` and `grafcet.json`.
- Dashboard content check: pass; all five利善美 dashboards link to `warroom-nas-host-health`, and host-health dashboard references `cpu_busy_percent`, `memory_used_percent`, `disk_max_use_percent`, `disk_volume1_use_percent`, `service_ssh_up`, `service_smb_up`, `service_nginx_up`, `process_count`, and `uptime_seconds`.
- Terminal insight pie panel check: pass; `thesmart-dlp-terminal-stream.json` panel `id=10` is `piechart`, uses instant queries, and exposes seven semantic evidence categories instead of raw action buckets.
- `docker compose config`: pass.
- YAML parse: pass for Prometheus config/template and Grafana provisioning files.

## Architecture Sync

- Verified (No doc changes). `specs/architecture.md` already records the intended boundary: no persistent NAS-side Warroom agent/exporter/container, local `warroom-dlp-file-collector` exposes host/service observations from SSH payloads, and `host_health_remote` captures uptime, load, memory, CPU jiffies, disk usage, process count, and service status metadata.
