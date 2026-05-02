# Event 2026-05-02 — 免侵入式 SSH Remote Payload 主機指標擴充

## 需求

使用者指出：`ssh + shell script` 或 remote payload 已能創造足夠資訊實作 dashboard；希望開發一組免侵入式 remote payload，透過 SSH command 跑了直接拿數據，cron/週期由 Warroom 自己掌控。

## 範圍

IN:
- 擴充既有 `host_health_remote` / `tools/host_health_adapter.py` transient payload。
- 補齊 network interface counters 與 dashboard-friendly scalar summaries。
- 維持 Warroom-side collector/cron interval 控制。

OUT:
- 不在 NAS 部署 node_exporter、container、daemon、Promtail 或 NAS-side cron。
- 不提交 secret 或 credential。

## 任務清單

- 1.1 Establish plan/event ledger for SSH remote payload metrics expansion
- 1.2 Inventory existing host health payload and collector flow
- 1.3 Extend remote payload with network interface counters and scalar summaries
- 1.4 Update dashboard references if needed and validate payload/config/docs

## Key Decisions

- DD-1: 採用現有 SSH stdin Python payload 作為 remote command 載體；不新增 persistent exporter。
- DD-2: Network bandwidth 先輸出 cumulative counters，不在 payload 內猜 rate；Grafana/Loki 或後續 collector delta 負責時間序列 rate。

## Debug Checkpoints

### Baseline

- `host_health_adapter.py` 已支援 uptime/load、memory、CPU busy/jiffies、disk、process count、service status。
- 缺口：沒有 network interface byte/packet/error/drop counters，dashboard 只能顯示 service/network-facing status，無法顯示實際 NIC counters。

### Instrumentation Plan

- Component boundary: NAS `/proc/net/dev` + `/sys/class/net/*` → transient payload JSON → collector Loki event → Grafana dashboard panels。
- Evidence: local payload JSON contains `network` list and scalar total counters。

### Execution

- `tools/host_health_adapter.py` 新增 `_network()` 與 `_network_summary()`，透過 `/proc/net/dev` 取得 NIC cumulative byte/packet/error/drop counters，並透過 `/sys/class/net/<iface>/` 補 `operstate`、`carrier`、`speed`、`mtu`。
- Host health event 新增 `network` list 與 scalar 欄位：`network_interface_count`、`network_up_interface_count`、`network_total_rx_bytes`、`network_total_tx_bytes`、`network_total_rx_packets`、`network_total_tx_packets`、`network_total_rx_errors`、`network_total_tx_errors`、`network_total_rx_drops`、`network_total_tx_drops`。
- `grafana/dashboards/warroom-nas-host-health.json` 新增 NIC cumulative counters timeseries 與 network counter snapshot lines，並保留 service reachability panel。
- 未新增 NAS-side exporter、daemon、container、cron 或 Prometheus scrape port。

## Verification

- `python3 tools/host_health_adapter.py --mode local --nas-host test-nas`: pass; output contains `events[0].network` and scalar network totals.
- `python3 -m py_compile tools/host_health_adapter.py`: pass.
- `python3 -m json.tool grafana/dashboards/warroom-nas-host-health.json`: pass.
- `docker compose config`: pass.

## Architecture Sync

- Updated `specs/architecture.md` to include network interface counters in the `host_health_remote` metrics model and `tools/host_health_adapter.py` utility description.
