# Handoff — 利善美智能異常偵測強化

## Required Reads

- `docs/ops/lishanmei-anomaly-readiness.md`
- `services/warroom-dlp-file-collector/app.py`
- `lishanmei/config/sources.json`
- `tools/nas_system_log_adapter.py`
- `tools/host_health_adapter.py`
- `grafana/dashboards/lishanmei-dlp-file-evidence.json`
- `grafana/dashboards/warroom-nas-host-health.json`

## Execution Notes

- Preserve `/tools` global reusable role.
- Preserve `/<server>/config` and `/<server>/data` split.
- Do not add NAS persistent agent/container/exporter.
- Capability gaps must be explicit events, not hidden fallbacks.

## Expected Output

- New auth and network source events in Loki after collector run.
- Active/historical capability gap dashboard semantics.
- Anomaly readiness panels for management-facing view.
