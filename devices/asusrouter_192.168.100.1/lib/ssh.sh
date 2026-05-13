#!/usr/bin/env bash
# Common SSH wrapper for zero-intrusion router control.
# Sourced by every script in bin/.
set -euo pipefail

DEVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DEVICE_DIR/config.env"

rssh() {
  ssh \
    -o ConnectTimeout=5 \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile="$DEVICE_DIR/known_hosts" \
    -o LogLevel=ERROR \
    -o BatchMode=yes \
    -i "$SSH_KEY" \
    "$USER@$HOST" "$@"
}

# Run a heredoc script on the router without leaving anything on disk.
# Caveat: ASUS firmware intercepts the literal command `sh` as a CFE memory
# command (store-halfword), so we MUST NOT invoke `sh` explicitly. Instead,
# ssh passes the whole string to the login shell (busybox ash) for us.
# Usage:  rssh_script <<'SH'
#           commands here
#         SH
rssh_script() {
  local script
  script="$(cat)"
  rssh "$script"
}

export -f rssh rssh_script
