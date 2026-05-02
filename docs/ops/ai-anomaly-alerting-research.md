# AI Anomaly Alerting Research for Warroom

## Executive Summary

Warroom already has the right observability substrate for a first AI anomaly module: normalized metadata events in Loki, bounded labels, per-server config roots, and collector source registry semantics. The recommended POC is not to start with a deep model. Start with a hybrid pipeline:

1. deterministic rules for obvious high-signal cases;
2. statistical baselines for rates and volumes;
3. unsupervised anomaly scoring once enough history exists;
4. LLM-assisted triage only after the numeric/scored alert exists.

This preserves explainability and avoids hallucinated security alerts.

## Common Model Families

| Family | Examples | Data needed | Strengths | Weaknesses | Warroom fit |
|---|---|---|---|---|---|
| Static rules | thresholds, allow/deny lists, schedules | domain fields + thresholds | explainable, fast POC | brittle, noisy | Best Phase 1 |
| Statistical baselines | z-score, MAD, EWMA, STL decomposition | time buckets by actor/IP/source | simple, explainable drift detection | needs clean seasonality handling | Best Phase 1/2 |
| Density / distance ML | Isolation Forest, Local Outlier Factor, One-Class SVM | numeric feature vectors | works without labels | harder to explain; retraining needed | Phase 2 |
| Clustering | k-means, DBSCAN | normalized behavior vectors | finds peer groups | cluster interpretation needed | Phase 2 |
| Autoencoders | dense / variational autoencoders | large stable numeric history | captures nonlinear patterns | data hungry, less explainable | Later only |
| Sequence models | HMM, LSTM, Transformer | ordered event sequences per actor/IP | detects unusual action order | needs lots of sequence history | Later only |
| Graph / UEBA | bipartite user-file-IP graphs, graph embeddings | actor/IP/file relationships | strong for insider / lateral movement | more engineering | Phase 3 |
| LLM-assisted triage | summarize evidence, classify explanation | already-scored alert + context | readable incident narratives | not reliable as primary detector | Use as assistant, not detector |

## Required Data and Feature Engineering

### Existing Warroom evidence fields

Current Loki payloads already provide:

- Identity / entity: `nas_host`, `actor`, `source_ip`, `source_country`, `source_region`.
- Source taxonomy: `source_key`, `source_app`, `source_channel`, `affected_capability`.
- DLP actions: `webapp_file_download`, `webapp_file_export`, `file_activity`, `auth_failure`, `session_opened`, `network_socket_snapshot`, `capability_gap`.
- File transfer fields: `size_bytes`, path/file metadata where available.
- Auth fields: `event_outcome`, `failure_reason`, `network_protocol`, `service`.
- Network fields: `tcp_connection_count`, `tcp_established_count`, `tcp_listen_count`, `tcp_remote_ip_count`, `top_remote_ips`.
- Host health fields: CPU, memory, disk, network counters, process count, service status from `host_health_remote`.

### Recommended feature buckets

Use fixed windows: 5m, 15m, 1h, 24h.

| Feature group | Example features | Source |
|---|---|---|
| Auth failure rate | `auth_failure_count_5m`, `auth_failure_by_source_ip_1h`, `success_after_failure` | `auth_log` |
| Download behavior | `download_count_15m`, `download_bytes_1h`, `large_download_count_1h`, `top_actor_bytes` | File Station / DLP events |
| Off-hours behavior | `off_hours_login_count`, `off_hours_download_bytes` | auth + download timestamps |
| Network behavior | `tcp_established_max_15m`, `remote_ip_count_15m`, `new_listening_port_seen` | `network_socket` |
| Evidence health | `active_gap_count_2m`, `gap_by_capability_24h` | `collector_capability_gap` |
| Host health | `cpu_busy_avg`, `memory_used_pct`, `disk_used_pct`, `network_tx_rate` | `host_health_remote` |

## Recommended Warroom POC Architecture

```text
Loki normalized events
  -> AI anomaly feature extractor
       - runs scheduled queries against Loki API
       - aggregates features per nas_host / actor / source_ip / source_key
  -> scoring engine
       - rule scorer
       - statistical baseline scorer
       - optional ML scorer after history exists
  -> alert event writer
       - pushes `action="anomaly_alert"` back to Loki
       - writes local audit spool under /<server>/data/alerts
  -> notification dispatcher
       - email
       - LINE Bot push/reply
       - future Slack/webhook
  -> Grafana Alert Center dashboard
```

## Loki Integration Design

### Query mode

Use the Loki HTTP API from a local service, not Grafana as an execution engine.

- `/loki/api/v1/query` for instant scalar scoring.
- `/loki/api/v1/query_range` for trend windows and context samples.
- Keep raw high-cardinality fields in payload extraction, not Loki labels.

### Example feature queries

Auth failures:

```logql
sum by (source_ip) (
  count_over_time({nas_host="lishanmei", source_channel="auth_log", action="auth_failure"}
  | json | source_ip != "" [5m])
)
```

Large downloads:

```logql
sum by (actor) (
  sum_over_time({nas_host="lishanmei", action="webapp_file_download"}
  | json | unwrap size_bytes [1h])
)
```

Network spike:

