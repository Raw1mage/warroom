# Event: 利善美智能與 rawdb 非侵入式 SSH Pull 監測收斂

## 需求

- 將 Grafana dashboard folder 顯示名稱調整為「利善美智能」，重用原「陽光沙灘」Warroom dashboard 佈局。
- 讓既有 Warroom 監控 `nas.wuyang.co`，而不是在 NAS 上部署第二套 Grafana 或 Docker stack。
- 對 `nas.wuyang.co` 與 `rawdb` 採一致的非侵入式監測姿態：由 Warroom 端透過預先認證 SSH，把只讀 exporter/collector payload 送到 NAS 臨時執行並回收 stdout，再由本地 collector 推送 Loki / 暴露 Prometheus metrics。

## 範圍

### IN

- Grafana provisioning folder 名稱改為「利善美智能」。
- `config/nas-targets.json` 新增 `thesmart` 目標，透過 SSH 讀取 File Station transfer DB 與 NAS home-scope log metadata。
- `warroom-dlp-file-collector` 容器補齊 SSH client 與 SSH key mount，以便本地 collector 可透過 SSH 執行 transient payload。
- `specs/architecture.md` 同步：`rawdb` 與 `thesmart` 的預設監測模式皆為 SSH stdin payload pull，不是 NAS 端常駐 agent/exporter，也不是因區網便利而直接依賴 syslog。

### OUT

- 不在 `nas.wuyang.co` 部署 Docker、Grafana、Promtail、node_exporter 或任何常駐 Warroom agent。
- 不預設開啟 NAS 端 Prometheus scrape port，例如 `:9100`。
- 不把 direct syslog 當作 `rawdb` 或 `thesmart` 的標準收集路徑；Alloy/syslog profile 僅保留為明確批准的 compatibility/experimental path。
- 不收集檔案內容、不提交 NAS 密碼或 SSH 私鑰。

## 任務清單

- [x] 將 Grafana provisioning folder 顯示名稱改為「利善美智能」。
- [x] 將 `thesmart` 加入 NAS target config，沿用本地 collector 的 SSH remote adapter 模式。
- [x] 移除 Prometheus 對 `nas.wuyang.co:9100` / `thesmart-node-exporter` 的直接 scrape 設定。
- [x] 更新架構文件，明確規範 `rawdb` 與 `thesmart` 都應採 SSH payload pull 預設姿態。
- [x] 本機驗證 compose config 與 Python collector/helper 語法。

## Key Decisions

- **DD-1 非侵入式優先**：所有監測 NAS（包含區網內 `rawdb`）預設都由 Warroom 端透過 SSH stdin 傳 payload 臨時執行；不因區網便利而改用 direct syslog 或 NAS-side exporter 作為預設。
- **DD-2 metrics 歸屬本地**：NAS host/service metrics 由本地 `warroom-dlp-file-collector` `/metrics` 與 Loki event payload 表達；Prometheus 只 scrape 本地 Warroom services。
- **DD-3 syslog 例外化**：`synology-nginx-log-exporter` / direct syslog profile 保留，但定位為明確啟用的 compatibility/experimental path，不是標準 NAS 監測模式。

## Issues Found

- 先前規劃曾錯誤導向 NAS 端常駐 node_exporter/Promtail 與 reverse tunnel。已在 `prometheus/prometheus.yml` 移除 direct NAS scrape，並在 `specs/architecture.md` 改寫為 SSH payload pull。
- `rawdb` 原先容易被視為「因在區網內可直接接 syslog」的例外；本次決策收斂為 rawdb 與 thesmart 同規格，避免監測架構分裂。

## Verification

- `docker compose config`：通過；resolved config 中 Prometheus 僅包含本地 targets，未包含 `nas.wuyang.co:9100`。
- `python3 -m py_compile services/warroom-dlp-file-collector/app.py tools/file_station_transfer_adapter.py tools/nas_home_log_adapter.py`：通過。
- Search check：未在 active config 中發現 `thesmart-node-exporter`、`nas.wuyang.co:9100`、`warroom-node-exporter`、`warroom-promtail`；僅 legacy plan note 還有 `warroom-node-exporter-c` 設計名詞。
- Architecture Sync: Updated `specs/architecture.md` to make SSH stdin payload pull the default collection boundary for both `rawdb` and `thesmart`.

## Remaining

- 仍需由實際 SSH credentials / sudoers 狀態驗證 `rawdb` 與 `nas.wuyang.co` 的 remote payload execution 能回傳可解析 JSON。
- 若未來真的需要 reverse tunnel 或 NAS-side exporter，必須另行明確批准並記錄為 host-specific exception。

## Gap Resolution 2026-05-02

### Resolved: `thesmart/file_station_remote`

- Symptom: Loki capability gap `nas_host="thesmart"`, `source_channel="file_station_remote"`, `gap_stage="adapter_returned_failure"`.
- Root cause: remote File Station transfer DB adapter succeeded when run serially with a longer timeout, but the target config used `timeout_seconds: 30`, which was too short for the NAS-side SQLite scan and SSH payload round trip.
- Change: `config/nas-targets.json` now sets `thesmart.file_station_remote.timeout_seconds` to `90`.
- Validation: direct adapter run returned `events_normalized` from `/volume1/@database/synolog/.DSMFMXFERDB`; collector metrics later showed `events_pushed_total=249`, and Loki had 50 recent `nas_host="thesmart"`, `source_channel="file_station_transfer_db"` events.

### Verified clean: `thesmart/nas_home_log_remote`

- Symptom: older Loki capability gaps existed for `nas_home_log_remote`.
- Finding: after serial SSH testing and the longer running collector cycle, no new 1-minute gap appeared; Loki had 332 recent `nas_host="thesmart"`, `source_channel="nas_home_log"` events.
- Decision: no code/config change needed for this gap at this point; treat existing entries as historical gaps visible in the dashboard.

### Blocked: `rawdb/file_station_remote` and `rawdb/nas_home_log_remote`

- Symptom: rawdb continued producing capability gaps for both remote sources.
- Root cause evidence: container SSH initially ignored operator SSH config because adapters used `ssh -F /dev/null`; after removing that override and copying the mounted SSH directory into a container-owned `/root/.ssh`, OpenSSH could read config, but the config only contains `Host github.com` and no `Host rawdb` rule. Direct probes resolved rawdb as `root@rawdb` or `wuyangadmin@rawdb` and failed with `Permission denied (publickey,password)`.
- Change made: adapters now allow normal SSH config resolution; collector copies `${WARROOM_SSH_DIR}` from read-only `/ssh-ro` into a container-owned `/root/.ssh` with OpenSSH-compatible permissions at startup.
- Blocker: need an approved rawdb SSH target definition or credentials, e.g. `Host rawdb` in the mounted SSH config with the correct HostName/User/IdentityFile, or explicit `config/nas-targets.json` host/user values plus an available key.
