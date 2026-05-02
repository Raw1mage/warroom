# Event Log: Warroom Planning Session

Date: 2026-04-27
Session: Warroom enterprise monitoring platform planning
Project path: `/home/pkcs12/projects/warroom`

## Requirement

Create planning artifacts for a new project named **Warroom**.

Warroom is an enterprise internal monitoring platform for online services, devices, computers, and other internal infrastructure. The first POC is **Synology NAS shared-folder DLP monitoring** for the folder `~Raw1mage`.

The long-term architecture uses Grafana ecosystem components for dashboarding, visualization, and alert observability, while Warroom owns the domain control plane: policy, incident state, AI alert judgment, approval, audit, and response recommendations.

## Scope In

- Establish project planning folder under `/home/pkcs12/projects/warroom`.
- Capture Warroom platform vision.
- Define first POC as Synology NAS DLP monitoring.
- Document SSH/sudo access assumption without performing live SSH during planning.
- Capture DSM-version-independent architecture using capability detection.
- Capture first monitored folder: `~Raw1mage`.
- Define Grafana Docker deployment shape.
- Define LINE Bot as alert delivery integration.
- Clarify that Warroom's core contribution is AI-assisted alert judgment, not basic alert routing.
- Produce implementation architecture, implementation steps, and gap questions.

## Scope Out

- No implementation started.
- No SSH to `rawdb` during planning.
- No secrets, NAS credentials, LINE tokens, sudo output, or raw sensitive logs written into plan files.
- No destructive response automation in POC planning.
- No DSM-version-specific behavior assumption.

## Key Decisions

1. Project name: `warroom`.
2. First POC: Synology NAS shared-folder DLP monitoring.
3. Initial monitored folder: `~Raw1mage`.
4. NAS access assumption: SSH + sudo are available; target hint is `yeatsluo@rawdb`.
5. DSM version is not a design dependency; collector must use capability detection and explicit collection-gap reporting.
6. Grafana is used as dashboard/observability plane, deployed through Docker.
7. Warroom is the domain control plane for policy, incident, AI judgment, approval, audit, and response.
8. LINE Bot is mature notification integration, not the core academic/product contribution.
9. AI Alert Judge is the main contribution: context-aware severity refinement, multi-signal correlation, noise reduction, explainability, and response recommendation.
10. POC response mode is observe-only/dry-run/approval-gated by default.
11. File content inspection is not performed by default; POC remains metadata-first unless explicitly changed.

## Artifacts Created or Updated

Plan root:

- `/home/pkcs12/projects/warroom/plans/20260427_warroom_monitoring_platform/`

Planning files:

- `proposal.md`
- `requirements.md`
- `architecture-options.md`
- `open-questions.md`
- `environment.md`
- `capability-detection.md`
- `ai-alerting.md`
- `alert-delivery.md`
- `docker-deployment.md`
- `implementation-architecture.md`
- `implementation-steps.md`
- `gap-questions.md`
- `tasks.md`

This event log:

- `/home/pkcs12/projects/warroom/docs/events/event_20260427_warroom_planning_session.md`

## Implementation Architecture Summary

Recommended POC topology:

```text
Synology NAS rawdb / ~Raw1mage
  -> warroom-synology-collector
  -> Loki / Prometheus / Warroom API
  -> rule engine + AI Alert Judge
  -> LINE Bot notify-only + Grafana dashboard
```

Core services:

- `warroom-grafana`: dashboard panels and alert visualization.
- `warroom-prometheus`: collector health and rule metrics.
- `warroom-loki`: normalized DLP event and diagnostic log stream.
- `warroom-api`: policy, incidents, approvals, audit, and domain state.
- `warroom-synology-collector`: SSH/sudo capability detection, log collection, snapshot diff, normalization.
- `warroom-ai-alert-judge`: severity refinement, explanation, grouping, response recommendation.
- `warroom-linebot`: notify-only POC delivery.

## Implementation Step Summary

Planned implementation phases:

1. Decide minimum unresolved product/engineering choices.
2. Create repository and Docker skeleton.
3. Define Warroom domain data model.
4. Implement Synology capability detection.
5. Implement metadata snapshot diff collector.
6. Add log/session collectors where available.
7. Emit events to Loki and metrics to Prometheus.
8. Build deterministic rule engine MVP.
9. Add AI Alert Judge MVP.
10. Add LINE Bot notify-only delivery.
11. Build Grafana dashboards.
12. Validate with synthetic/scrubbed POC scenarios.
13. Harden before real use.

## Remaining Decisions / Discussion Gates

Tracked in `gap-questions.md` and `tasks.md`:

1. MVP implementation language/runtime.
2. First mandatory demo anomaly scenarios.
3. Warroom API database choice, with PostgreSQL recommended.
4. Whether Warroom API should expose a Grafana JSON datasource later.
5. Whether LINE Bot remains notify-only or eventually supports acknowledgement/approval actions.
6. Whether a NAS-side lightweight agent is acceptable after remote-only POC.

Implementation priority clarified by user:

1. Deploy the Grafana runtime environment first and produce a basic local dashboard POC.
2. Build Synology NAS node_exporter monitoring and Grafana dashboard next.
3. After backend data collection is working, start AI expansion development.

## Validation / Evidence

- Planning artifacts were written under the Warroom project path.
- No implementation, SSH access, Docker runtime, or secret-dependent validation was performed.
- POC constraints were documented in planning artifacts:
  - metadata-first collection
  - capability detection over DSM version dependency
  - observe-only/dry-run response
  - LINE notify-only
  - no secrets in planning files

### Plan Validation — 2026-04-27

Result: conditionally valid for planning/design discussion; not yet execution-ready.

Checks performed:

- Scope alignment: `proposal.md`, `requirements.md`, `implementation-architecture.md`, and `tasks.md` consistently identify the first POC as Synology NAS shared-folder DLP monitoring for `rawdb / ~Raw1mage`.
- Safety alignment: metadata-first collection, no automatic destructive response, no DSM-version routing, no secrets in plan files, and LINE notify-only delivery are consistently documented.
- Architecture alignment: collector, API/control plane, AI Alert Judge, LINE Bot, Grafana, Loki, Prometheus, and PostgreSQL recommendation are coherent across architecture/deployment documents.
- Decision gates: `tasks.md` correctly keeps unresolved implementation choices as `[?]` items before build work.
- Execution readiness gaps: formal data schema, test vectors, validation plan, and long-lived architecture file are not yet present; these are required before implementation begins.

Blocking items before implementation:

1. Resolve remaining `tasks.md` decision items 4.2, 4.3, and 4.5.
2. Produce formal data schema and test vectors (`tasks.md` 4.7).
3. Produce concrete validation plan (`tasks.md` 4.8).
4. Create or sync long-lived architecture documentation once the implementation architecture is finalized.

### Implementation Priority Update — 2026-04-27

User clarified implementation order: local Grafana dashboard POC first, Synology NAS node_exporter/dashboard second, backend data collection third, AI expansion after evidence collection exists.

Plan artifacts updated:

- `plans/20260427_warroom_monitoring_platform/implementation-steps.md`
- `plans/20260427_warroom_monitoring_platform/docker-deployment.md`
- `plans/20260427_warroom_monitoring_platform/tasks.md`

Validation impact:

