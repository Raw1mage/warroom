#!/usr/bin/env bash
# Enable SNMP v2c on the router, LAN-only, with a non-default community.
# This mutates nvram and starts a service — distinct from the iptables-only
# safe-apply path. We snapshot current values and produce a diff.
#
# Pair: snmp-enable-unset.sh
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

# Read community from config.env if user overrode; else generate a random one
# and persist it back. Random > "public" to avoid drive-by scanners on LAN.
SNMP_COMMUNITY="${SNMP_COMMUNITY:-}"
CONFIG="$DEVICE_DIR/config.env"
if [ -z "$SNMP_COMMUNITY" ]; then
  if grep -q '^SNMP_COMMUNITY=' "$CONFIG"; then
    SNMP_COMMUNITY="$(. "$CONFIG"; echo "$SNMP_COMMUNITY")"
  else
    SNMP_COMMUNITY="warroom-$(head -c 16 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 12)"
    printf '\n# Auto-generated SNMP v2c community (LAN-only).\nSNMP_COMMUNITY=%q\n' "$SNMP_COMMUNITY" >> "$CONFIG"
    echo "[snmp] generated community and saved to config.env"
  fi
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
snap="$DEVICE_DIR/snapshots/${ts}_snmp"
mkdir -p "$snap"

echo "[snmp] capturing baseline nvram"
rssh '
  for k in snmpd_enable snmpd_wan snmpd_community snmpd_rocommunity snmpd_rwcommunity \
           snmpd_sysname snmpd_syscontact snmpd_syslocation snmpd_v3_auth_type; do
    printf "%s=%s\n" "$k" "$(nvram get $k)"
  done
' > "$snap/before.nvram"

echo "[snmp] applying values (LAN-only, community=<set>)"
rssh "
  nvram set snmpd_enable=1
  nvram set snmpd_wan=0
  nvram set snmpd_community=$SNMP_COMMUNITY
  nvram set snmpd_rocommunity=$SNMP_COMMUNITY
  nvram set snmpd_rwcommunity=
  nvram set snmpd_sysname=$(rssh 'nvram get productid')
  nvram set snmpd_syscontact=warroom
  nvram set snmpd_syslocation=home
  nvram commit
  service start_snmpd 2>&1 | head -5
  sleep 1
  ps w | grep -E 'snmpd' | grep -v grep | head -3
  echo --- listening sockets ---
  netstat -ulnp 2>/dev/null | grep ':161 '
"

echo
echo "[snmp] capturing after-state"
rssh '
  for k in snmpd_enable snmpd_wan snmpd_community snmpd_rocommunity snmpd_rwcommunity \
           snmpd_sysname snmpd_syscontact snmpd_syslocation snmpd_v3_auth_type; do
    printf "%s=%s\n" "$k" "$(nvram get $k)"
  done
' > "$snap/after.nvram"

echo "[snmp] diff:"
diff -u "$snap/before.nvram" "$snap/after.nvram" | sed 's/^/  /' || true

echo
echo "[snmp] smoke test from warroom (via snmp-exporter image's snmpget if available, else docker run)"
if command -v snmpget >/dev/null 2>&1; then
  snmpget -v2c -c "$SNMP_COMMUNITY" -t 3 192.168.100.1 1.3.6.1.2.1.1.1.0
else
  docker run --rm --network warroom_default polinux/snmpd:alpine snmpget \
    -v2c -c "$SNMP_COMMUNITY" -t 3 192.168.100.1 1.3.6.1.2.1.1.1.0 2>&1 || \
  echo "[snmp] (install snmp-utils for local smoke-test; will verify via Prometheus instead)"
fi
