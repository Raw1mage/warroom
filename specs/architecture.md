# Warroom Architecture

## Purpose

Warroom is an enterprise internal monitoring platform. The current POC focuses on Synology NAS shared-folder DLP monitoring for `~Raw1mage`, with Grafana ecosystem components providing observability and dashboards while Warroom owns domain policy, evidence normalization, incident state, AI-assisted judgment, approval posture, audit, and notification boundaries.

## Current POC Boundary

- Primary monitored environment: Synology NAS `rawdb` and the `~Raw1mage` folder scope.
- Primary web-app surfaces: Synology Drive, Synology File Station, public sharing routes, and Synology nginx web ingress.
- Collection posture: metadata-first; no file content inspection by default.
- Response posture: observe-only / dry-run / approval-gated; no automatic destructive response in the POC.
- Deployment posture: local Docker Compose stack for Grafana, Prometheus, Loki, supporting exporters, and local collector utilities.
- Reboot recovery posture: host-level recovery is handled by `scripts/warroom-recover-after-boot.sh` and the optional `deploy/systemd/warroom-compose-recover.service` oneshot unit. The recovery path waits for the Warroom project and provisioned dashboard files before starting Compose, then verifies the Grafana dashboard bind mount inside `warroom-grafana`. It must not remove Grafana/Loki/Prometheus volumes.
- NAS-side posture: least-intrusive SSH read-only payload execution from the Warroom side for all monitored NAS hosts, including `rawdb` and `thesmart`; no persistent NAS-side Warroom agent/exporter/container and no direct syslog dependency unless explicitly approved for an exception.

## Runtime Components

### Grafana

- Service: `grafana` in `docker-compose.yml`.
- Image: `registore.thesmart.cc/warroom/grafana:11.5.2-zh-hant`.
- Role: dashboard and visualization plane.
- Public route: `/warroom` via opencode gateway to port `3000`.
- Provisioned dashboard folder display name: `利善美智能`; this reuses the original Warroom/陽光沙灘 dashboard JSON layout while targeting `thesmart` data streams.
- Alerting posture: Grafana-managed alerting is the first alert-system layer. Provisioned TheSmartAI alert rules live under `grafana/provisioning/alerting/`, send to contact point `warroom-thesmartai-email`, and use the LAN `rawdb:25` MTA relay by default with sender `service@sob.com.tw`. Grafana owns alert state, grouping, deduplication, notification policy, and email delivery; Warroom collector remains the evidence producer.
- Current home dashboard: `warroom-dlp-web-ingress`.
- DLP dashboards include `warroom-dlp-web-ingress`, `warroom-dlp-file-evidence`, `thesmart-recent-file-access-table`, `warroom-dlp-terminal-stream`, `thesmart-anomaly-alert-center`, `warroom-local-overview`, and `warroom-dlp-insights`.
- `thesmart-recent-file-access-table` presents a table of recently accessed files from Loki payload fields only: event time, `file_name`, `actor`, `source_app`, and `source_ip`. Missing users or IPs remain empty rather than being inferred.
- `warroom-dlp-terminal-stream` is management-facing despite the legacy uid: it presents an evidence-category pie chart, a recent important-event table, source/field coverage status, trend by source/action, and a table of actionable collection problems. It must not show raw JSON/log lines as the primary human interface.
- `thesmart-anomaly-alert-center` is an actionable alert summary, not a raw log stream. It presents alert counts, auth-failure and TCP-readiness indicators, signal composition, trend aggregation, AI anomaly rows, auth failure actor/IP rankings, large-download candidates, and capability gaps. TCP socket readiness panels aggregate unwrapped `tcp_established_count` into bounded single-series values for management readability.
- `warroom-dlp-insights` provides Webalizer-style evidence statistics from existing Loki payload fields only: event trends, actor/IP/protocol/file/folder rankings, GeoIP country/region rankings when local MMDB enrichment exists, source channel rankings, and capability-gap rankings.
- Non-responsibilities: Grafana must not own NAS credentials, response approvals, or Warroom policy state.

### Prometheus

- Service: `prometheus` in `docker-compose.yml`.
- Role: scrape local service/exporter health and metrics.
- Current scrape surfaces include `warroom-dlp-file-collector`, Loki, Grafana, Prometheus, Loki canary, and local `snmp-exporter` self metrics.
- Remote NAS infrastructure/file activity is represented through local collector metrics and Loki events emitted by `warroom-dlp-file-collector`; Prometheus does not scrape monitored NAS hosts directly and no NAS-side `node_exporter` port is opened by default.
- Synology SNMP target configuration remains template-only until an approved NAS SNMP path is configured.

