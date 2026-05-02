# Grafana Email Alerting

Warroom uses Grafana-managed alerting as the first alert-system layer.

## SMTP relay

The local LAN allows `rawdb` to act as MTA relay, so the Docker Compose default is:

```env
GRAFANA_SMTP_ENABLED=true
GRAFANA_SMTP_HOST=rawdb:25
GRAFANA_SMTP_FROM_ADDRESS=service@sob.com.tw
GRAFANA_SMTP_FROM_NAME=Warroom Grafana
GRAFANA_SMTP_SKIP_VERIFY=true
```

No SMTP password or Gmail app password is committed. Override these values in `.env` if the relay host or sender changes.
The default sender address is `service@sob.com.tw`.

## Recipient

The provisioned contact point is `warroom-thesmartai-email` and sends to:

- `yeatsluo@gmail.com`

## Provisioned files

- `grafana/provisioning/alerting/contact-points.yml`
- `grafana/provisioning/alerting/notification-policies.yml`
- `grafana/provisioning/alerting/the-smart-ai-rules.yml`

## Current alert rules

- TheSmartAI collector down.
- TheSmartAI active capability gap.
- TheSmartAI auth failures spike.
- TheSmartAI large download evidence ingested.
- TheSmartAI TCP established count high.

## Operating notes

- Grafana owns alert state, grouping, deduplication, notification policy, and email delivery.
- Warroom collector remains the evidence producer only.
- Large-download alerting is a POC ingestion alert until a freshness/cursor guard is added for File Station `observed_at`.
- Validation confirmed the Grafana container can resolve `rawdb` and connect to TCP port 25.
- End-to-end SMTP test from the Grafana container succeeded; rawdb MTA accepted the message and returned queue id `DA3431020A4F`.
- If UI/API verification is needed, use the current Grafana admin credential from the operator; the persisted password may differ from `.env.example`.
