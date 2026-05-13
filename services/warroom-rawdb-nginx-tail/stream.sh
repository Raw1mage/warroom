#!/usr/bin/env bash
# Long-running ssh-tail of DSM nginx error.log on rawdb. Emits one line per
# event to a host-side file the alloy compose service tails.
set -euo pipefail
DEVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DEVICE_DIR/state/nginx-error-stream.log"
mkdir -p "$(dirname "$OUT")"; touch "$OUT"
exec ssh \
  -o BatchMode=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=accept-new \
  -i "$HOME/.ssh/id_ed25519" \
  yeatsluo@192.168.100.40 \
  "sudo tail -F -n 500 /var/log/nginx/error.log" >> "$OUT"
