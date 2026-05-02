# Bounded SSH Execution-Plan Runner MVP Contract

## Purpose

Reduce repeated SSH setup overhead while preserving the no-persistent-agent NAS boundary.

## Non-goals

- No NAS-side installed daemon.
- No background process surviving the SSH session.
- No destructive response actions.

## Execution model

```text
local collector
  -> ssh <server> sudo -n python3 -
  -> stdin: runner source + execution_plan JSON
  <- stdout: JSONL envelopes
  -> local spool + Loki push + Prometheus metrics
```

The remote runner runs only inside the SSH process. It exits when TTL, max cycles, timeout, or stdin/stdout failure occurs.

## Required controls

- `ttl_seconds`: maximum remote runner lifetime.
- `interval_seconds`: default source execution interval.
- `max_cycles`: hard cycle cap.
- `heartbeat_interval_seconds`: JSONL heartbeat cadence.
- Per-source timeout.
- Read-only collectors only.
- Capability gaps emitted on command/path/permission failures.

## Execution plan example

```json
{
  "schema_version": 1,
  "nas_host": "lishanmei",
  "ttl_seconds": 300,
  "max_cycles": 10,
  "heartbeat_interval_seconds": 30,
  "sources": [
    {"name": "host_health", "interval_seconds": 30, "timeout_seconds": 10},
    {"name": "auth_log", "interval_seconds": 15, "timeout_seconds": 10},
    {"name": "network_socket", "interval_seconds": 15, "timeout_seconds": 10},
    {"name": "file_station_transfer", "interval_seconds": 60, "timeout_seconds": 20}
  ]
}
```

## JSONL envelopes

```json
{"type":"heartbeat","nas_host":"lishanmei","observed_at":1777690000}
{"type":"events","source":"auth_log","events":[...]}
{"type":"capability_gap","source":"network_socket","stage":"command_missing","detail":"ss not found"}
{"type":"runner_done","nas_host":"lishanmei","cycles":10,"observed_at":1777690300}
```

## Phase decision

For the current anomaly-improvement phase, the runner remains a documented next-phase MVP. The implemented collectors continue to use SSH transient scripts so the data gaps can be closed first with lower operational risk.
