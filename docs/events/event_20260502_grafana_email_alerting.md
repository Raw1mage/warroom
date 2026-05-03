# Event 2026-05-02 — Grafana Email Alerting

## 需求

Use Grafana's built-in alerting framework first and send email alerts to `yeatsluo@gmail.com`.

## Scope IN

- Grafana-managed contact point, notification policy, and alert rules.
- SMTP environment defaults use LAN `rawdb:25` MTA relay; no committed SMTP secret.
- TheSmartAI (`nas_host="thesmart"`) first-batch alerts.

## Scope OUT

- No custom notifier/alert lifecycle engine.
- No LINE relay in this pass.
- No auto-response action.

## Tasks

- Create provisioning artifacts.
- Wire Compose/env placeholders.
- Validate syntax and Grafana visibility.

## Decisions

- Use Grafana Alerting as the primary alert lifecycle and notification system.
- Use `rawdb:25` as the default SMTP relay because the local LAN allows MTA relay.
- Normalize the typed recipient `yeatsluo @gmail.com` to `yeatsluo@gmail.com`.
- Normalize the typed sender `service @sob.com.tw` to `service@sob.com.tw`.

## Validation

- Alerting YAML parse: pass for `contact-points.yml`, `notification-policies.yml`, and `the-smart-ai-rules.yml`.
- `docker compose config`: pass; Grafana SMTP env resolves to `rawdb:25` and sender `service@sob.com.tw`.
- Grafana restarted successfully and loaded SMTP env values:
  - `GF_SMTP_ENABLED=true`
  - `GF_SMTP_HOST=rawdb:25`
  - `GF_SMTP_FROM_ADDRESS=service@sob.com.tw`
- Grafana alerting provisioning log: `finished to provision alerting`.
- Grafana container sees all alerting provisioning files under `/etc/grafana/provisioning/alerting/`.
- Grafana container resolves `rawdb` to `192.168.100.40`; TCP probe to `rawdb:25` succeeded.
- End-to-end SMTP test from the Grafana container to `rawdb:25` succeeded without needing Grafana admin API credentials; MTA accepted the test message from `service@sob.com.tw` to `yeatsluo@gmail.com` and returned queue id `DA3431020A4F`.
- User confirmed the test email was received at `yeatsluo@gmail.com`, completing end-to-end delivery validation.
- Grafana provisioning API verification was skipped because the persisted Grafana admin password differs from the Compose default. This does not block file-based provisioning or SMTP delivery verification, both confirmed above.

## Go-live

- User approved Phase 1 to go live after receiving the test email.
- Phase 1 live scope: Grafana-managed TheSmartAI email alerts via `rawdb:25` MTA relay to `yeatsluo@gmail.com` from `service@sob.com.tw`.
- Phase 1 live boundary: alert lifecycle and email delivery are owned by Grafana Alerting; no auto-response action is enabled.