- The plan is now more execution-oriented for the observability layer.
- A local dashboard POC can begin before full domain data schema completion if it uses placeholder/synthetic metrics and does not imply DLP backend completion.
- Synology node_exporter deployment remains gated by NAS deployment constraints and must fail fast with an explicit capability/blocker report if direct exporter deployment is not viable.
- AI expansion remains downstream of backend evidence collection or repeatable synthetic fixtures.

### Gateway Route Registration — 2026-04-27

User requested the initial Grafana frontend be registered in the opencode gateway route registry as `/warroom`.

Changes:

- Added `warroom` entry to `/home/pkcs12/.config/web_registry.json` with `publicBasePath: /warroom`, `host: 127.0.0.1`, and `primaryPort: 3000`.
- Published `/warroom -> 127.0.0.1:3000` through `/run/opencode-gateway/ctl.sock` with auth enabled.
- Added `webctl.sh` for the Warroom Docker Compose stack so managed route controls can start/stop/status the local POC.
- Configured Grafana sub-path settings via `GF_SERVER_ROOT_URL` and `GF_SERVER_SERVE_FROM_SUB_PATH` so assets and redirects work behind `/warroom`.

Validation:

- `jq` validated the `warroom` registry entry.
- `docker compose -f /home/pkcs12/projects/warroom/docker-compose.yml config` completed successfully.
- Gateway route list includes `/warroom 127.0.0.1 3000 1000 1`.

### IDEF0 Diagram Artifact — 2026-04-27

User requested an IDEF0 model and SVG diagram from the current plan files.

Initial artifacts created:

- `plans/20260427_warroom_monitoring_platform/warroom_a0_idef0.json`
- `plans/20260427_warroom_monitoring_platform/warroom_a0_idef0.svg`

Correction:

- User noted the first SVG was manually drawn rather than generated by drawmiat renderer.
- Recreated a renderer-compatible payload and generated the SVG through drawmiat.

A1 decomposition update:

- User asked whether A1 should be decomposed instead of stopping at A0.
- Added A1 decomposition for the observability deployment slice.

Drawmiat artifacts:

- `plans/20260427_warroom_monitoring_platform/warroom_a0_idef0.drawmiat.json`
- `plans/20260427_warroom_monitoring_platform/drawmiat/diagram_A0.svg`
- `plans/20260427_warroom_monitoring_platform/drawmiat/diagram_A1.svg`

Model summary:

- A0: Warroom Synology NAS DLP POC A0.
- A1: Deploy Observability.
- A11: Configure Runtime.
- A12: Provision Datasources.
- A13: Provision Dashboards.
- A14: Publish Gateway.
- A15: Validate Access.
- A2: Monitor Infrastructure.
- A3: Collect Evidence.
- A4: Normalize Evidence.
- A5: Judge Anomalies.
- A6: Notify Operators.

Validation:

- `drawmiat_validate_diagram` passed for the updated A0 payload: 6 top-level activities, 16 top-level arrows, `node_reference='A0'`.
- `drawmiat_generate_diagram` generated both `drawmiat/diagram_A0.svg` and `drawmiat/diagram_A1.svg` successfully.

### Build Planning Decisions Closed — 2026-04-28

User accepted the recommended implementation defaults to unblock build planning.

Decisions:

- MVP runtime: Python/FastAPI for Warroom POC services, with Python collector and AI Alert Judge first.
- Mandatory demo anomaly scenarios: mass delete/rename/modify burst, failed-login burst followed by success, and permission broadening.
- Database: PostgreSQL for Warroom API state.
- Collection strategy: metadata-first snapshot diff plus logs/session collection; no DSM-version-primary routing.
- Content inspection: out of scope for the POC.
- LINE Bot: notify-only; no acknowledgement, approval, or destructive execution path in POC.

Artifacts updated:

- `plans/20260427_warroom_monitoring_platform/tasks.md`
- `plans/20260427_warroom_monitoring_platform/data-schema.md`
- `plans/20260427_warroom_monitoring_platform/test-vectors.json`
- `plans/20260427_warroom_monitoring_platform/validation-plan.md`

Validation impact:

- Build-planning decision gates 4.2, 4.3, 4.5, 4.7, and 4.8 are now closed in `tasks.md`.
- Formal POC entity contracts are documented for FastAPI/Pydantic and PostgreSQL implementation.
- Test vectors now cover the three mandatory demo scenarios plus capability-gap and benign-change safety cases.
- Validation plan records static, schema/fixture, rule engine, AI judge, LINE notify-only, observability, safety, and audit validation layers.
- Architecture Sync: Verified (No doc changes) because this update narrows POC implementation choices and adds execution contracts without changing the existing module boundaries documented in `implementation-architecture.md`.

### Local Overview Dashboard Placeholder — 2026-04-28

Scope:

- Completed `tasks.md` item 5.2: provision local overview dashboard with synthetic or placeholder metrics/logs.

Changes:

- Added `services/warroom-placeholder/` Python service.
- The placeholder exposes `/metrics` on port 8000 using Prometheus text format.
- The placeholder emits synthetic DLP-like events for mandatory demo scenarios and capability-gap evidence.
- The placeholder pushes synthetic log events to Loki through `LOKI_PUSH_URL` and also prints safe JSON logs to stdout.
- Added `warroom-placeholder` to `docker-compose.yml`.
- Added Prometheus scrape target `warroom-placeholder:8000`.
- Updated `grafana/dashboards/warroom-local-overview.json` to show placeholder health, synthetic event rate, synthetic capability gaps/incidents, and Loki synthetic logs.

Safety notes:

- No real NAS access was added.
- No file content inspection was added.
- No secrets, LINE tokens, private paths, or credentials were introduced.
- Synthetic host label remains non-production (`synthetic-rawdb`) for placeholder output.
- No fallback behavior was added; missing Loki push increments a visible failure metric.

Validation:

- `docker compose -f docker-compose.yml config` passed.
- `jq empty grafana/dashboards/warroom-local-overview.json` passed.
- `python3 -m py_compile services/warroom-placeholder/app.py` passed.
- Architecture Sync: Verified (No doc changes) because this change implements the already-planned observability placeholder slice without changing module boundaries.

### MVP Scope Narrowed to NAS Read/Download Sensing — 2026-04-28

User clarified the next step should proceed incrementally: first make Warroom able to sense that files inside the specified NAS folder are opened online through browser, read, or downloaded.

Decision:

- First real DLP capability is browser-open/read/download sensing for `~Raw1mage`.
- Browser-based online open/preview/view behavior counts as data leakage, even without explicit download.
- Broader scenarios such as delete/rename/modify bursts, permission broadening, failed-login correlation, AI judgment, LINE delivery, and response automation are deferred until read/download evidence collection is proven.
- Snapshot diff alone is not treated as sufficient evidence for read/download, because reads are access events rather than filesystem metadata changes.
- Capability detection must identify whether NAS file-service logs or access-audit channels can prove read/download events; if not, Warroom must produce an explicit capability gap.
- User selected Synology Drive access records as the first evidence source/protocol to test for browser-open/read/download sensing.
- User provided the Synology Drive browser entrypoint `https://sob.com.tw/drive/`.
- User can currently reach the user home through that URL; the POC target is now described as `Raw1mage @ 192.168.100.40:~/`.
- User clarified that two Synology applications can export files outward: Synology Drive and Synology File Station.
- Warroom must treat both Drive and File Station as monitored file-egress surfaces; Drive remains the first validation path, while File Station is included in capability detection and event normalization scope.
- The assistant did not fetch or crawl the URL; it is recorded only as environment/context for later controlled validation.

