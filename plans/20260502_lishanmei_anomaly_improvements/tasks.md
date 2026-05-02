# Tasks — 利善美智能異常偵測強化

## 1. Plan and audit baseline

- [x] 1.1 Write implementation spec and execution gates
- [x] 1.2 Record event log baseline and prior readiness evidence

## 2. Capability gap dashboard

- [x] 2.1 Update capability gap panel titles/queries to split active 2m and historical 24h, using registry-backed `source_key/affected_capability/gap_stage` semantics
- [~] 2.2 Add remediation-oriented latest gap table if dashboard shape allows (deferred: current pass added active stat + historical histogram; detailed remediation table should follow after stable gap taxonomy)

## 3. Auth anomaly source

- [x] 3.1 Add global `tools/auth_log_adapter.py`
- [x] 3.2 Add `auth_log_remote` to collector source registry and dispatch
- [x] 3.3 Add `auth_log_remote` to `lishanmei/config/sources.json`

## 4. Network anomaly source

- [x] 4.1 Add global `tools/network_socket_adapter.py`
- [x] 4.2 Add `network_socket_remote` to collector source registry and dispatch
- [x] 4.3 Add `network_socket_remote` to `lishanmei/config/sources.json`

## 5. Dashboard and validation

- [~] 5.1 Add anomaly readiness panels for auth failures, connection summary, traffic spike readiness, large downloads, off-hours downloads (partial: active gaps, auth failures, TCP established, large downloads added; off-hours panel deferred)
- [x] 5.2 Run Python/JSON/Compose/dashboard validations
- [x] 5.3 Update event log and architecture sync notes

## 6. SSH execution-plan runner design

- [x] 6.1 Document bounded long-running SSH runner MVP contract with TTL/heartbeat/max cycles
- [x] 6.2 Decide whether to implement runner MVP in this phase or leave as next phase

## 7. Registry rebuild after validation

- [x] 7.1 Replace scattered allowed-source dispatch with collector source registry
- [x] 7.2 Split internal `source_key` from evidence `source_channel/source_app` and capability-gap `affected_*` fields
- [x] 7.3 Rework active gap panel to short-window registry gap query to avoid restart-transition pollution
