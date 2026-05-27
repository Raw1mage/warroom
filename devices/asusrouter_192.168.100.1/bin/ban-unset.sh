#!/usr/bin/env bash
# Remove a router-side DROP rule and write a grace period to prevent immediate
# re-ban by cron ticks (Loki events stay in-window after unban).
# Usage: ban-unset.sh <ip>
set -euo pipefail
source "$(dirname "$0")/../lib/safe-apply.sh"

IP="${1:?usage: $0 <ip>}"
case "$IP" in *[!0-9.]*) echo "invalid IP: $IP" >&2; exit 2 ;; esac

STATE="$DEVICE_DIR/state/banned.json"
RULE_BODY="-i $WAN_IFACE -s $IP -j DROP"
GRACE_SEC="${GRACE_SEC:-1800}"   # must be ≥ longest tick WINDOW_SEC (correlation=1800)

remove_router_rule raw PREROUTING "$RULE_BODY" "ban-$IP"

# Instead of deleting the entry, replace it with a grace marker.
# Ticks check for .suppressed and skip; expiry logic cleans it after grace_until.
now=$(date +%s)
grace_until=$((now + GRACE_SEC))
if [ -f "$STATE" ]; then
  tmp="$(mktemp)"
  jq --arg ip "$IP" --argjson grace_until "$grace_until" \
     'if .[$ip] then .[$ip] = {suppressed: true, grace_until: $grace_until} else . end' \
     "$STATE" > "$tmp" && mv "$tmp" "$STATE"
fi
echo "[ban-unset] $IP unbanned (grace until $(date -d @$grace_until '+%F %T'))"
