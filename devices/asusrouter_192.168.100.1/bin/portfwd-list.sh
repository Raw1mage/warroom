#!/usr/bin/env bash
# List active DNAT rules and their packet/byte counters.
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

rssh_script <<'SH'
echo "===== vts_rulelist (configured) ====="
nvram get vts_rulelist | tr '<' '\n' | awk -F'>' 'NF>=4 {printf "  %-12s %-18s -> %-18s proto=%s\n",$1,$2,$3":"($4==""?$2:$4),$5}'
echo
echo "===== iptables VSERVER (active DNAT + counters) ====="
iptables -t nat -L VSERVER -nv --line-numbers
SH
