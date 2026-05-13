#!/usr/bin/env bash
# Disable SNMP on the router. Stops service and clears community string.
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

rssh '
  service stop_snmpd 2>&1 | head -3
  nvram set snmpd_enable=0
  nvram set snmpd_community=
  nvram set snmpd_rocommunity=
  nvram set snmpd_rwcommunity=
  nvram commit
  echo "[snmp-unset] state:"
  nvram get snmpd_enable
'