Artifacts updated:

- `plans/20260427_warroom_monitoring_platform/requirements.md`
- `plans/20260427_warroom_monitoring_platform/implementation-steps.md`
- `plans/20260427_warroom_monitoring_platform/gap-questions.md`
- `plans/20260427_warroom_monitoring_platform/tasks.md`

Next discussion focus:

- Verify whether Synology Drive access records expose browser-open/preview/view events with enough detail for `~Raw1mage`.
- Verify whether Synology File Station exposes browser-open/export/download records with enough detail for `~Raw1mage`.
- Use the Synology Drive web entrypoint as the controlled browser-open test path when implementation/validation begins.
- Define the minimum normalized `file_browser_open` / `file_read` / `file_download` event fields.
- Define a safe controlled test for browser-opening/viewing a test file under `~Raw1mage` without storing secrets or raw sensitive logs in the repo.

### MVP Refocused to Web App Access Control — 2026-04-28

User clarified that the POC should keep focus on web app access control rather than SMB read/write detection.

Decision:

- MVP primary surfaces are Synology Drive and Synology File Station.
- The control-plane question is who can access `Raw1mage` through these web apps and who actually opens/previews/downloads/exports files.
- Browser open/preview remains data leakage for this POC.
- SMB observations remain useful as secondary context, but SMB deep read/write detection is not the MVP focus.

SMB observation summary from live probing:

- Active SMB sessions for `Raw1mage` were visible via `smbstatus`.
- SMB tree scan was visible as session/share activity, but did not create durable `.SMBXFERDB` transfer rows during the observation window.
- SMB write/delete probing showed a durable `.SMBXFERDB` `delete` event and a live open-handle burst, but no confirmed durable write/upload event yet.
- Therefore SMB requires separate audit design if it becomes a first-class objective later.

### Plan-First Gate for Controlled Web App Validation — 2026-04-28

User instructed that the next step must be planned before execution.

Plan artifact created:

- `plans/20260427_warroom_monitoring_platform/webapp-access-control-validation-plan.md`

Plan summary:

- Phase V1: baseline safe aggregate snapshots.
- Phase V2: Synology Drive browser open/preview validation.
- Phase V3: Synology Drive download/export validation.
- Phase V4: File Station download/export validation.
- Phase V5: File Station browser preview/open validation.

Stop gate:

- No controlled validation should run until user explicitly approves the plan.
- Validation must not read file contents, store raw sensitive rows, expose credentials/tokens/session IDs, or crawl the browser URLs automatically.

### Synology nginx Promoted to First-Class Evidence Source — 2026-04-28

User pointed out that Synology internal nginx is the web traffic gateway and is worth monitoring.

Decision:

- Treat Synology nginx as a first-class `web_ingress_nginx` evidence surface alongside Drive/File Station application DBs.
- Use nginx/access-log capability detection to close the public sharing link access gap where Drive DBs do not record page loads.
- Monitor `/drive/`, `/file/`, `/sharing/`, app portal routes, reverse proxy behavior, and generated-link port mismatches.
- Do not change NAS nginx configuration yet; first document capability requirements and validation plan.

Artifacts updated:

- `plans/20260427_warroom_monitoring_platform/capability-detection.md`
- `plans/20260427_warroom_monitoring_platform/implementation-steps.md`
- `plans/20260427_warroom_monitoring_platform/webapp-access-control-validation-plan.md`
- `plans/20260427_warroom_monitoring_platform/tasks.md`

### Synology Observability Entry Points Refined — 2026-04-28

User clarified the next research direction: first ask community / public documentation whether Synology already has usable exporter or monitoring paths, and only build a custom exporter if no suitable existing path exists. User also requested keeping any future system inspection phrased as defensive observability/audit monitoring to avoid unnecessary cyber-safety escalation.

Public documentation findings:

- Synology DSM officially supports SNMP under Terminal & SNMP, including SNMPv1/v2c/v3 and MIB-based monitoring for system, drive, and RAID volume status.
- Synology Log Center supports syslog send/receive, archival, search, and filtering, making it a preferred official audit/log pipeline before internal scraping.
- Prometheus `snmp_exporter` is the most compatible first Prometheus bridge for Synology infrastructure metrics.
- Prometheus `node_exporter` remains optional; on Synology/Container Manager it requires explicit host-visibility validation and should not silently replace SNMP or Log Center if blocked.
- File Station, Drive, and web-ingress evidence still require controlled validation for per-file/per-user DLP semantics.

Artifact updated:

- `plans/20260427_warroom_monitoring_platform/capability-detection.md`

Safety boundary:

- Use observability/audit wording: Synology SNMP, Log Center/syslog, Drive/File Station activity logs, Prometheus exporters.
- Avoid wording or actions around privilege bypass, hidden-log extraction, credential discovery, stealth monitoring, or unauthorized access.

Architecture Sync: Verified (No doc changes) because this update refines capability-detection priority and evidence sourcing without changing the existing Warroom module boundaries.

### Synology Observability Capability Probe Checklist — 2026-04-28

User requested autorun continuation. The session stayed in planning/documentation mode and did not perform live NAS SSH, DSM setting changes, package installation, or browser/file action validation.

Artifact created:

- `plans/20260427_warroom_monitoring_platform/synology-observability-capability-probe.md`

Tasks updated:

- `5.3` marked complete for producing the capability probe checklist.
- `5.4` changed from node-exporter-first to SNMP / `snmp_exporter` scrape template after approved SNMP path confirmation.
- `5.5` changed to Synology infrastructure dashboard for SNMP/exporter metrics and capability gaps.
- Subsequent Drive/File Station/nginx implementation items were renumbered to preserve unique task IDs.

Probe scope:

- P1: public/official monitoring surface — Synology SNMP, MIB/OID mapping, `snmp_exporter` bridge.
- P2: existing Prometheus/exporter surface — already-running exporter, `node_exporter` viability, Synology-specific exporter acceptability.
- P3: official log/audit surface — Log Center/syslog, login/session/service event coverage, file-service event coverage.
- P4: web app DLP evidence surface — File Station, Drive, and nginx/web-ingress evidence.
- P5: custom collector decision — only after explicit gaps are recorded.

Safety boundary:

- All probe language remains defensive observability/audit monitoring.
- Stop gates are documented before DSM setting changes, NAS installs, controlled browser/file actions, raw log copying, or privilege escalation beyond approved monitoring/admin scope.

Architecture Sync: Verified (No doc changes) because this update adds execution-ready probe documentation and task ordering without changing Warroom service/module boundaries.

### Synology SNMP Exporter Template — 2026-04-28

Scope:

- Completed `tasks.md` item 5.4 as a safe local template slice.
- Added a Warroom-managed `snmp-exporter` service to Docker Compose.
- Added Prometheus scraping for the exporter service's own `/metrics` endpoint only.
- Added an inactive Synology SNMP scrape template with placeholder target/auth values.

Files changed:

- `docker-compose.yml`
- `prometheus/prometheus.yml`
- `prometheus/synology-snmp-scrape.template.yml`
- `plans/20260427_warroom_monitoring_platform/tasks.md`

Safety notes:

- No real NAS host, IP, community string, SNMPv3 username/password, or DSM credential was added.
- The Synology SNMP scrape block is not mounted or included by Prometheus; it is a copy-in template for after approved SNMP path confirmation.
- `snmp-exporter` is exposed only on the Docker Compose internal network, not published to the host.
- No live NAS connection, DSM setting change, package install, or controlled file/browser action was performed.

