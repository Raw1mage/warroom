# Event 2026-05-02 — Grafana skills host dashboard refresh

## 需求

- User asked to use Grafana official skills / dashboard-engineering guidance and make the NAS host dashboard look like a more general host monitoring dashboard.

## 範圍

IN:
- Add `https://github.com/grafana/skills` as submodule at `refs/skills`.
- Read Grafana dashboarding / infrastructure / Prometheus / Loki reference material.
- Refactor `grafana/dashboards/warroom-nas-host-health.json` into a standard infrastructure dashboard layout.
- Validate JSON, Loki queries, and Compose config.

OUT:
- No NAS-side node_exporter, SNMP target, container, daemon, or cron.
- No production restart.

## Key Decisions

- Use host monitoring hierarchy: Overview -> CPU/Load -> Memory/Disk -> Network/Services -> Raw Evidence.
- Keep non-row panel count below 20; current dashboard has 13 non-row panels.
- Use Stat/Gauge for current status, Time series for trends, Bar gauge for service availability, and Logs only for drill-down.
- Network traffic panel now uses `sum(rate(... unwrap network_total_*_bytes ...))` and unit `Bps` rather than showing only cumulative byte counters.

## Issues Found

- First validation pass used Loki instant API against the logs panel and produced a false `400 Bad Request` for raw log stream query.
- Re-ran validation with metric panels using `/loki/api/v1/query` and logs panel using `/loki/api/v1/query_range`.

## Verification

- `python3 -m json.tool grafana/dashboards/warroom-nas-host-health.json`: pass
- Dashboard structural check: `panel_count=18`, `non_row_count=13`, required rows present.
- Loki query validation: all 28 dashboard targets pass after substituting `$nas=thesmart`, `$__range=30m`, `$__interval=5m`.
- `docker compose config`: pass
- Architecture Sync: Verified (No doc changes). Existing architecture already documents `host_health_remote` SSH transient payload and network counters; this change is dashboard presentation only.

## Remaining

- Await in-flight dashboard data-gap coding subagent completion before deciding whether additional dashboard query cleanup is needed elsewhere.
