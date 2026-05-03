# Server Root Config/Data Layout

## Contract

Warroom separates reusable collection code from per-server configuration and runtime data:

```text
/tools/                 global reusable adapters and helpers
/<server>/config/       server-specific target/source settings
/<server>/data/         server-specific local runtime, audit, and spool data
```

Grafana does not read `/<server>/data` directly. Dashboards continue to query Loki and Prometheus. The data directory is for local debug, replay, and capability-gap state.

## Server config files

Each server root can contain:

```text
/<server>/config/target.json
/<server>/config/sources.json
```

`target.json` defines identity and SSH endpoint:

```json
{
  "schema_version": 1,
  "id": "thesmart",
  "display_name": "利善美智能",
  "enabled": true,
  "ssh": {
    "host": "nas.wuyang.co",
    "user": "wuyangadmin"
  }
}
```

`sources.json` defines enabled sources and per-source settings. Source settings inherit `ssh.host` and `ssh.user` unless explicitly overridden.

## Server data folders

```text
/<server>/data/raw/             reserved for raw adapter payload snapshots
/<server>/data/normalized/      collector-written JSONL event spool
/<server>/data/metrics/         reserved for Prometheus textfile/spool metrics
/<server>/data/state/           collector-written last run state
```

Current collector writes:

- `data/normalized/events.jsonl`
- `data/normalized/capability_gaps.jsonl`
- `data/state/last_run.json`

## Compatibility

`config/nas-targets.json` remains a fallback for existing deployments. If `WARROOM_SERVER_ROOTS_DIR` points to a directory with valid server roots, those roots are used first.
