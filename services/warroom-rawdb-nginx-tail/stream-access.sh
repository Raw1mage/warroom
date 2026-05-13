#!/usr/bin/env bash
# Ship rawdb's DSM nginx access log (combined format) into warroom Loki pipeline.
set -euo pipefail
DEVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DEVICE_DIR/state/nginx-access-stream.log"
mkdir -p "$(dirname "$OUT")"; touch "$OUT"
exec ssh \
  -o BatchMode=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=accept-new \
  -i "$HOME/.ssh/id_ed25519" \
  yeatsluo@192.168.100.40 \
  "sudo tail -F -n 0 /var/log/nginx/warroom-access.log" >> "$OUT"
