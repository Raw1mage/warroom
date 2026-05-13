#!/usr/bin/env bash
# Remove a router-side DROP rule and clear state.
# Usage: ban-unset.sh <ip>
set -euo pipefail
source "$(dirname "$0")/../lib/safe-apply.sh"

IP="${1:?usage: $0 <ip>}"
case "$IP" in *[!0-9.]*) echo "invalid IP: $IP" >&2; exit 2 ;; esac

STATE="$DEVICE_DIR/state/banned.json"
RULE_BODY="-i $WAN_IFACE -s $IP -j DROP"

remove_router_rule raw PREROUTING "$RULE_BODY" "ban-$IP"

if [ -f "$STATE" ]; then
  tmp="$(mktemp)"
  jq --arg ip "$IP" 'del(.[$ip])' "$STATE" > "$tmp" && mv "$tmp" "$STATE"
fi
echo "[ban-unset] $IP unbanned"