### Loki

- Service: `loki` in `docker-compose.yml`.
- Role: normalized DLP event stream and web-ingress evidence storage.
- Receives bounded-label events from one-shot local DLP event collector tooling and the long-running `warroom-dlp-file-collector` service. For `rawdb` and `thesmart`, log and DB evidence is pulled by SSH payload execution and then pushed to Loki by the local collector. Alloy nginx/syslog ingestion remains an explicitly enabled compatibility profile, not the default NAS collection path.

### Non-intrusive SSH payload collection for NAS targets

- Server roots are the preferred onboarding contract: `/tools` is the global reusable adapter/tool layer, while each monitored target owns `/<server>/config` and `/<server>/data`. `/<server>/config/target.json` holds identity and SSH endpoint settings; `/<server>/config/sources.json` holds enabled source settings; `/<server>/data` is local runtime/audit/spool state and is not read directly by Grafana.
- Legacy `config/nas-targets.json` remains a compatibility fallback. Each target `id` is the stable bounded Loki/Grafana selector label `nas_host="<id>"`; `display_name` is human-facing only.
- Collection model: Warroom/Grafana-side collector connects over pre-authenticated SSH, streams a small read-only Python payload over stdin, runs it with `sudo -n python3 -`, and captures JSON stdout.
- Bounded SSH execution-plan runner: documented as a next-phase optimization in `docs/ops/bounded-ssh-execution-plan-runner.md`. If implemented, it must remain tied to a single SSH session with TTL, heartbeat, max cycles, and no NAS-side persistent process.
- Fleet onboarding model: adding a monitored NAS should normally require only one target object plus SSH/sudo validation; generic dashboards discover targets through `$nas` / `label_values(..., nas_host)` and must be preferred over hand-copying dashboards per machine.
- Metrics model: host/service observations collected from SSH payloads are exposed only by the local `warroom-dlp-file-collector` `/metrics` endpoint and/or as Loki events. The standard `host_health_remote` source captures uptime, load, memory, CPU jiffies, disk usage, network interface counters, process count, and service status metadata without running NAS-side node exporters or Promtail agents.
- Log model: approved DSM, SSH, SMB, nginx, HTTPD, rsync, and FTP log paths are tailed by transient payload only during a collection cycle, then normalized locally into bounded Loki payloads.
- SSHD boundary: no reverse tunnel is required for the default pull model. If a future source requires tunneling, it must remain explicitly approved and localhost-only; it must not become the default collection path.

### Synology nginx log exporter

- Service: `synology-nginx-log-exporter` in `docker-compose.yml`.
- Implementation: Grafana Alloy config at `loki/synology-nginx-alloy.template.alloy`.
- Activation: gated behind the `synology-nginx-logs` Compose profile.
- Role: compatibility/experimental path for approved read-only mounted nginx logs and/or Synology nginx syslog on port `1514`; this is not the default `rawdb` or `thesmart` collection model.
- Safety boundary: no raw cookies, session IDs, credentials, or sensitive filenames are committed to repo artifacts.

### SNMP exporter

- Service: `snmp-exporter` in `docker-compose.yml`.
- Role: Prometheus bridge for Synology infrastructure metrics after approved SNMP configuration.
- Current state: local template surface only; no real NAS target or community/auth secret is committed.

### Warroom DLP file collector service