Validation:

- `docker compose -f docker-compose.yml config` passed.
- Architecture Sync: Verified (No doc changes) because this adds observability plumbing/template only and does not change Warroom service boundaries.

### Synology nginx Log Exporter Template — 2026-04-28

User pointed out that the critical nginx log exporter was missing from the exporter/template slice. The plan was corrected to treat nginx web-ingress logs as a first-class Loki evidence pipeline, not just a later adapter task.

Scope:

- Completed new `tasks.md` item 5.5: add Synology nginx log exporter template.
- Added a `synology-nginx-log-exporter` Docker Compose service using Grafana Alloy.
- The service is gated behind the `synology-nginx-logs` profile, so it is inactive by default.
- Added `loki/synology-nginx-alloy.template.alloy` to tail approved mounted nginx log files and forward them to Loki with `source_surface="web_ingress_nginx"` labels.

Files changed:

- `docker-compose.yml`
- `loki/synology-nginx-alloy.template.alloy`
- `plans/20260427_warroom_monitoring_platform/tasks.md`

Safety notes:

- No real Synology nginx log path, raw log row, credential, session ID, cookie, IP, or sensitive file path was committed.
- The Alloy pipeline is conservative and does not parse request fields until controlled validation confirms actual Synology nginx log format.
- The log exporter requires an explicit profile and approved read-only log mount before it can run.

Validation:

- `docker compose -f docker-compose.yml config` passed with the default profile, where the nginx log exporter remains inactive.
- `docker compose -f docker-compose.yml --profile synology-nginx-logs config` passed with the profile-enabled service included.
- Architecture Sync: Verified (No doc changes) because this adds a profile-gated evidence ingestion template within the existing Loki observability boundary.

### First DLP Web-Ingress Monitor Live Validation — 2026-04-28

User approved necessary NAS configuration/log-pipeline adjustments for connecting real information flow, including logs. Synology nginx skill guidance was applied: persistent Synology nginx include paths were preferred over non-persistent generated config edits.

Local monitor additions:

- Added `synology-nginx-logs/sanitized-web-ingress.log` with safe synthetic Drive/File/Sharing routes.
- Added `grafana/dashboards/warroom-dlp-web-ingress.json` for Loki panels grouped by `route_family` and HTTP status.
- Extended `loki/synology-nginx-alloy.template.alloy` with low-sensitivity route/status label extraction and syslog TCP/UDP receivers on port `1514`.
- Published `1514/tcp` and `1514/udp` only when the `synology-nginx-logs` profile is enabled.

NAS configuration changes:

- Added persistent nginx access log config under `/etc/nginx/conf.d/http.warroom-access-log.conf`.
- Added location-level access logging for Synology Drive/File Station/Sharing app-portal locations where global `access_log off` otherwise suppressed logs.
- Added nginx syslog forwarding to Warroom Alloy at `192.168.100.10:1514` with tag `warroom_nginx_access`.
- `nginx -t` passed before reload; DSM's existing duplicate server-name warnings were observed but did not block reload.

Validation evidence:

- Sanitized local fixture reached Loki with `route_family=drive`, `route_family=file`, and `route_family=sharing` labels.
- Live `https://sob.com.tw/drive/` request produced a NAS nginx access log row.
- Live NAS nginx syslog reached Warroom Loki with labels: `job="synology-nginx"`, `source_surface="web_ingress_nginx"`, `transport="syslog_udp"`, `route_family="drive"`, `method="GET"`, `status="200"`.

Safety notes:

- No raw NAS log line, cookie, session ID, credential, or sensitive filename was copied into repo artifacts.
- Current live validation proves `/drive/` page-load web-ingress evidence only; Drive preview/download, File Station, sharing, and fsdownload behavior still require controlled validation.
- Architecture Sync: Verified (No doc changes) because this completes the first live evidence pipeline inside the already-planned Loki web-ingress boundary.

### ActiveInsight Reference Snapshot — 2026-04-28

User requested copying the Synology ActiveInsight source/config locally for slower source-code analysis, especially to investigate possible toggles/switches controlling exporter behavior.

Artifacts added:

- `refs/activeinsight/README.md`
- `refs/activeinsight/var/packages/ActiveInsight/target/client-python/`
- `refs/activeinsight/var/packages/ActiveInsight/target/configs/prometheus.yml`
- `refs/activeinsight/usr/local/packages/@appdata/ActiveInsight/collectors_all/current/`

Notes:

- Snapshot was copied read-only from NAS paths; no NAS runtime setting was changed for this step.
- Runtime TSDB data, raw logs, sessions, cookies, credentials, and `.pyc` cache files were excluded/removed.
- Local grep for secret-like strings found only library helper names/comments (`basic_auth_handler`, `token` variable names, README safety text), not concrete credentials.
- `tasks.md` item 5.7 now records the ActiveInsight refs snapshot as completed.

Architecture Sync: Verified (No doc changes) because this adds reference material for local analysis without changing Warroom runtime boundaries.

### ActiveInsight UI Capability Boundary — 2026-04-28

User researched `insight.synology.com` and confirmed the NAS appears in the official ActiveInsight UI with complete monitoring information. This confirms that Synology's local metrics collection and upload pipeline is functioning.

Key finding:

- ActiveInsight activity monitoring mainly covers login activity and file activity.
- File activity monitoring is not functional on the current NAS because it requires a newer DSM version.
- Therefore ActiveInsight can currently contribute abnormal login/IP alerting and infrastructure metrics, but should not be treated as a primary file-level DLP evidence source for this POC.

Decision:

- Keep ActiveInsight in the plan as infrastructure/login anomaly context.
- Keep file-level DLP evidence on the Warroom-controlled paths: Synology nginx web-ingress logs, Drive/File Station databases, and File Station transfer logs.
- Record any future DSM upgrade that enables ActiveInsight file activity as a new detected capability, not an assumed baseline.

Artifact updated:

- `plans/20260427_warroom_monitoring_platform/capability-detection.md`

Architecture Sync: Verified (No doc changes) because this clarifies a source capability boundary without changing Warroom runtime boundaries.

### Warroom Custom C Exporter Direction — 2026-04-28

User decided to abandon ActiveInsight as the primary runtime architecture because it has limited usable functionality on the current DSM version and is inconvenient for Warroom's needs. The preferred direction is a custom, high-efficiency C-language node exporter that exposes only the metrics and capability signals Warroom needs.

Decision:

- ActiveInsight remains a reference source under `refs/activeinsight`, not a mainline dependency.
- Warroom should design a custom C exporter for NAS infrastructure metrics and capability-gap reporting.
- File-level DLP evidence should remain in the nginx/Loki and Drive/File Station DB collection paths, not in the C metrics exporter.

Rationale:

- ActiveInsight file activity is unavailable on the current DSM without a newer DSM version.
- ActiveInsight's exporter returns sparse interval-based metrics and can emit empty responses between due collector windows.
- Warroom needs predictable scrape behavior with last-known values and explicit capability-gap metrics.

Artifact updates:

- `plans/20260427_warroom_monitoring_platform/capability-detection.md`
- `plans/20260427_warroom_monitoring_platform/tasks.md`

Architecture Sync: Verified (No doc changes) because this changes implementation priority inside the already-planned exporter/metrics boundary, without changing the broader Warroom module boundaries.

### File-Level DLP Precision Requirement — 2026-04-28

