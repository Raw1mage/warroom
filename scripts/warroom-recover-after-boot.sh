#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${WARROOM_PROJECT_DIR:-/home/pkcs12/projects/warroom}"
DASHBOARD_FILE="${WARROOM_HOME_DASHBOARD_FILE:-grafana/dashboards/thesmart-dlp-file-evidence.json}"
GRAFANA_CONTAINER="${WARROOM_GRAFANA_CONTAINER:-warroom-grafana}"
WAIT_TIMEOUT_SECONDS="${WARROOM_BOOT_WAIT_TIMEOUT_SECONDS:-180}"
WAIT_INTERVAL_SECONDS="${WARROOM_BOOT_WAIT_INTERVAL_SECONDS:-5}"
COMPOSE="${WARROOM_DOCKER_COMPOSE:-docker compose}"

log() {
  printf '[warroom-recover] %s\n' "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_cmd docker

if ! docker compose version >/dev/null 2>&1; then
  fail "docker compose plugin is unavailable"
fi

wait_for_project_ready() {
  local deadline now
  deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  while true; do
    if [ -d "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/docker-compose.yml" ] && [ -f "$PROJECT_DIR/$DASHBOARD_FILE" ]; then
      return 0
    fi
    now=$SECONDS
    if [ "$now" -ge "$deadline" ]; then
      fail "project/dashboard files not ready after ${WAIT_TIMEOUT_SECONDS}s: $PROJECT_DIR/$DASHBOARD_FILE"
    fi
    log "waiting for project/dashboard files: $PROJECT_DIR/$DASHBOARD_FILE"
    sleep "$WAIT_INTERVAL_SECONDS"
  done
}

compose_up() {
  log "starting compose stack from $PROJECT_DIR"
  (cd "$PROJECT_DIR" && $COMPOSE up -d --remove-orphans)
}

wait_for_container_dashboard() {
  local deadline now
  deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  while true; do
    if docker exec "$GRAFANA_CONTAINER" test -f "/var/lib/grafana/dashboards/$(basename "$DASHBOARD_FILE")" >/dev/null 2>&1; then
      return 0
    fi
    now=$SECONDS
    if [ "$now" -ge "$deadline" ]; then
      docker ps --filter "name=$GRAFANA_CONTAINER" --format 'table {{.Names}}\t{{.Status}}\t{{.Mounts}}' || true
      fail "Grafana container cannot see dashboard file: /var/lib/grafana/dashboards/$(basename "$DASHBOARD_FILE")"
    fi
    log "waiting for Grafana dashboard bind mount inside $GRAFANA_CONTAINER"
    sleep "$WAIT_INTERVAL_SECONDS"
  done
}

show_status() {
  (cd "$PROJECT_DIR" && $COMPOSE ps)
}

main() {
  wait_for_project_ready
  compose_up
  wait_for_container_dashboard
  log "Grafana dashboard bind mount is visible"
  show_status
}

main "$@"