- Service: `warroom-dlp-file-collector` in `docker-compose.yml`.
- Implementation: `services/warroom-dlp-file-collector/app.py`.
- Role: interval collector for `DLP 檔案證據總覽`; emits dashboard-compatible Drive, File Station, and NAS home-scope normalized file evidence into Loki.
- NAS target configuration: server roots are preferred (`rawdb/config`, `thesmart/config`, and future `/<server>/config` folders). Each target has an `id`, optional `display_name`, enabled flag, source list, and per-source settings such as SSH host/user, File Station DB path, home-scope log paths, tail window, limit, and timeout. Legacy `config/nas-targets.json` and `config/nas-targets.example.json` remain compatibility references during migration.
- Default monitored target: `rawdb`, using `host_health_remote`, `file_station_remote`, and `nas_home_log_remote` against explicit SSH endpoint `192.168.100.40` with SSH user `yeatsluo`. Missing or failing remote access emits `capability_gap`; the collector does not silently fall back to fixture or placeholder events.
- Additional monitored target: `thesmart` (display name `TheSmartAI`) points to `nas.wuyang.co` with SSH user `wuyangadmin` for read-only File Station transfer DB and NAS home-scope log metadata collection. Warroom does not deploy containers, persistent agents, exporters, Promtail, or Grafana on this NAS.
- TheSmartAI anomaly sources include structured auth log metadata (`auth_log_remote`) and network socket snapshots (`network_socket_remote`) for login failure/session and connection-spike readiness. The `thesmart-anomaly-alert-center` dashboard is the first-batch POC alert center for auth failures, large downloads, TCP connection spikes, and capability gaps while retaining `nas_host="thesmart"` as the stable Loki selector.
- Source registry: collector source onboarding is centralized in `SOURCE_REGISTRY` inside `services/warroom-dlp-file-collector/app.py`. Each source has an internal `source_key` (for config/dispatch, e.g. `auth_log_remote`), evidence labels (`source_app` / `source_channel`, e.g. `nas_auth` / `auth_log`), an `affected_capability`, and a handler. Capability-gap events use `source_app="collector"` and `source_channel="collector_capability_gap"`, while storing `source_key`, `affected_source_app`, `affected_source_channel`, and `affected_capability` in the payload. Dashboard gap panels must use those registry fields instead of treating internal source keys as evidence channels.
- Coverage status: every configured source emits `action="coverage_status"` with `source_app="collector"`, `source_channel="collector_coverage"`, `covered_source_app`, `covered_source_channel`, `coverage_status`, and numeric `coverage_value` (`1=active`, `0=no_events`, `-1=gap`). The collector also emits `action="field_coverage_status"` for selected payload fields such as `source_ip`, GeoIP fields, paths, file names, sizes, and protocol. These coverage events are dashboard health metadata only; they must not be interpreted as user activity or used to fabricate missing File Station/Drive/nginx/GeoIP evidence.
- Remote NAS adapters require an SSH client in the local collector runtime. In the Docker Compose POC, `app.py`, `tools/`, server roots mounted at `/servers`, `config/`, `geoip/`, and the operator-provided SSH directory are mounted into the local collector container so Warroom can pull metadata from configured NAS targets and write per-server local spool/state.
- Fallback env mode: if `WARROOM_NAS_TARGETS_CONFIG` is unset or missing, legacy environment variables can still define one target, but config file mode is preferred for adding future NAS targets.
- Optional GeoIP enrichment: `WARROOM_GEOIP_MMDB_PATH` points to a locally mounted MaxMind-compatible `.mmdb` file under `./geoip`. When configured, the collector enriches global `source_ip` values with `source_country` and `source_region`; missing or unreadable MMDB files emit `capability_gap` instead of using an external API or guessing.
- Protocol normalization: collector events include `network_protocol` for dashboard display. Current Synology web events normalize to `http`; future FTP/SMB/NFS/WebDAV sources should set the concrete network protocol value directly.
- Metrics: `/metrics` on port `8010`, scraped by Prometheus job `warroom-dlp-file-collector`.
- Safety boundary: metadata-only, no file contents, no NAS-side persistent agent/exporter, no committed credentials, and bounded Loki/Prometheus labels only.

### Collector CLI utilities

- `tools/drive_file_resolver.py`: read-only Drive DB object-id resolver.
- `tools/drive_event_enricher.py`: local SSH stdin runner that streams the resolver to NAS and returns readable normalized Drive evidence.
- `tools/file_station_transfer_adapter.py`: read-only File Station transfer DB adapter for `.DSMFMXFERDB` rows.
- `tools/nas_home_log_adapter.py`: read-only NAS home-scope log adapter that streams over SSH stdin, tails configured log files, and normalizes only lines referencing `/home`, `/homes`, or `/volume*/homes` paths.
- `tools/host_health_adapter.py`: read-only NAS host health adapter that streams over SSH stdin and captures uptime, load, memory, CPU, disk, network interface counters, process count, and service status metadata.
- `tools/auth_log_adapter.py`: read-only auth log adapter that streams over SSH stdin and normalizes authentication success/failure/session metadata with bounded, redacted excerpts.
- `tools/network_socket_adapter.py`: read-only socket metadata adapter that streams over SSH stdin and normalizes TCP connection/listening-port/top-remote-IP summaries.
- `tools/dlp_event_collector.py`: local normalized event collector that dry-runs JSONL or pushes bounded-label streams to Loki.

These utilities are reusable normalization helpers. They are used directly for CLI workflows and indirectly by `warroom-dlp-file-collector` where applicable.

