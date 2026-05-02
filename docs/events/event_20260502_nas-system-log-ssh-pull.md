# Event: NAS system log SSH pull

## 需求

- 使用者指出利善美智能 dashboard 不應以 CPU / memory / disk 等 host health 數值取代資料安全監測。
- Warroom 必須透過 SSH 連進 `nas.wuyang.co`，實際盤點 NAS 內部可讀的各種系統 / 服務 log，並把 log stream 帶回 Loki。
- 釐清「誰讀了哪些檔案」只能來自 File Station transfer DB、Drive DB 或 NAS 本身的 audit log；一般 host health 不能推導檔案活動。

## 範圍

IN:
- 新增 `nas_system_log_remote` source，透過 SSH transient payload tail NAS 端既有 log files。
- 將 `nas_system_log` events push 到 Loki，label 固定包含 `nas_host` / `source_channel` / `source_app`。
- 利善美 DLP file evidence dashboard 新增「NAS 系統 / 服務 log 串流」panel。
- 以 capability gap 說明服務 log stream 不等同 kernel-level / SMB full_audit per-file read audit。

OUT:
- 不在 NAS 上安裝 exporter / agent / container。
- 不讀取使用者檔案內容。
- 不把 SSH key bake 進 image 或 commit 到 repo。

## 任務清單

- [x] 新增 `tools/nas_system_log_adapter.py`。
- [x] 更新 `services/warroom-dlp-file-collector/app.py` 支援 `nas_system_log_remote`。
- [x] 更新 `config/nas-targets.json` / `config/nas-targets.example.json` / `.env*` / `docker-compose.yml`。
- [x] 重建 `warroom-dlp-file-collector` 並驗證 Loki 有 `source_channel="nas_system_log"`。
- [x] 更新 `grafana/dashboards/lishanmei-dlp-file-evidence.json` 加入系統 / 服務 log stream panel。

## Debug checkpoints

- Baseline: `host_health_remote` 只有 uptime / service / memory / cpu / disk / process，不代表 filesystem activity。
- Instrumentation: 遠端以 SSH stdin payload 查 `nas.wuyang.co` 可讀 log source。
- Evidence: `nas.wuyang.co` 目前可讀 `/var/log/messages`、`/var/log/samba/log.smbd`、`/var/log/samba/log.nmbd`、`/var/log/auth.log`；未看到 `synofile` / `synosmb` audit log 檔存在。
- Root Cause: dashboard 空值與誤導來自把 host health 當資料安全主訊號；檔案活動應使用 File Station DB / NAS service logs / explicit audit logs。
- Validation:
  - `python3 -m py_compile services/warroom-dlp-file-collector/app.py tools/*.py` passed。
  - `jq empty config/nas-targets.json config/nas-targets.example.json` passed。
  - `docker compose up -d --build --force-recreate warroom-dlp-file-collector` passed。
  - Loki query: `source_channel="nas_system_log"` for `nas_host="lishanmei"` returned 200 entries in 5m。
  - Dashboard JSON validation passed for `grafana/dashboards/lishanmei-dlp-file-evidence.json`。

## Key decisions

- `nas_system_log_remote` captures redacted service/system log lines and keeps raw evidence references (`raw_ref.path`, `raw_ref.line_ref`, `sha256_24`).
- `nas_system_log` is evidence of service/system log activity; it must not be represented as guaranteed per-file read audit.
- File Station DB events remain the stronger evidence for `actor + action + display_path + source_ip` downloads.

## Remaining

- If the operator requires exhaustive SMB per-file reads, enable/locate Synology audit logs or Samba `full_audit` on the NAS side, then add that log path as another `nas_system_log_remote.log_paths` source.

## Architecture Sync

- Verified: architecture remains non-intrusive SSH pull. This task extends the collector source catalog with `nas_system_log_remote`; no NAS-side persistent agent was introduced.