User clarified that the DLP POC must move beyond route-level activity detection. Required file-level questions are:

- Which exact file was opened or previewed?
- How long was the file likely viewed?
- Was the file downloaded or exported?
- Was the file shared or accessed through a public sharing route?

Key technical boundary:

- nginx logs are sufficient for web-app activity timing and route/action candidates.
- nginx logs are not sufficient for exact file identity when identifiers live in browser fragments, e.g. `#file_id=...`, because fragments are not sent to the server.
- Exact file identity requires correlation with Synology Drive/File Station databases and transfer/share metadata.

Artifact updates:

- Added `plans/20260427_warroom_monitoring_platform/file-level-dlp-correlation.md`.
- Updated `plans/20260427_warroom_monitoring_platform/data-schema.md` with web-app actions, file object id, estimated viewing duration fields, and correlation refs.
- Updated `plans/20260427_warroom_monitoring_platform/tasks.md` item 5.12 as completed design work for file-level DLP correlation.

Decision:

- Treat nginx as the timing/action-candidate source.
- Treat Drive DB / File Station transfer DB / sharing metadata as object identity and high-confidence action sources.
- Viewing duration is an estimate unless a future close/heartbeat signal is proven.

Architecture Sync: Verified (No doc changes) because this refines the DLP evidence model inside the existing nginx + Drive/File Station collector boundary.

### Drive DB Mapping Data-Flow Probe — 2026-04-28

User asked whether Warroom needs to actively read the Drive DB and whether that data flow has already been connected.

Current state:

- nginx/syslog/Loki flow is connected and live.
- Drive DB flow is not yet an automated collector pipeline.
- A read-only Drive DB lookup path has now been validated for the controlled `file_id=853993314635001175` case.

Validated mapping:

- `view-route-db.sqlite.route_table.permanent_id = 853993314635001175` resolves to `view_id = 1`.
- `view/1/view-db.sqlite.node_table.permanent_id = 853993314635001175` resolves to a Drive node record with safe metadata fields.
- `node_table.access_time` did not reflect the recent viewer action in this probe.
- `user-db.sqlite.recently_access_table` did not return a row for this controlled file id during the probe.
- `log-db.sqlite.log_table` showed recent type `24` rows for `view_id=1`, but action semantics still require decoding.

Decision:

- Warroom must actively read Drive DBs for object identity enrichment.
- For MVP, nginx/Loki remains the event timing/action-candidate stream; Drive DB is queried on demand or cached periodically for file identity mapping.
- Drive DB polling for access events should not be treated as complete until `log_table.type` semantics and `recently_access_table` behavior are validated.

Artifact updated:

- `plans/20260427_warroom_monitoring_platform/file-level-dlp-correlation.md`

Architecture Sync: Verified (No doc changes) because this clarifies data-flow readiness inside the planned file-level correlation boundary.

### Human-Readable Drive Metadata Resolver — 2026-04-28

User clarified that Warroom is an administrator-facing system and must present human-readable file/folder metadata for DLP investigations. Hash-only records are insufficient for operational use.

Technical assessment:

- It is technically possible to restore human-readable Drive file/folder metadata from the Drive DBs.
- Controlled `file_id=853993314635001175` resolved to a readable Drive path through parent-chain reconstruction.
- Mapping chain: `view-route-db.sqlite.route_table` -> `view_id` -> `view/<view_id>/view-db.sqlite.node_table` -> recursive `parent_id` chain.

Implementation:

- Added `tools/drive_file_resolver.py`, a read-only CLI helper that resolves a Drive `permanent_id`/`file_id` to readable metadata.
- Added `fixtures/dlp-events/drive-file-preview-readable.json`, the first readable normalized `webapp_file_preview` fixture.
- Updated `data-schema.md` so internal Warroom/Grafana management views may store and show `file_name`, `folder_path`, and `display_path`; hashes remain for joins/external summaries.

Validation:

- `tools/drive_file_resolver.py` was executed against NAS Drive DBs via sudo read-only access.
- It resolved the controlled object to readable metadata including file name, folder path, display path, Drive `view_id`, `node_id`, and parent chain.
- `python3 -m py_compile tools/drive_file_resolver.py` passed.
- `jq empty fixtures/dlp-events/drive-file-preview-readable.json` passed.

Policy:

- Internal administrator evidence may contain readable file/folder metadata.
- File contents, cookies, session tokens, credentials, and raw credential-bearing URLs remain forbidden.

Architecture Sync: Verified (No doc changes) because this implements the Drive DB enrichment path already defined in the file-level DLP correlation design.

### SSH Readonly Enrichment Automation and Terminal Log Module — 2026-04-28

User confirmed the current DB access pattern should remain the least-intrusive model: Warroom SSHes into the NAS and executes read-only scripts instead of installing a persistent NAS-side agent.

Automation implementation:

- Added `tools/drive_event_enricher.py`.
- The enricher runs locally, streams `tools/drive_file_resolver.py` to the NAS over SSH stdin, executes `sudo -n python3 - <file_id>`, and returns normalized readable DLP event JSON.
- No helper script is installed on the NAS, and Drive SQLite databases are opened read-only.
- Controlled run with `file_id=853993314635001175` produced a readable `webapp_file_preview` event with `file_name`, `folder_path`, `display_path`, `view_id`, and `node_id`.

Grafana design/implementation:

- Added `grafana/dashboards/warroom-dlp-terminal-stream.json`.
- This dashboard provides terminal-like Loki log panels for comprehensive chronological DLP evidence streams inside Grafana's graph-oriented interface.
- It includes a full evidence stream and a narrower action-candidate stream for viewer/download/share/API-like activity.

Validation:

- `python3 -m py_compile tools/drive_file_resolver.py tools/drive_event_enricher.py` passed.
- `jq empty grafana/dashboards/warroom-dlp-terminal-stream.json` passed.
- `jq empty grafana/dashboards/warroom-dlp-web-ingress.json` passed.
- `docker compose -f docker-compose.yml --profile synology-nginx-logs config` passed.

Tasks updated:

- `5.13` now records SSH readonly enrichment CLI and the first readable fixture as partial completion.
- `5.14` now records the terminal-like Grafana log stream dashboard as partial completion.

Architecture Sync: Verified (No doc changes) because this implements the agreed SSH-readonly enrichment and Grafana log visualization surfaces inside existing Warroom boundaries.

### Grafana Dashboard Chinese Management Labels — 2026-04-28

User confirmed Grafana OSS does not need full i18n replacement if Warroom dashboards and event payloads are localized. The dashboard shell remains Grafana-native English where unavoidable, while Warroom-managed dashboards use Traditional Chinese titles/descriptions.

Changes:

- Renamed `warroom-dlp-terminal-stream` dashboard title to `DLP 即時事件流`.
- Renamed `warroom-dlp-web-ingress` dashboard title to `DLP 網頁存取統計`.
- Localized panel titles/descriptions for terminal-like evidence stream, action-candidate stream, route activity trend, event count, HTTP status distribution, and raw web-ingress evidence stream.
- Restarted Grafana so provisioning reloaded the updated dashboard JSON files.

Validation:

- `jq empty grafana/dashboards/warroom-dlp-web-ingress.json` passed.
- `jq empty grafana/dashboards/warroom-dlp-terminal-stream.json` passed.
- Grafana search API confirmed the Warroom folder now contains `DLP 即時事件流` and `DLP 網頁存取統計`.

