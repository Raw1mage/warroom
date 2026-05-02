# Event 2026-05-02 — Server Root Config/Data Refactor

## 需求

依使用者要求，將 Warroom NAS collection layout 改成：`/tools` 保持 global reusable code；每台 server 以 repo root 下的 `/<server>/config` 與 `/<server>/data` 管理設定與本地 runtime/audit/spool 資料。

## 範圍 IN

- 保留 `/tools` 作為 global adapter/tool layer。
- 新增 `rawdb/` 與 `lishanmei/` server roots。
- 支援 `/<server>/config/target.json` 與 `/<server>/config/sources.json`。
- 支援 collector 將 normalized events 與 run state 寫到 `/<server>/data`。
- 保留舊 `config/nas-targets.json` 相容回退。

## 範圍 OUT

- 不把 Grafana 改成直接讀檔案；Grafana 仍查 Loki/Prometheus。
- 不在 NAS 上新增 persistent agent/exporter/container。
- 不移除現有 global config，避免一次性破壞現場。

## 任務清單

- [x] 1.1 記錄目標 folder contract。
- [x] 1.2 新增 per-server config/data skeletons。
- [x] 1.3 更新 collector server-root loading。
- [x] 1.4 新增 per-server data spool/state。
- [x] 1.5 驗證與架構同步。

## Debug Checkpoints

### Baseline

- Current config source: `config/nas-targets.json` contains all target definitions.
- Current global tool layer: `tools/*_adapter.py` already works as parameterized reusable code.
- Current collector: `services/warroom-dlp-file-collector/app.py` loads a central targets file and pushes normalized events to Loki.

### Instrumentation Plan

- Verify new server roots load into equivalent target dictionaries.
- Verify fallback central config remains available if no server roots exist.
- Verify collector can create/write server `data/normalized` and `data/state`.
- Verify Compose mounts expose server roots to the collector container.

### Execution

- Added `rawdb/config/target.json`, `rawdb/config/sources.json`, and `rawdb/data/{raw,normalized,metrics,state}` skeletons.
- Added `lishanmei/config/target.json`, `lishanmei/config/sources.json`, and `lishanmei/data/{raw,normalized,metrics,state}` skeletons.
- Updated `services/warroom-dlp-file-collector/app.py` to prefer `WARROOM_SERVER_ROOTS_DIR` server roots, merge `target.json` SSH settings into each source, and keep `config/nas-targets.json` as fallback.
- Updated collector to write per-server local spool/state when `data_root` exists: `data/normalized/events.jsonl`, `data/normalized/capability_gaps.jsonl`, and `data/state/last_run.json`.
- Updated `docker-compose.yml` to set `WARROOM_SERVER_ROOTS_DIR=/servers` and mount the repo at `/servers` for server-root discovery/spool.
- Added `docs/ops/server-root-layout.md`.
- Updated `.gitignore` so runtime `/<server>/data` contents stay local while `.gitkeep` directory skeletons remain trackable.

### Root Cause / Design Decision

Central target config is functional but mixes per-server config into one global file. The new responsibility split keeps code under `/tools`, while per-server settings and local spool/state live under `/<server>`.

### Validation

- `python3 -m py_compile services/warroom-dlp-file-collector/app.py tools/dlp_event_collector.py`: pass.
- Server-root loading check with `WARROOM_SERVER_ROOTS_DIR=.` returned `lishanmei` and `rawdb` targets with expected source lists, data roots, and SSH hosts.
- Temporary spool unit check wrote `events.jsonl`, `capability_gaps.jsonl`, and `last_run.json`: pass.
- `docker compose config`: pass.
- `docker compose up -d warroom-dlp-file-collector`: pass; collector recreated with `WARROOM_SERVER_ROOTS_DIR=/servers`.
- Runtime check inside `warroom-dlp-file-collector`: `/servers/lishanmei/config/target.json` and `/servers/rawdb/config/target.json` visible, `/metrics` healthy.
- Actual runtime spool observed: `lishanmei/data/state/last_run.json` and `rawdb/data/state/last_run.json` created after collector start.

## Architecture Sync

Updated `specs/architecture.md` and added `docs/ops/server-root-layout.md` to document `/tools` global responsibility, `/<server>/config`, `/<server>/data`, legacy fallback, and Grafana/Loki/Prometheus boundaries.
