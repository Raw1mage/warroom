# Warroom Reboot Recovery

## Purpose

After host reboot, Docker may start containers before the Warroom project path and dashboard bind mounts are fully ready. The observed failure mode is Grafana starting with an empty `/var/lib/grafana/dashboards` mount, which makes the configured home dashboard fail to load.

This recovery path waits for the project and dashboard files, starts the Docker Compose stack, and verifies that Grafana can see the dashboard JSON inside the container.

## Files

- `scripts/warroom-recover-after-boot.sh`
- `deploy/systemd/warroom-compose-recover.service`

## Safety

The recovery script does not remove volumes and does not run `docker compose down -v`. It only:

1. Waits for `docker-compose.yml` and the home dashboard JSON to exist.
2. Runs `docker compose up -d --remove-orphans` from the project directory.
3. Verifies `/var/lib/grafana/dashboards/thesmart-dlp-file-evidence.json` inside `warroom-grafana`.
4. Prints `docker compose ps`.

## Manual run

```bash
/home/pkcs12/projects/warroom/scripts/warroom-recover-after-boot.sh
```

## Install systemd unit

```bash
sudo cp /home/pkcs12/projects/warroom/deploy/systemd/warroom-compose-recover.service /etc/systemd/system/warroom-compose-recover.service
sudo systemctl daemon-reload
sudo systemctl enable warroom-compose-recover.service
sudo systemctl start warroom-compose-recover.service
```

## Check status

```bash
systemctl status warroom-compose-recover.service
journalctl -u warroom-compose-recover.service -b
```

## Tunables

- `WARROOM_PROJECT_DIR` defaults to `/home/pkcs12/projects/warroom`.
- `WARROOM_HOME_DASHBOARD_FILE` defaults to `grafana/dashboards/thesmart-dlp-file-evidence.json`.
- `WARROOM_GRAFANA_CONTAINER` defaults to `warroom-grafana`.
- `WARROOM_BOOT_WAIT_TIMEOUT_SECONDS` defaults to `180`.
- `WARROOM_BOOT_WAIT_INTERVAL_SECONDS` defaults to `5`.
