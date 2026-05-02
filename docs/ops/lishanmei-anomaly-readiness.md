# 利善美智能資料收集與異常偵測盤點

## 現有資料來源

目前利善美智能使用 `/<server>/config` 設定，`/tools` 為 global reusable adapter layer。

`lishanmei/config/sources.json` 已啟用：

- `host_health_remote`
- `file_station_remote`
- `nas_home_log_remote`
- `nas_system_log_remote`

最近 1 小時 Loki 觀測到的主要資料：

- `host_health_snapshot`: 73
- `webapp_file_download`: 86
- `file_station_transfer_db/unknown`: 14
- `nas_home_log/file_activity`: 3285
- `nas_home_log/file_read`: 35
- `nas_system_log/auth_activity`: 10
- `nas_system_log/system_log`: 390

最近 15 分鐘與 1 小時沒有 active `capability_gap`。最近 24 小時仍有 historical gap：

- `file_station_remote/adapter_returned_failure/returncode=1`: 15
- `nas_home_log_remote/adapter_returned_failure/remote_home_log_adapter_failed`: 12
- `nas_home_log_remote/adapter_returned_failure/returncode=1`: 2
- `host_health_remote/unsupported_source/source mode is not supported by this collector`: 5
- `nas_system_log_remote/unsupported_source/source mode is not supported by this collector`: 2

`unsupported_source` 是舊 collector 能力未支援時留下的 historical gap；目前已支援 `host_health_remote` 與 `nas_system_log_remote`。

## 已具備的異常偵測基礎資料

### 大流量 / 流量突增

`host_health_remote` 已收：

- `network_total_rx_bytes`
- `network_total_tx_bytes`
- `network_total_rx_packets`
- `network_total_tx_packets`
- `network_total_rx_errors`
- `network_total_tx_errors`
- `network_total_rx_drops`
- `network_total_tx_drops`
- interface count / up interface count

可用 Loki `rate(... unwrap network_total_*_bytes ...)` 建立 RX/TX throughput anomaly。

缺口：目前主要是總量 counters，缺 per-interface throughput、per-service/per-client flow、連線數與 top talkers。

### 登入錯誤 / 異常登入嘗試

`nas_system_log_remote` 已產生 `auth_activity`，包含部分 `message_excerpt`、service、path ref。

缺口：目前 parsing 偏 keyword-based，`event_outcome`、`auth_user`、`source_ip` 並不穩定；部分非登入錯誤如 UPS failed 也被歸到 `auth_activity`，需要更精準 regex/parser。

### 檔案下載 / 外流行為

`file_station_remote` 已產生 `webapp_file_download`，欄位包含 actor/source_ip/path/size_bytes（視 DB 欄位存在與否）。

缺口：

- `unknown` action 仍存在，代表 File Station command mapping 未完整。
- 純 preview/open 未必進 `.DSMFMXFERDB`，仍需 Drive DB / DSM audit / nginx route correlation 補證。
- 缺下載 session duration、response bytes、HTTP status、user-agent。

### 檔案服務活動

`nas_home_log_remote` 可從 home-scope log normalized 出 `file_activity`、`file_read` 等。

缺口：大量 `file_activity` 是低 confidence home-path match，缺完整 actor/source_ip/action_reason；適合當 signal，不適合單獨當高可信告警。

## 可透過 SSH 腳本補齊的 gap

高優先：

1. `auth_log_adapter`
   - 針對 SSH/DSM/SMB/FTP/WebDAV login success/failure 建結構化 parser。
   - 輸出 `auth_success` / `auth_failure` / `auth_lockout` / `session_opened` / `session_closed`。
   - 欄位：`actor`, `source_ip`, `service`, `event_outcome`, `failure_reason`, `geoip`, `observed_at`。

2. `network_socket_adapter`
   - transient 執行 `ss` / `netstat` / `/proc/net/*`，收連線數與 listening ports。
   - 欄位：`tcp_established_count`, `remote_ip_count`, `service_port`, `state`, top remote IPs（bounded）。
   - 可用於突增連線、異常 remote IP、服務曝露變動。

3. `file_station_transfer_adapter` 強化
   - 對 `unknown` command 增加 command histogram 與 raw command reason。
   - 保留 bounded `command_normalized`，建立新 mapping。

