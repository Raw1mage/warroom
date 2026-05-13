#!/usr/bin/env bash
# Show currently active bans, both from local state file and from router.
# Useful for sanity-checking drift between warroom truth and router reality.
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

STATE="$DEVICE_DIR/state/banned.json"
[ -f "$STATE" ] || echo '{}' > "$STATE"

echo "=== warroom state (truth) ==="
jq -r 'to_entries | sort_by(.value.expires_at) | .[] | "\(.key)\t reason=\(.value.reason // "?")\t banned_at=\(.value.banned_at|todate)\t expires_at=\(.value.expires_at|todate)"' "$STATE" || true

echo
echo "=== router raw/PREROUTING DROP rules (reality) ==="
rssh 'iptables -t raw -L PREROUTING -nv | awk "NR<=2 || /DROP/"'