### Warroom AI anomaly scorer service

- Service: `warroom-ai-anomaly-scorer` in `docker-compose.yml`.
- Implementation: `services/warroom-ai-anomaly-scorer/app.py`.
- Role: Phase 2 anomaly signal producer for TheSmartAI. It queries Loki for bounded feature windows, evaluates deterministic rule candidates, optionally calls a direct Ollama HTTP endpoint for triage enrichment, and pushes bounded-label `action="anomaly_alert"` events back to Loki.
- Runtime contract: Grafana Alerting remains responsible for alert lifecycle, grouping, deduplication, and email delivery. The AI scorer must not implement its own notification system and must not perform automatic response actions.
- LLM posture: direct Ollama triage is optional and non-blocking. If Ollama is unavailable, the scorer still emits deterministic anomaly signals and marks `llm_status="unavailable"`. LLM output is triage-only and must not be treated as primary detection, final severity, or response authority.
- Metrics: `/metrics` on port `8020`, scraped by Prometheus job `warroom-ai-anomaly-scorer`.
- Current rules: auth failure spike, active collector capability gap, TCP established spike, and large File Station download ingestion. Download alerting remains ingestion-based until an `observed_at` freshness/cursor guard is implemented.

## Evidence Sources and Data Flow

### Web ingress evidence

```text
Synology nginx access/syslog/log files
  -> Warroom SSH payload adapter by default
  -> optional Grafana Alloy (`synology-nginx-log-exporter`) only when explicitly enabled
  -> Loki labels: job/source_surface/route_family/method/status/transport
  -> Grafana web-ingress dashboards
```

Use nginx for route family, timing, HTTP method/status, and viewer/download/share route candidates. nginx cannot see browser URL fragments such as `#file_id=...`, so it is not sufficient for exact file identity by itself.

### Drive object identity enrichment

```text
browser file_id / Drive permanent_id
  -> `/volume1/@synologydrive/@sync/view-route-db.sqlite`.route_table
  -> view_id
  -> `/volume1/@synologydrive/@sync/view/<view_id>/view-db.sqlite`.node_table
  -> readable file/folder metadata
  -> normalized `webapp_file_preview` / object-ref evidence
```

Drive DB enrichment is read-only and least-intrusive. Current controlled validation decoded Drive web `log-db.sqlite.log_table` action candidates in this environment: `type=24` with `client_type=256` for browser open/preview/view and `type=23` with `client_type=256` for explicit Drive web download. Drive `node_table.access_time` and `user-db.sqlite.recently_access_table` can support correlation, but viewing duration remains estimated.

### File Station transfer evidence

```text
`/volume1/@database/synolog/.DSMFMXFERDB`
  -> `tools/file_station_transfer_adapter.py`
  -> normalized `webapp_file_download` / `webapp_file_export` evidence
  -> Loki push through `warroom-dlp-file-collector` / `tools/dlp_event_collector.py`
```

The adapter opens SQLite databases in read-only mode, discovers candidate tables from schema metadata, and maps explicit download/export-like commands from table `logs` to bounded normalized DLP events. Controlled validation showed File Station pure preview/open did not create a new `/volume1/@database/synolog/.DSMFMXFERDB` table `logs` record during the immediate observation window, so pure preview/open remains a capability gap unless another evidence source is proven.

### NAS home-scope service log evidence

```text
configured NAS log paths in `config/nas-targets.json`
  -> `tools/nas_home_log_adapter.py` over SSH stdin
  -> only lines matching `/home`, `/homes`, or `/volume*/homes`
  -> normalized `file_activity` / `file_read` / `file_write` / `file_delete` / `file_rename` evidence
  -> Loki push through `warroom-dlp-file-collector`
```

The adapter tails existing NAS log files only and does not scan the filesystem or read file contents. It classifies protocol from log source/path text when possible (`smb`, `nfs`, `ftp`, `rsync`, `webdav`, `sftp`) and otherwise emits `nas_log`. If log files are inaccessible or contain no home-scope file evidence in the configured tail window, the collector emits a `capability_gap` for `nas_home_log_remote` instead of manufacturing placeholder events.

### Normalized event ingestion

```text
NAS targets in `config/nas-targets.json`
  -> `warroom-dlp-file-collector` interval loop
  -> per-target metadata source adapters
  -> Loki Push API
  -> Grafana file-evidence dashboard filtered by `nas_host`
```