Architecture Sync: Verified (No doc changes) because this is a presentation/localization improvement only.

### Grafana Home Dashboard Override — 2026-04-28

User requested removing the default Grafana welcome/blog home screen and opening directly into the Warroom comprehensive panel.

Changes:

- Set `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/warroom-dlp-terminal-stream.json` in `docker-compose.yml`.
- Recreated `warroom-grafana` so the environment variable is active.
- Set Grafana organization preferences `homeDashboardUID=warroom-dlp-terminal-stream` through the Grafana API.

Validation:

- Container environment contains the default home dashboard path.
- Grafana organization preferences return `homeDashboardUID: warroom-dlp-terminal-stream`.
- Dashboard search confirms `DLP 即時事件流` is available under the Warroom folder.

Architecture Sync: Verified (No doc changes) because this is a Grafana presentation/default-route change only.

### Grafana Home Dashboard Switched to Web Ingress — 2026-04-28

User requested the Grafana Home route open the web ingress statistics dashboard instead of the terminal stream dashboard.

Changes:

- Updated `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH` in `docker-compose.yml` to `/var/lib/grafana/dashboards/warroom-dlp-web-ingress.json`.
- Recreated `warroom-grafana` so the environment variable is active.
- Set Grafana organization preferences `homeDashboardUID=warroom-dlp-web-ingress` through the Grafana API.

Validation:

- Container environment now points to `warroom-dlp-web-ingress.json`.
- Grafana organization preferences return `homeDashboardUID: warroom-dlp-web-ingress`.

Architecture Sync: Verified (No doc changes) because this is a Grafana presentation/default-route change only.

### Public Grafana URL and Viewer User — 2026-04-28

User requested making `https://cms.thesmart.cc/warroom/` the public Warroom Grafana website and adding a normal viewer account that can read the home dashboard.

Changes:

- Updated Grafana root URL default in `docker-compose.yml` to `https://cms.thesmart.cc/warroom/`.
- Updated `.env.example` to document the same public root URL.
- Recreated `warroom-grafana` so the public root URL is active.
- Created Grafana user `ncu8ds`.
- Set `ncu8ds` organization role to `Viewer`.

Validation:

- `GF_SERVER_ROOT_URL` inside the container is `https://cms.thesmart.cc/warroom/`.
- `https://cms.thesmart.cc/warroom/login` returns HTTP 200.
- `https://cms.thesmart.cc/warroom/d/warroom-dlp-web-ingress/` returns HTTP 200.
- Admin API confirms `ncu8ds` role is `Viewer`.
- `ncu8ds` can search/read `DLP 即時事件流` and `DLP 網頁存取統計` dashboards.

Security note:

- The viewer password was applied via Grafana API but is not recorded in this event log.

Architecture Sync: Verified (No doc changes) because this is deployment/access configuration for the existing Grafana surface.

### Gateway Route Access Corrected for Public Warroom — 2026-04-28

User reported `https://cms.thesmart.cc/warroom/` still showed the opencode/TheSmartAI gateway login instead of Grafana. Root cause: the opencode gateway route `/warroom` was still configured with gateway auth enabled (`auth=1`), so requests were blocked before reaching Grafana.

Changes:

- Updated `/home/pkcs12/.config/web_registry.json` so the `warroom` entry has `access: public`.
- Updated the active gateway route table so `/warroom 127.0.0.1 3000 1000 0`.
- Used `/run/opencode-gateway/ctl.sock` to remove and republish `/warroom` with `auth: 0`, updating the gateway in-memory route table without restarting the gateway.

Validation:

- Control socket route list returns `/warroom` with `auth: 0`.
- `/etc/opencode/web_routes.conf` contains `/warroom 127.0.0.1 3000 1000 0`.
- Public `https://cms.thesmart.cc/warroom/` now redirects to `/warroom/login` from Grafana rather than showing the opencode login page.
- Public `https://cms.thesmart.cc/warroom/login` returns Grafana login headers.

Architecture Sync: Verified (No doc changes) because this fixes gateway access policy for the existing public Grafana route.

### Grafana Traditional Chinese Image Patch — 2026-04-28

User requested using Grafana's existing Simplified Chinese i18n as the basis for a Traditional Chinese Warroom image, then clarified that the language menu label must also show Traditional Chinese.

Changes:

- Converted `/usr/share/grafana/public/locales/zh-Hans/grafana.json` from Simplified Chinese to Traditional Chinese using OpenCC `s2twp.json`.
- Patched Grafana's language bundle so the `zh-Hans` option displays `中文（繁體）` instead of `中文（简体）`.
- Committed the patched running container as local image `registore.thesmart.cc/warroom/grafana:11.5.2-zh-hant`.
- Restored the NAS Docker Registry service by recreating container `registry1` from `registry:latest` with `/volume1/docker/registry:/var/lib/registry` and `5050:5000`.
- Pushed the image into the NAS registry from the NAS side as `warroom/grafana:11.5.2-zh-hant`.
- Updated `docker-compose.yml` so `warroom-grafana` uses `registore.thesmart.cc/warroom/grafana:11.5.2-zh-hant` instead of rebuilding the local Grafana image.

Validation:

- `http://127.0.0.1:3000/public/locales/zh-Hans/grafana.json` is valid JSON and contains Traditional Chinese terms such as `儀表板`.
- `http://127.0.0.1:3000/public/build/355.99c61a8a485bbdf597fd.js` contains the language label `中文（繁體）` and no longer contains the original `中文（简体）` label.
- `https://registore.thesmart.cc/v2/warroom/grafana/tags/list` returns tag `11.5.2-zh-hant`.
- `https://registore.thesmart.cc/v2/warroom/grafana/manifests/11.5.2-zh-hant` returns digest `sha256:43b47e1169547f070cf2679b185690993911cefdd181d3ce3400ddcb43df28c1`.
- `docker compose -f docker-compose.yml config` passed.
- `warroom-grafana` was recreated from `registore.thesmart.cc/warroom/grafana:11.5.2-zh-hant` and the refreshed container still serves the Traditional Chinese locale and language label.

Registry root cause:

- Synology reverse proxy already pointed `registore.thesmart.cc` to `http://192.168.100.40:5050`, but `registry1` had been stopped and lost its host port binding.
- Recreating `registry1` with the original registry data volume restored `/v2/` and enabled registry publication without changing stored image data.

Architecture Sync: Verified (No doc changes) because this is a Grafana presentation/image packaging change only.

### Warroom Custom C Node Exporter Design — 2026-04-28

Scope:

- Completed `tasks.md` item 5.8 as a design-only slice.
- Added a custom C exporter design for NAS infrastructure metrics and capability-gap reporting.

Artifact added:

- `plans/20260427_warroom_monitoring_platform/custom-c-node-exporter-design.md`

Key decisions:

- The exporter exposes Prometheus text format over `/metrics` with `/healthz` and `/readyz` health endpoints.
- The exporter returns current or last-known metrics on every scrape and exposes staleness/success indicators instead of sparse interval-only responses.
- The exporter reports NAS infrastructure and capability-gap metrics only; file-level DLP actions remain in nginx/Loki and Drive/File Station DB collection paths.
- Labels must remain bounded; raw file paths, usernames, IP addresses, session IDs, permanent links, and arbitrary error text are forbidden as metric labels.
- First implementation slice should validate on a non-production Linux target before any NAS-side installation.

Validation:

