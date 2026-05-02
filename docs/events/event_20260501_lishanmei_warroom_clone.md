# Event: 利善美智能 NAS 接入既有 Warroom

## 需求

- 使用既有 Warroom 監控 `nas.wuyang.co`。
- 監控對象命名為「利善美智能」。
- 保留第一個 Warroom「陽光沙灘」的既有 Grafana 版面與 dashboard，不在 `nas.wuyang.co` 部署第二套 Grafana。

## 範圍

### IN

- 在既有 `config/nas-targets.json` 新增 `lishanmei` target。
- 讓本機 Warroom collector 容器能透過 SSH 對 `nas.wuyang.co` 執行唯讀 metadata 取證。
- 驗證 File Station transfer DB 與 NAS home-scope log metadata 可進入 Loki，供既有 dashboard 以 `nas_host="lishanmei"` 過濾。

### OUT

- 不在 `nas.wuyang.co` 部署 Docker、Grafana、Loki、Prometheus 或 Warroom agent。
- 不修改 NAS DSM reverse proxy、DNS、Web Station 或 nginx。
- 不提交密碼、SSH 私鑰、cookie、token、raw credential-bearing URL 或檔案內容。

## Key Decisions

- **KD-1** Warroom runtime 仍只在本機/現有部署面執行；NAS 端只提供 SSH + sudo read-only metadata access。
- **KD-2** `nas_host` label 使用 `lishanmei`，display name 記錄為「利善美智能」。
- **KD-3** 錯誤方向的 `deploy/lishanmei/` 第二 stack 產物已移除，不納入本任務結果。

## Changes

- `config/nas-targets.json` 新增 enabled target：`id="lishanmei"`, `display_name="利善美智能"`, host `nas.wuyang.co`, user `wuyangadmin`。
- `docker-compose.yml` 將 collector 預設 sources 改為 `file_station_remote,nas_home_log_remote`，掛載 `app.py`、`tools/`、`config/`、`geoip/` 與本機 SSH 目錄供本機 collector 出站連線。
- `services/warroom-dlp-file-collector/Dockerfile` 安裝 `openssh-client`，供 remote adapters 使用 SSH。
- `tools/file_station_transfer_adapter.py` 與 `tools/nas_home_log_adapter.py` 在 SSH 呼叫中忽略容器內不相容的 host SSH config，避免 `/root/.ssh/config` ownership 檢查阻斷。

## Debug Checkpoints

### Baseline

- 使用者澄清需求是「既有 Warroom 連進 `nas.wuyang.co` 撈 log 回來做 dashboard」，不是在 NAS 上部署 Grafana。
- `wuyangadmin@nas.wuyang.co` 可 SSH 登入；使用者完成 sudoers 設定後，`sudo -n true` 成功。

### Instrumentation Plan

- 從 host 與 collector 容器分別執行 File Station DB adapter 與 NAS home log adapter dry-run。
- 查 Loki `{nas_host="lishanmei"}` range query，確認事件可供既有 Grafana dashboard 查詢。

### Execution

- Host dry-run 成功讀取 `/volume1/@database/synolog/.DSMFMXFERDB`，回傳 `webapp_file_download` 事件。
- Host dry-run 成功讀取 `/var/log/messages`、`/var/log/samba/log.smbd`、`/var/log/auth.log` 中 home-scope metadata。
- Collector container dry-run 成功回傳 `nas_host="lishanmei"` 的 File Station 與 NAS log metadata。
- `docker compose -f docker-compose.yml up -d --no-build warroom-dlp-file-collector` 已重建本機 collector 容器；沒有在 NAS 上部署任何容器。

### Root Cause / Design Finding

- 原先第二 stack 方向錯誤；正確設計是新增 monitored NAS target，並沿用既有 dashboard layout。
- Collector image 原本缺 SSH client，且 `/app/app.py` 是 build-time COPY；為避免 registry rebuild 阻塞，Compose 掛載 repo 內 `app.py` 作為本機開發/POC 的 source of truth。

## Validation

- `python3 -m py_compile tools/file_station_transfer_adapter.py tools/nas_home_log_adapter.py services/warroom-dlp-file-collector/app.py` 通過。
- `docker compose -f docker-compose.yml config` 通過。
- Collector container dry-run 產生 `nas_host="lishanmei"` events。
- Loki query_range `{nas_host="lishanmei"}` 回傳 `success`，result count `1`。
- Architecture Sync: `specs/architecture.md` 已同步新增 `lishanmei` target 與 SSH client requirement。
