# Event 2026-05-02 — Reboot Recovery

## 需求

Host reboot 後 Warroom Grafana 首頁 dashboard 載入失敗；需要可恢復、可自動化的開機後 recovery 機制，避免 Grafana 綁到空 dashboard mount 或核心服務停在 exited。

## 範圍 IN

- 等待 Warroom project path 與 dashboard JSON ready。
- 啟動 Docker Compose stack。
- 驗證 Grafana 容器內 dashboard JSON 可見。
- 提供 systemd oneshot unit 範本。
- 不刪除 Loki/Prometheus/Grafana volumes。

## 範圍 OUT

- 不重建 NAS-side agent/exporter。
- 不執行 `docker compose down -v`。
- 不自動安裝 systemd unit 到 `/etc/systemd/system`。

## 任務清單

- [x] 1.1 說明 dashboard 可恢復與根因邊界。
- [x] 1.2 新增 `scripts/warroom-recover-after-boot.sh`。
- [x] 1.3 新增 `deploy/systemd/warroom-compose-recover.service`。
- [x] 1.4 驗證腳本、Compose 與 dashboard bind-mount check。
- [x] 1.5 更新架構同步/驗證結論。

## Debug Checkpoints

### Baseline

- Symptom: Grafana 顯示 `Dashboard failed to load` / `Failed to load home dashboard`。
- Boundary: Grafana home dashboard provisioning / dashboard bind mount / Docker Compose startup ordering。
- Initial evidence from prior checks: host repo dashboard files still exist; Grafana container did not see dashboard JSON after reboot; Loki/Prometheus/collector may also be exited.

### Instrumentation Plan

- Check script syntax with `bash -n`.
- Check Compose validity with `docker compose config`.
- Check that recovery script validates host dashboard file before compose start.
- Check that recovery script validates container dashboard file after compose start.

### Execution

- Added `scripts/warroom-recover-after-boot.sh`.
- Added `deploy/systemd/warroom-compose-recover.service`.
- Added `docs/ops/reboot-recovery.md`.
- The script waits for `docker-compose.yml` and `grafana/dashboards/lishanmei-dlp-file-evidence.json`, runs `docker compose up -d --remove-orphans`, then verifies the Grafana container sees `/var/lib/grafana/dashboards/lishanmei-dlp-file-evidence.json`.

### Root Cause

Working root cause: reboot startup ordering allowed Docker containers to start before the project/dashboard bind mount path was ready, so Grafana saw an empty dashboard directory and could not load the configured home dashboard.

### Validation

- `bash -n scripts/warroom-recover-after-boot.sh`: pass.
- `docker compose config`: pass.
- `scripts/warroom-recover-after-boot.sh`: pass; stack started without deleting volumes and Grafana dashboard bind mount was visible inside `warroom-grafana`.
- `docker exec warroom-grafana test -f /var/lib/grafana/dashboards/lishanmei-dlp-file-evidence.json`: pass.
- `docker exec warroom-dlp-file-collector python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8010/metrics", timeout=5).read(1)'`: pass.
- `curl http://127.0.0.1:3000/warroom/api/health`: pass.
- `curl http://127.0.0.1:3100/ready`: pass after normal Loki startup delay.
- `curl http://127.0.0.1:9090/-/ready`: pass.

## Architecture Sync

Updated `specs/architecture.md` with the reboot recovery lifecycle boundary and artifact paths.
