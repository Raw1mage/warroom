# NAS SSH Pull Onboarding

Warroom monitors many NAS targets with the same non-intrusive pattern: the local collector connects over SSH, streams a read-only Python payload over stdin, captures JSON stdout, and pushes normalized metadata events to Loki. NAS hosts do not run persistent Warroom agents, Promtail, node_exporter, or Grafana by default.

## Contract

- Target inventory lives in `config/nas-targets.json`.
- Each `targets[].id` is the stable Loki/Grafana selector value: `nas_host="<id>"`.
- `targets[].display_name` is human-facing only; it must not replace the stable `id` in queries.
- SSH identity is a host-side SSOT mounted read-only into the collector through `.env`:
  - `WARROOM_SSH_DIR=/home/<operator>/.ssh`
  - `WARROOM_SSH_IDENTITY_FILE=/home/<operator>/.ssh/id_ed25519`
- The configured NAS user must support non-interactive execution of `sudo -n python3 -` for the read-only payloads.
- `host_health_remote` is a standard source for every NAS target. It collects uptime, load, memory, CPU jiffies, disk usage, process count, and service status metadata through the same transient SSH payload path.
- Missing SSH, sudo, Python, host health, DB, or log capabilities must emit `capability_gap`; do not add fallback data.

## Add a NAS target

1. Ensure the host SSH SSOT can connect from the Warroom host:

   ```bash
   ssh -i "$WARROOM_SSH_IDENTITY_FILE" -o IdentitiesOnly=yes <user>@<host> true
   ```

2. Confirm transient payload prerequisites:

   ```bash
   ssh -i "$WARROOM_SSH_IDENTITY_FILE" -o IdentitiesOnly=yes <user>@<host> \
     'sudo -n python3 - <<"PY"
   print("payload_ok")
   PY'
   ```

3. Add one object under `config/nas-targets.json` using `config/nas-targets.example.json` as the template:

   ```json
   {
     "id": "customer-slug",
     "display_name": "Customer Display Name",
     "enabled": true,
     "sources": [
       "host_health_remote",
       "file_station_remote",
       "nas_home_log_remote"
     ],
     "host_health_remote": {
       "host": "nas.example.internal",
       "user": "readonly-admin",
       "timeout_seconds": 90
     },
     "file_station_remote": {
       "host": "nas.example.internal",
       "user": "readonly-admin",
       "db_path": "/volume1/@database/synolog/.DSMFMXFERDB",
       "limit": 50,
       "timeout_seconds": 90
     },
     "nas_home_log_remote": {
       "host": "nas.example.internal",
       "user": "readonly-admin",
       "log_paths": ["/var/log/messages", "/var/log/samba/log.smbd"],
       "tail_lines": 2000,
       "limit": 50,
       "timeout_seconds": 90
     }
   }
   ```

4. Recreate the local collector:

   ```bash
   docker compose up -d --build warroom-dlp-file-collector
   ```

5. Verify source adapters from inside the collector container:

   ```bash
   docker exec warroom-dlp-file-collector sh -lc \
     'python /tools/host_health_adapter.py --mode remote --host <host> --user <user> --nas-host <target-id> --timeout-sec 90'

   docker exec warroom-dlp-file-collector sh -lc \
     'python /tools/file_station_transfer_adapter.py --mode remote --host <host> --user <user> --nas-host <target-id> --limit 1 --timeout-sec 90'

   docker exec warroom-dlp-file-collector sh -lc \
     'python /tools/nas_home_log_adapter.py --mode remote --host <host> --user <user> --nas-host <target-id> --limit 1 --timeout-sec 90'
   ```

6. Verify Loki labels:

   ```logql
   {job="warroom-dlp-event-collector", nas_host="customer-slug"}
   ```

## Dashboard reuse

Use the generic Warroom dashboards with the `$nas` template variable for fleet-wide operations. `warroom-nas-host-health.json` is the baseline machine-health dashboard, and DLP dashboards cover file/log evidence. They discover available targets from:

```logql
label_values({job="warroom-dlp-event-collector"}, nas_host)
```

For large fleets, prefer one reusable dashboard set filtered by `$nas` over manually copying JSON per machine. If a branded customer dashboard is required, generate it from the generic dashboard by changing only UID, title, tags, and the default `$nas` selection; do not hand-edit panel queries.

## Safety boundaries

- Do not copy private keys into images or repo files.
- Do not install persistent code on NAS hosts for the default path.
- Do not open NAS-side Prometheus scrape ports by default.
- Do not use direct syslog as a silent fallback.
- Do not place raw paths, usernames, source IPs, or arbitrary error text in Loki/Prometheus labels.
