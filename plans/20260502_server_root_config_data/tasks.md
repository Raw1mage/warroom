# Server Root Config/Data Refactor Tasks

## 1. Server-root layout

- [x] 1.1 Capture target folder contract: `/tools` is global, `/<server>/config` and `/<server>/data` are server-specific
- [x] 1.2 Add per-server config/data skeletons for `rawdb` and `lishanmei`
- [x] 1.3 Update collector to scan server roots and merge `target.json` + `sources.json`
- [x] 1.4 Spool normalized events and run state into `/<server>/data`
- [x] 1.5 Validate config loading, collector syntax, Compose config, and architecture docs