Loki labels are intentionally bounded to avoid high-cardinality or sensitive values. Raw paths, filenames, usernames, and source IPs remain in event payloads for internal management views, not labels.
GeoIP country/region enrichment is payload-only and local-MMDB-only. The POC does not call external geolocation APIs and does not infer country/region when no MMDB match exists.
The Webalizer-style insights dashboard aggregates only observed Loki evidence and extracted payload fields; it must not present missing user/IP/folder/country values as inferred activity.

## Normalized DLP Actions

Current normalized file/web-app actions include:

- `webapp_file_open`
- `webapp_file_preview`
- `webapp_file_download`
- `webapp_file_export`
- `public_share_page_load`
- `sharing_link_access`
- `file_activity`
- `file_read`
- `file_write`
- `file_delete`
- `file_rename`
- `capability_gap`

Viewing duration is currently an estimate derived from viewer/open timing windows. It must not be presented as exact unless a future application-level close or heartbeat signal is validated.

## Capability and Gap Policy

- Capability detection is preferred over DSM-version-specific behavior routing.
- Missing, blocked, stale, or unknown collection surfaces must be emitted as explicit capability gaps.
- ActiveInsight remains a reference source for infrastructure/login context only; it is not a primary file-level DLP source for this POC because file activity requires a newer DSM capability on the current NAS.
- Future NAS infrastructure metrics should follow the same SSH payload pull posture unless a host-specific persistent exporter exception is explicitly approved.

## Security and Privacy Constraints

- Do not collect or commit file contents.
- Do not commit secrets, private keys, passwords, LINE tokens, cookies, session tokens, or raw credential-bearing URLs.
- Keep NAS DB/log access read-only and use SSH stdin payload execution over persistent NAS-side helper installation.
- Do not rely on direct syslog or direct Prometheus scrape ports for monitored NAS hosts by default, even when the NAS is reachable over the LAN.
- Keep metrics labels bounded and low-cardinality; never use raw file paths, usernames, IP addresses, session IDs, permanent links, or arbitrary error text as Prometheus labels.
- Protective or destructive response actions require explicit human approval and are outside the current POC execution path.

## Current Validation Signals

- Docker Compose config validates for default and `synology-nginx-logs` profile modes.
- Live Synology nginx `/drive/` page-load evidence reached Loki with route-family labels.
- Drive DB read-only resolver produced readable metadata for a controlled file id and decoded controlled open/preview/download action candidates.
- File Station transfer adapter and DLP event collector compile; explicit File Station download is observable through `/volume1/@database/synolog/.DSMFMXFERDB` table `logs`, while pure preview/open is currently a capability gap.
- NAS home-scope log adapter compiles and is wired into `rawdb` target config as `nas_home_log_remote`; current dry-run emits rawdb capability gaps when remote SSH/log access is unavailable, with no fixture or placeholder fallback.
- `warroom-dlp-file-collector` builds and runs under Docker Compose.
- Dashboard queries now separate observed DLP evidence from collector coverage metadata. `warroom-dlp-web-ingress` counts actual non-collector evidence and shows `collector_coverage` status for configured but quiet/gapped sources instead of presenting missing File Station/Drive/nginx evidence as No data activity panels.
- `thesmart-recent-file-access-table` and the matching panel in `warroom-dlp-file-evidence` validate as Grafana JSON and use Loki payload extraction to show recent file access rows without grouping on high-cardinality labels.
- `warroom-dlp-insights` JSON validates and is linked from the other Warroom dashboards. Its queries do not reference fixture, placeholder, or synthetic streams.
- Prometheus target `warroom-dlp-file-collector:8010` is up and exposes `warroom_dlp_file_collector_events_pushed_total`.
- GeoIP helper validation maps MaxMind-style records into `source_country/source_region`, and dashboard line rendering shows protocol as a raw network value (`http`) followed by country/region or `-`.
- Grafana is publicly reachable through the `/warroom` route and serves Warroom dashboards with Traditional Chinese dashboard/image customization, including the DB-backed `DLP 檔案證據總覽` dashboard.

## Open Architecture Items

- Phase 2 AI detection is tracked in `plans/20260502_phase2_ai_detection/`: AI scoring is a proposed signal-producer module, not the alert lifecycle. It should extract features from Loki/Prometheus, apply deterministic rules plus rolling baselines, optionally add Isolation Forest after enough history, and emit bounded-label `action="anomaly_alert"` events back to Loki. Grafana Alerting remains responsible for alert state, grouping, deduplication, email delivery, and future LINE webhook routing. LLMs may assist triage summaries only; they must not be the primary detector or automatic response authority.