- Design aligns with `capability-detection.md` and `synology-observability-capability-probe.md`.
- No NAS service, DSM setting, Docker container, package, or runtime config was changed for this design slice.
- Architecture Sync: Verified (No doc changes) because this remains inside the existing Prometheus/Grafana observability boundary; DLP event and file identity module boundaries are unchanged.

### File Station Transfer DB Adapter — 2026-04-28

Scope:

- Completed `tasks.md` item 5.10: implement a read-only File Station adapter over `/volume1/@database/synolog/.DSMFMXFERDB`.
- Extended `tasks.md` item 5.13 partial event-flow evidence with a File Station transfer fixture.

Artifacts added:

- `tools/file_station_transfer_adapter.py`
- `fixtures/dlp-events/file-station-transfer-download-sanitized.json`

Implementation notes:

- The adapter opens SQLite databases in read-only mode and sets `PRAGMA query_only = ON`.
- It supports local reads and remote least-intrusive SSH stdin execution, matching the existing Drive enrichment model without installing helper scripts on the NAS.
- It discovers candidate DB files and tables through `sqlite_master` / `PRAGMA table_info` instead of assuming a single table name.
- It maps explicit download-like commands to `webapp_file_download`, export/archive-like commands to `webapp_file_export`, and leaves unmapped commands as `unknown` with lower confidence.
- It emits sanitized Warroom DLP-style event JSON with `source_channel=file_station_transfer_db`, `source_app=file_station`, `source_surface=transfer_db`, and bounded `raw_ref` / `correlation_refs`.

Safety notes:

- No file contents, cookies, session tokens, credentials, or raw credential-bearing URLs are read or written.
- The committed fixture is synthetic/sanitized and does not contain raw NAS rows.
- No NAS service, DSM setting, Docker container, package, or runtime config was changed for this adapter slice.

Validation:

- `python3 -m py_compile tools/drive_file_resolver.py tools/drive_event_enricher.py tools/file_station_transfer_adapter.py` passed.
- `jq empty fixtures/dlp-events/file-station-transfer-download-sanitized.json` passed.
- `docker compose -f docker-compose.yml config` passed.
- Architecture Sync: Verified (No doc changes) because this implements the already-planned File Station transfer DB collector boundary without changing the broader Warroom module boundaries.

### Minimal DLP Event Collector Slice — 2026-04-28

Scope:

- Completed `tasks.md` item 5.13's local continuous-event-flow slice.
- Added a local collector CLI that can read normalized DLP fixture/event JSON and either dry-run JSONL output or push bounded-label streams to Loki.

Artifact added:

- `tools/dlp_event_collector.py`

Implementation notes:

- The collector reads local JSON objects or JSON arrays from explicit file paths only.
- It validates required fields: `event_id`, `action`, `source_channel`, `source_app`, and `confidence`.
- It adds `collector="warroom-dlp-event-collector"` and `ingested_at` when absent.
- Loki labels are intentionally bounded to `job`, `source_channel`, `source_app`, `action`, and optional `nas_host`; raw paths, filenames, usernames, and source IPs remain in event payload only, not labels.
- Missing inputs, invalid JSON, invalid confidence, missing required fields, missing `--loki-url`, and Loki push failures return explicit fail-fast JSON with non-zero exit.

Safety notes:

- No NAS probing, SSH execution, DSM setting, container, package, or runtime config change was performed for this collector slice.
- No file contents, cookies, session tokens, credentials, or raw credential-bearing URLs are read or written.
- No fallback behavior, daemonization, credential storage, or implicit NAS access was added.

Validation:

- `python3 -m py_compile tools/dlp_event_collector.py tools/file_station_transfer_adapter.py tools/drive_event_enricher.py tools/drive_file_resolver.py` passed.
- `python3 tools/dlp_event_collector.py --dry-run fixtures/dlp-events/file-station-transfer-download-sanitized.json` passed.
- `python3 tools/dlp_event_collector.py --dry-run fixtures/dlp-events/drive-file-preview-readable.json fixtures/dlp-events/file-station-transfer-download-sanitized.json` passed.
- Negative missing-field fixture returned non-zero fail-fast JSON with `stage="missing_required_fields"`; temporary files were cleaned.
- `python3 tools/dlp_event_collector.py --loki-url http://127.0.0.1:3100/loki/api/v1/push --timeout-sec 3 fixtures/dlp-events/file-station-transfer-download-sanitized.json` pushed one sanitized fixture event to local Loki and returned `{"events_pushed": 1, "ok": true}`.
- Architecture Sync: Verified (No doc changes) because this implements local normalized event emission inside the already-planned Loki/collector boundary without changing module boundaries.

## Architecture Sync

Architecture Sync: Completed for planning scope.

Long-lived architecture knowledge is now captured in:

- `specs/architecture.md`
- `plans/20260427_warroom_monitoring_platform/implementation-architecture.md`
- `plans/20260427_warroom_monitoring_platform/file-level-dlp-correlation.md`
- this event log

### Long-Lived Architecture Document Created — 2026-04-28

Scope:

- Created `specs/architecture.md` as the current Warroom architecture SSOT.
- Consolidated the runtime component boundaries, evidence data flows, security constraints, current validation signals, and remaining architecture items from the active plan and event log.

Key architecture state captured:

- Grafana remains the dashboard/visualization plane and does not own NAS credentials, policy state, or approvals.
- Loki stores web-ingress and normalized DLP event evidence with bounded labels.
- Prometheus owns metrics/exporter health; Synology SNMP remains template-only until approved configuration exists.
- Synology nginx provides route/timing/action-candidate evidence but cannot identify browser-fragment file ids by itself.
- Drive DB enrichment maps `file_id` / `permanent_id` to readable object metadata through `view-route-db.sqlite` and `view/<id>/view-db.sqlite`.
- File Station transfer DB evidence is handled by the read-only `.DSMFMXFERDB` adapter.
- `tools/dlp_event_collector.py` is the current local normalized event ingestion path for sanitized fixtures and Loki pushes.

Validation:

- Architecture Sync: Updated `specs/architecture.md` from current plan/event/tool state.
- No NAS service, DSM setting, Docker container, package, or runtime route was changed for this documentation sync.
- `docker compose -f docker-compose.yml config` passed.
- `docker compose -f docker-compose.yml --profile synology-nginx-logs config` passed.
- `python3 -m py_compile tools/drive_file_resolver.py tools/drive_event_enricher.py tools/file_station_transfer_adapter.py tools/dlp_event_collector.py` passed.
- `jq empty` passed for the active Grafana dashboards, DLP fixtures, and `test-vectors.json`.


### Drive/File Station DB Evidence Dashboard — 2026-04-28

Scope:

- Completed `tasks.md` item 5.14's Drive/File Station DB-backed dashboard slice.
- Added a dedicated Grafana dashboard for normalized file-level DLP evidence from Drive DB enrichment and File Station transfer DB adapter events.

Changes:

- Added `grafana/dashboards/warroom-dlp-file-evidence.json` with stable UID `warroom-dlp-file-evidence` and title `DLP 檔案證據總覽`.
- Added bounded-label Loki panels for normalized file event count, Drive/File Station action trends, Drive DB open/preview evidence, File Station download/export evidence, capability gaps, and a combined file-level evidence stream.
- Updated `plans/20260427_warroom_monitoring_platform/tasks.md` item 5.14 to complete.

Safety notes:

