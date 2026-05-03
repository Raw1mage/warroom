# Dashboard coverage and no-data remediation

## 需求

- 修正 Grafana dashboard 多處 No data 的問題。
- Dashboard 不應把未穩定接上的 File Station / Synology Drive / nginx ingress 當成主資料面板。
- 能由現有 collector 證據補上的欄位要補；不能補的資料源要輸出 coverage/gap 狀態，不得用 fallback 或假事件補齊。

## 範圍(IN)

- `services/warroom-dlp-file-collector/app.py` 增加 source/field coverage status event。
- `grafana/dashboards/thesmart-dlp-file-evidence.json` 調整來源 IP/GeoIP 查詢與 coverage 呈現。
- `grafana/dashboards/thesmart-dlp-web-ingress.json` 修正 dashboard 文案與查詢範圍，避免誤稱 nginx ingress。

## 範圍(OUT)

- 不新增 NAS 常駐 agent。
- 不讀取檔案內容、cookie、session token、credential-bearing URL。
- 不新增 fallback mechanism，不製造 File Station / Drive / download 假活動。

## 任務清單

- [x] Baseline：確認 Loki 最近 30 分鐘有 `nas_home_log/auth_log/host_health/network_socket` 事件。
- [x] Baseline：確認 `file_station/synology_drive` 目前沒有穩定事件，dashboard 因查詢範圍過窄而出現 No data。
- [ ] Execution：collector 增加 `coverage_status` 與 `field_coverage_status`。
- [ ] Execution：dashboard 查詢改用實際可用 evidence 與 coverage 狀態。
- [ ] Validation：Python compile、JSON lint、必要查詢驗證。

## Debug checkpoints

- Baseline：服務 healthy；Loki 有資料，不是 ingestion 全斷。
- Instrumentation Plan：在 collector cycle 邊界輸出 source coverage 與 field coverage，讓 dashboard 顯示「資料源無事件/缺欄位」而非 No data。
- Root Cause：dashboard 查詢把尚未穩定產生事件的來源當主視角，且缺少 coverage 狀態面板。

## Validation

- Pending.

## Architecture Sync

- Pending.
