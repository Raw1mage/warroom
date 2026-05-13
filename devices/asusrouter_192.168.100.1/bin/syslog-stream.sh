#!/usr/bin/env bash
# Long-running poller of rawdb's Log Center SQLite DB for asusrouter syslog.
# Emits one TSV line per row to state/router-stream.log so the alloy
# compose service can tail it.
#
# Tracks last seen id in state/last-id to avoid re-emitting rows on restart.
# Designed to run under systemd user unit with Restart=always.
set -euo pipefail

DEVICE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$DEVICE_DIR/state/router-stream.log"
LAST_ID_FILE="$DEVICE_DIR/state/last-id"
RAWDB_USER="yeatsluo"
RAWDB_HOST="192.168.100.40"
ROUTER_HOST_DIR="RAWAX86U-1CBDF4B-C"
DB_PATH="/volume1/NetBackup/${ROUTER_HOST_DIR}/SYNOSYSLOGDB_${ROUTER_HOST_DIR}.DB"
POLL_INTERVAL="${POLL_INTERVAL:-2}"

mkdir -p "$(dirname "$OUT")"
touch "$OUT"
[ -f "$LAST_ID_FILE" ] || echo 0 > "$LAST_ID_FILE"

ssh_rawdb() {
  ssh -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -o StrictHostKeyChecking=accept-new -i "$HOME/.ssh/id_ed25519" \
      "$RAWDB_USER@$RAWDB_HOST" "$@"
}

while true; do
  last_id="$(cat "$LAST_ID_FILE")"
  # One row per line via printf(); pipe-separated; embedded newlines stripped.
  rows="$(ssh_rawdb "sudo sqlite3 '$DB_PATH' \"\
    SELECT printf('%d|%d|%s|%s|%s', \
      id, utcsec, IFNULL(prog,''), IFNULL(prio,''), \
      REPLACE(REPLACE(IFNULL(msg,''), char(10),' '), char(13),' ')) \
    FROM logs WHERE id > $last_id ORDER BY id LIMIT 500;\"" 2>/dev/null || true)"
  if [ -n "$rows" ]; then
    printf '%s\n' "$rows" >> "$OUT"
    new_max="$(printf '%s\n' "$rows" | awk -F'|' 'END{print $1}')"
    [ -n "$new_max" ] && echo "$new_max" > "$LAST_ID_FILE"
  fi
  sleep "$POLL_INTERVAL"
done