- No NAS access, SSH, live browser action, external URL access, Docker runtime change, credential, raw log, cookie, session id, or file content was used.
- Dashboard queries group only by bounded Loki labels such as `job`, `source_app`, and `action`; readable file metadata remains in normalized event payloads only.

Validation:

- `jq empty grafana/dashboards/warroom-dlp-file-evidence.json grafana/dashboards/warroom-dlp-web-ingress.json grafana/dashboards/warroom-dlp-terminal-stream.json fixtures/dlp-events/drive-file-preview-readable.json fixtures/dlp-events/file-station-transfer-download-sanitized.json` passed.
- `docker compose -f docker-compose.yml config` passed.
- Architecture Sync: Verified (No doc changes) because this implements the DB-backed Grafana visualization surface already recorded in `specs/architecture.md` without changing runtime component boundaries.

### Controlled File Station Preview/Open Validation and AI Judge Deferral — 2026-04-28

Scope:

- Completed `tasks.md` item 5.16's remaining File Station preview/open validation slice.
- Completed `tasks.md` item 5.17 by explicitly keeping AI Alert Judge deferred from this POC implementation slice.

Changes:

- Verified the File Station transfer DB path is the SQLite file `/volume1/@database/synolog/.DSMFMXFERDB` with table `logs`; `/volume1/@database/synolog/.DSMFMXFERDB/logs` is not a valid DB path in this environment.
- Updated `tools/file_station_transfer_adapter.py` default DB path to `/volume1/@database/synolog/.DSMFMXFERDB`.
- Updated `fixtures/dlp-events/file-station-transfer-download-sanitized.json` to reference table `logs` under the correct DB file path.
- Updated `plans/20260427_warroom_monitoring_platform/webapp-access-control-validation-plan.md` with the V5 result: two controlled File Station preview/open attempts produced no new `.DSMFMXFERDB` table `logs` row during the immediate observation window.
- Updated `plans/20260427_warroom_monitoring_platform/tasks.md` so 5.16 and 5.17 are complete.
- Updated `specs/architecture.md` to reflect decoded Drive action candidates, File Station preview/open capability gap, and DB-backed Grafana dashboard completion.

Validation evidence:

- Baseline before second File Station preview/open attempt: `logs` count `14771`, max rowid `14771`, max time `1777353237`, latest `cmd=download` count `1243`.
- After second File Station preview/open attempt: `logs` count `14771`, max rowid `14771`, max time `1777353237`, latest `cmd=download` count remained `1243`.
- Therefore File Station explicit download/export remains observable through `/volume1/@database/synolog/.DSMFMXFERDB` table `logs`, while pure preview/open is a capability gap unless another evidence source is proven.
- `python3 -m py_compile tools/file_station_transfer_adapter.py tools/drive_file_resolver.py tools/drive_event_enricher.py tools/dlp_event_collector.py` passed.
- `jq empty fixtures/dlp-events/file-station-transfer-download-sanitized.json fixtures/dlp-events/drive-file-preview-readable.json grafana/dashboards/warroom-dlp-file-evidence.json grafana/dashboards/warroom-dlp-web-ingress.json grafana/dashboards/warroom-dlp-terminal-stream.json` passed.
- `python3 tools/dlp_event_collector.py --dry-run fixtures/dlp-events/file-station-transfer-download-sanitized.json` passed.
- `python3 tools/file_station_transfer_adapter.py --mode remote --limit 1` passed with sanitized summary: `found=true`, `stage=events_normalized`, `event_count=1`, `action=webapp_file_download`, `evidence_path=/volume1/@database/synolog/.DSMFMXFERDB`, `evidence_table=logs`.
- `docker compose -f docker-compose.yml config` passed.
- Consistency grep found only intentional negative references to `/volume1/@database/synolog/.DSMFMXFERDB/logs` documenting that it is not a valid DB path.
- Secret/token grep found no concrete committed secrets in touched Warroom files; the only remaining match is a generic `basic_auth_handler` function in the vendored `refs/activeinsight` snapshot.

Safety notes:

- Observations were aggregate/read-only metadata snapshots only.
- No file contents, raw filenames from the live test, cookies, session IDs, credentials, sharing tokens, or raw URLs were stored.

Architecture Sync: Updated `specs/architecture.md` from the controlled validation results.

### Public README and GitHub Publication Prep — 2026-04-28

Scope:

- Prepared a public-facing `README.md` explaining the Warroom Synology NAS DLP POC, implementation approach, usage, and safety boundaries.
- Embedded the Traditional Chinese multi-level IDEF0 SVG diagrams from `drawmiat-multilevel-zh`.
- Added a public-safe `.gitignore` so local event logs, private planning markdown, architecture notes, reference snapshots, runtime logs, SQLite DB files, and credential files are not uploaded.
- Sanitized public defaults and fixtures by replacing private host/account/domain examples with placeholders such as `nas.example.local`, `nas-admin`, `demo-nas`, and `http://localhost:3000/`.

Files changed for public surface:

- `README.md`
- `.gitignore`
- `.env.example`
- `docker-compose.yml`
- `tools/drive_event_enricher.py`
- `tools/file_station_transfer_adapter.py`
- `fixtures/dlp-events/drive-file-preview-readable.json`
- `fixtures/dlp-events/file-station-transfer-download-sanitized.json`

Safety notes:

- Real email, NAS login hint, private public URL, internal IPs, registry URL, live Drive object metadata, and concrete user/file path examples were kept out of the public README and sanitized from tracked defaults/fixtures.
- Private local artifacts remain in the working directory but are excluded by `.gitignore` before GitHub publication.

Validation:

- Pending final git-aware tracked-file secret scan before commit/push.
- Architecture Sync: Verified (No doc changes) because this is public documentation/sanitization for an existing implementation boundary.

### MIAT-Compliant IDEF0/GRAFCET Regeneration — 2026-04-28

Scope:

- Loaded `miatdiagram` and regenerated drawmiat-compatible IDEF0/GRAFCET artifacts for the public Warroom POC.
- Created a new `plans/20260427_warroom_monitoring_platform/miat-compliant/` output set instead of overwriting the older diagram folder.
- Updated `README.md` to reference the new compliant IDEF0 SVGs and the GRAFCET state-machine SVG.

Artifacts added:

- `plans/20260427_warroom_monitoring_platform/miat-compliant/warroom_idef0.json`
- `plans/20260427_warroom_monitoring_platform/miat-compliant/warroom_grafcet.json`
- `plans/20260427_warroom_monitoring_platform/miat-compliant/diagram_A0.svg`
- `plans/20260427_warroom_monitoring_platform/miat-compliant/diagram_A1.svg`
- `plans/20260427_warroom_monitoring_platform/miat-compliant/diagram_A3.svg`
- `plans/20260427_warroom_monitoring_platform/miat-compliant/diagram_A4.svg`
- `plans/20260427_warroom_monitoring_platform/miat-compliant/diagram_Main.svg`

Validation:

- `drawmiat_validate_diagram` passed for IDEF0: 5 activities, 12 arrows, node reference `A0`.
- `drawmiat_validate_diagram` passed for GRAFCET: 9 steps, 1 initial step.
- `drawmiat_generate_diagram` generated the IDEF0 and GRAFCET SVG files listed above.
- Architecture Sync: Verified (No doc changes) because this regenerates formal diagrams for the existing public architecture without changing runtime boundaries.

## Next Recommended Step

The current implementation milestone slice is complete. Next work should start a new scoped plan/slice for rule thresholds, incident schema, and optional AI Alert Judge integration if desired.
