# 利善美智能異常偵測與資料收集強化計畫

## Goal

把利善美智能從「資料流水帳 dashboard」提升成「異常偵測 readiness dashboard + 可擴展 SSH 收集框架」。第一階段以不在 NAS 安裝 persistent agent 為前提，補齊登入異常、網路連線異常、active capability gaps 與基礎 dashboard 呈現。

## Scope IN

- Capability gap dashboard 改成 active vs historical，避免舊 gap 誤導。
- 新增 `auth_log_adapter`：結構化登入成功/失敗/鎖定/session 事件。
- 新增 `network_socket_adapter`：連線數、listening ports、top remote IP、socket state summary。
- 整合 `lishanmei/config/sources.json` 與 collector source dispatch。
- 新增/調整 anomaly readiness dashboard panels。
- 仍使用 SSH transient payload；不在 NAS 部署 persistent daemon。

## Scope OUT

- 不建立 NAS-side persistent agent/container/exporter。
- 不做自動封鎖、刪檔、停帳等 destructive response。
- 不將 Grafana 改成直接讀 `/<server>/data`。
- Bounded long-running SSH execution-plan runner 本輪只設計/預留，不作為第一階段必要完成項；若時間允許再落地 MVP。

## Current Evidence

- 最近 15m / 1h：`lishanmei` 無 active `capability_gap`。
- 最近 24h 有 historical gaps，主要是舊 collector unsupported source 與 transient adapter failures。
- 現有資料可支援總量流量與粗略檔案下載觀測，但登入異常與連線異常仍缺結構化資料。

## Design Decisions

- **DD-1** `/tools` 維持 global reusable adapters；`/lishanmei/config` 與 `/lishanmei/data` 維持 server-specific config/spool。
- **DD-2** 新 adapters 均採 SSH stdin transient payload，輸出 normalized JSON events；collector 負責 push Loki 與 per-server spool。
- **DD-3** capability gap dashboard 需區分 active windows（15m/1h）與 historical windows（24h），不能只看總 histogram。
- **DD-4** anomaly 偵測先採 rule/readiness signals：auth failures、traffic spikes、large downloads、off-hours events、connection spikes。
- **DD-5** bounded long-running SSH runner 若實作，必須有 TTL/heartbeat/max cycles，不能變成 NAS persistent agent。

## Validation Plan

- Python compile for new/changed adapters and collector.
- Local mode unit smoke tests for adapters.
- Collector `_load_targets` and source dispatch smoke test.
- Docker Compose config validation.
- Dashboard JSON validation.
- Loki query smoke tests for active/historical gap panels and new source event labels.

## Stop Gates

- If SSH credentials/permissions fail, emit capability gap; do not add fallback fake data.
- If a source requires persistent NAS install, stop and ask approval.
- If dashboard query requires unavailable Loki/Grafana feature, use simpler LogQL panels instead of silent workaround.