4. `host_health_adapter` 強化
   - per-interface counters，不只 total counters。
   - load/cpu/memory/network 建 baseline-friendly scalar。

中優先：

5. `dsm_audit_adapter`
   - 探測 DSM audit / synolog DB / log sources，補 DSM GUI login、share link、permission change、package/service changes。

6. `nginx_access_adapter`
   - 解析 access log 的 route/status/bytes/source_ip/user_agent。
   - 用於下載 HTTP bytes、異常 user-agent、非上班時間 web access。

## SSH 長連線框架評估

目前模式是每個 adapter 各自：

```text
ssh <server> sudo -n python3 - < adapter_script
```

這是安全、簡單、容易 fail-fast 的 transient 模式，但連線 overhead 較高，也不適合高頻近即時監測。

可改良成「單次 SSH 送一包 execution plan」：

```text
local collector
  -> ssh <server> sudo -n python3 -
  -> stdin: runner framework + JSON execution_plan
  <- stdout: JSONL result stream
  -> local log mechanism / Loki push / per-server spool
```

建議不要做真正永久 daemon，也不要在 NAS 安裝 agent。可以做 bounded long-running session：

- local 端保持一條 SSH process。
- remote stdin 一次送入 runner + execution plan。
- remote runner 在單一 process 內定時執行多個 read-only collectors。
- stdout 每輪輸出 JSONL envelope。
- local 端讀 stdout，寫 `/<server>/data/raw` / `normalized`，再 push Loki。
- session 有 TTL、max cycles、heartbeat、timeout；結束後由 local collector 重開。

這樣符合「不部署 persistent NAS agent」，也能減少 SSH overhead。

建議 execution plan schema：

```json
{
  "schema_version": 1,
  "nas_host": "lishanmei",
  "ttl_seconds": 300,
  "interval_seconds": 30,
  "sources": [
    {"name": "host_health", "interval_seconds": 30},
    {"name": "auth_log", "interval_seconds": 15},
    {"name": "network_socket", "interval_seconds": 15},
    {"name": "file_station_transfer", "interval_seconds": 60}
  ]
}
```

stdout JSONL envelope：

```json
{"type":"heartbeat","nas_host":"lishanmei","observed_at":1777690000}
{"type":"events","source":"auth_log","events":[...]}
{"type":"capability_gap","source":"network_socket","stage":"command_missing","detail":"ss not found"}
```

## 異常偵測資料需求 vs 現況

| 異常問題 | 現況是否足夠 | 缺口 |
|---|---:|---|
| 超大總流量 | 部分足夠 | 有 total network counters，可算 throughput；缺 per-interface/per-service/top remote IP |
| 異常登入錯誤 | 不足 | 有 auth_activity 但 parser 太粗；缺 outcome/user/source_ip/failure_reason 穩定欄位 |
| 異常時間登入 | 不足 | 需要 structured auth events + user/IP + time-of-day baseline |
| 異常時間下載 | 部分足夠 | 有 File Station downloads；缺 HTTP/nginx bytes、Drive/open/share link correlation |
| 大檔案下載 | 部分足夠 | File Station DB 可能有 size_bytes；需驗證欄位完整度；HTTP response bytes 缺 |
| 暴力破解 | 不足 | 需要 auth_failure by source_ip/user/service rolling windows |
| 服務曝露/連線突增 | 不足 | 需要 socket/listening-port/top remote IP source |
| DSM 設定/權限異動 | 不足 | 需要 DSM audit/synolog sources |
| 檔案大量操作 | 部分足夠 | nas_home_log 有大量 file_activity，但 confidence/actor/source_ip 不穩定 |

## 建議實作順序

1. 先修 active dashboard 語意：把 `Capability gap` 分成 active/historical，避免 historical gap 誤導。
2. 新增 `auth_log_adapter`，解決登入異常偵測最重要的結構化資料缺口。
3. 新增 `network_socket_adapter`，補連線數/top remote IP/listening ports。
4. 強化 `file_station_transfer_adapter` unknown command mapping 與 `size_bytes` completeness。
5. 建立 bounded SSH execution-plan runner，先用 5 分鐘 TTL，取代多個短 SSH call。
6. 在 Grafana 增加 anomaly readiness dashboard：資料覆蓋率、active gaps、auth failures、traffic spikes、large downloads、off-hours events。
