# Event 2026-05-02 — Dashboard Legacy Cleanup

## 需求

User requested dashboard reorganization with no legacy dashboards left after seeing many `No data` panels from an old `warroom-dlp-terminal-stream` URL.

## Scope IN

- Remove legacy `warroom-*` dashboard UIDs/files from provisioning.
- Keep only TheSmartAI/Lishanmei live dashboards.
- Rename NAS host health dashboard away from `warroom-nas-host-health`.
- Update live cross-dashboard links.

## Scope OUT

- No collector/Loki runtime rewrite.
- No alert rule semantic change.
- No legacy alias/redirect dashboards.

## Findings

- Monitoring stack was healthy.
- Loki had live `nas_host="thesmart"` events.
- `No data` was caused by opening legacy UID `warroom-dlp-terminal-stream`, whose panels queried stale labels such as `job="synology-nginx"`.

## Decisions

- Remove legacy UIDs rather than patch them as aliases.
- Use Git history as rollback path instead of leaving legacy JSON in provisioning.

## Validation

- Pending dashboard cleanup completion.
