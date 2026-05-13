#!/usr/bin/env bash
# Install a router-side DROP rule for an attacker IP, in raw/PREROUTING so
# the packet is dropped BEFORE conntrack tracks it.
#
# Usage: ban-set.sh <ip>
# Records to state/banned.json (atomic via tmpfile+mv).
set -euo pipefail
source "$(dirname "$0")/../lib/safe-apply.sh"
source "$(dirname "$0")/../lib/whitelist.sh"

IP="${1:?usage: $0 <ip>}"
TTL_SEC="${TTL_SEC:-3600}"
BAN_REASON="${BAN_REASON:-manual}"

# basic IPv4 sanity (defense in depth — safe-apply target allow-list is the
# real guarantee)
case "$IP" in
  *[!0-9.]*) echo "invalid IP: $IP" >&2; exit 2 ;;
esac

# Hard whitelist — refuse to ever ban these. This is a defense layer beyond
# the tick-level filter, because ban-set.sh may also be invoked by hand.
if is_whitelisted "$IP"; then
  echo "[ban-set] REFUSED: $IP is whitelisted" >&2
  exit 3
fi

STATE="$DEVICE_DIR/state/banned.json"
mkdir -p "$(dirname "$STATE")"
[ -f "$STATE" ] || echo '{}' > "$STATE"

RULE_BODY="-i $WAN_IFACE -s $IP -j DROP"

apply_router_rule_with_rollback raw PREROUTING -I "$RULE_BODY" "ban-$IP"

# record ban with expiry
now=$(date +%s)
exp=$((now + TTL_SEC))
tmp="$(mktemp)"
jq --arg ip "$IP" --arg reason "$BAN_REASON" \
   --argjson banned_at "$now" --argjson expires_at "$exp" \
   '.[$ip] = {banned_at: $banned_at, expires_at: $expires_at, reason: $reason}' \
   "$STATE" > "$tmp" && mv "$tmp" "$STATE"

echo "[ban-set] $IP banned until $(date -d @$exp '+%F %T') (reason=$BAN_REASON)"
