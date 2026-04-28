#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

usage() {
  cat <<'USAGE'
Usage: ./webctl.sh <start|stop|restart|status>

Controls the local Warroom Grafana POC Docker Compose stack.
USAGE
}

case "${1:-}" in
  start)
    docker compose -f "${COMPOSE_FILE}" up -d
    ;;
  stop)
    docker compose -f "${COMPOSE_FILE}" down
    ;;
  restart)
    docker compose -f "${COMPOSE_FILE}" down
    docker compose -f "${COMPOSE_FILE}" up -d
    ;;
  status)
    docker compose -f "${COMPOSE_FILE}" ps
    ;;
  *)
    usage
    exit 2
    ;;
esac