```logql
max_over_time({nas_host="lishanmei", source_channel="network_socket"}
| json | unwrap tcp_established_count [15m])
```

Active collector gaps:

```logql
sum(count_over_time({nas_host="lishanmei", action="capability_gap", source_channel="collector_capability_gap"}[2m]))
```

## Alert Event Schema

Emit alert decisions back to Loki as normalized metadata events:

```json
{
  "action": "anomaly_alert",
  "nas_host": "lishanmei",
  "source_app": "warroom_ai",
  "source_channel": "ai_anomaly_alert",
  "alert_id": "ai-lishanmei-auth-bruteforce-20260502T120000Z",
  "rule_id": "AUTH_BRUTE_FORCE_SOURCE_IP_V1",
  "severity": "high",
  "status": "active",
  "score": 0.92,
  "model_family": "rule+statistical",
  "entity_type": "source_ip",
  "entity_value_hash": "sha256:...",
  "summary": "登入失敗次數超過 5 分鐘門檻",
  "evidence": {
    "window": "5m",
    "count": 32,
    "threshold": 20
  },
  "recommended_action": "檢查來源 IP、帳號鎖定狀態與是否有成功登入跟隨失敗。",
  "observed_at": 1777700000
}
```

Do not put raw IPs, usernames, paths, or arbitrary text into Loki labels. Keep them in payload; hash sensitive entity values if needed for alert grouping.

## Email and LINE Bot Delivery

### Email

Recommended pattern:

```text
alert event
  -> notification dispatcher
  -> SMTP provider / local relay
  -> recipients from server config or policy config
```

Config should include:

- SMTP host/port/user via environment or secret file.
- Recipient groups by severity.
- Rate limit / dedup window.
- Dry-run mode.

### LINE Bot

Recommended pattern:

```text
alert event
  -> notification dispatcher
  -> LINE Messaging API push message
  -> configured group/user id
```

Config should include:

- Channel access token as secret/env only.
- Target group/user IDs as config, not code.
- Message template with severity, summary, dashboard link, and evidence window.
- Rate limit and dedup.

### Notification lifecycle

1. `candidate`: score computed, below notification threshold.
2. `active`: alert crosses threshold; write Loki event.
3. `notified`: email/LINE sent; write delivery audit event.
4. `suppressed`: duplicate within dedup window.
5. `resolved`: score returns below threshold for N windows.

## Recommended POC Phases

### Phase 1 — Explainable rules + alert events

- Implement local `warroom-ai-anomaly-scorer` service.
- Query Loki every 60s.
- Score 4 rule families:
  - auth brute force by source IP;
  - auth failures by actor;
  - large downloads by actor;
  - active capability gaps.
- Push `anomaly_alert` events back to Loki.
- Add dashboard panels for active alerts and severity counts.

### Phase 2 — Statistical baselines

- Store rolling baselines per `nas_host/entity/rule` in `/<server>/data/ai_state`.
- Use EWMA/MAD/z-score for download volume and TCP established count.
- Add `baseline`, `value`, `z_score`, `expected_range` to alert payload.

### Phase 3 — ML scorer

- Train Isolation Forest on feature vectors once enough history exists.
- Feature vector example:
  - auth failures 5m/1h;
  - downloads count/bytes 15m/1h;
  - tcp established max;
  - off-hours flags;
  - capability gap count.
- Keep ML score as one input, not sole decision.

### Phase 4 — LLM-assisted triage

- LLM summarizes already-selected evidence.
- LLM must not invent root cause or severity.
- Prompt input should include alert payload, bounded evidence samples, and known capability gaps.

## Recommended First Rules

| Rule ID | Condition | Severity | Data source |
|---|---|---|---|
| `AUTH_BRUTE_FORCE_SOURCE_IP_V1` | `auth_failure by source_ip > 20 / 5m` | high | auth_log |
| `AUTH_FAILURE_ACTOR_V1` | `auth_failure by actor > 10 / 15m` | medium | auth_log |
| `DOWNLOAD_LARGE_FILE_V1` | `size_bytes >= 100MB` | medium | file_station |
| `DOWNLOAD_VOLUME_SPIKE_V1` | `download bytes actor > baseline + 3*MAD` | high | file_station |
| `NETWORK_CONNECTION_SPIKE_V1` | `tcp_established_count > baseline + 3*MAD` | medium | network_socket |
| `COLLECTOR_ACTIVE_GAP_V1` | active gap count > 0 / 2m | high | collector_capability_gap |

## Key Risks

- Short history means statistical/ML baselines will be unstable initially.
- Missing actor or source IP can weaken entity-level rules.
- Auth logs can contain repetitive session open/close noise caused by the collector's own SSH use; rules must separate failure events from routine sessions.
- Notification channels need strict dedup/rate limiting to avoid alert storms.
- LINE/email secrets must never be committed.

## Recommendation

Build the first AI module as an explainable scorer, not a black-box model:

```text
warroom-ai-anomaly-scorer
  -> Loki feature queries
  -> rule + baseline scoring
  -> Loki anomaly_alert events
  -> email / LINE dispatcher with dry-run and dedup
```

After 2-4 weeks of stable event history, add Isolation Forest or another unsupervised model as a secondary score.
