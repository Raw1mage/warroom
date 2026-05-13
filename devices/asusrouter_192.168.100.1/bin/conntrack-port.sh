#!/usr/bin/env bash
# Live conntrack source-IPs hitting a given WAN port. Read-only.
# Usage: conntrack-port.sh <port> [--watch [interval_s]]
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

PORT="${1:?usage: $0 <port> [--watch [interval]]}"
shift || true
MODE="once"
INTERVAL=2
if [ "${1:-}" = "--watch" ]; then MODE="watch"; INTERVAL="${2:-2}"; fi

snapshot() {
  # Conntrack rows have two halves (original + reply direction).
  # We want the ORIGINAL src/dport, i.e. the first match in the row.
  rssh "
    ( cat /proc/net/nf_conntrack 2>/dev/null || cat /proc/net/ip_conntrack 2>/dev/null ) \
      | awk -v p=$PORT '
          index(\$0,\"dport=\"p\" \") {
            src=\"\"; dport=\"\"; sport=\"\"; state=\"\"
            for(i=1;i<=NF;i++){
              if(src==\"\"  && \$i~/^src=/)   src=\$i
              if(sport==\"\" && \$i~/^sport=/) sport=\$i
              if(dport==\"\" && \$i~/^dport=/) dport=\$i
              if(\$i~/^ESTABLISHED|^SYN_|^TIME_WAIT|^CLOSE|^FIN_WAIT|^LAST_ACK/) state=\$i
            }
            printf \"%-14s %-22s %-12s -> %s\\n\", state, src, sport, dport
          }'
  "
}

if [ "$MODE" = "once" ]; then
  echo "# conntrack snapshot for dport=$PORT"
  snapshot
else
  echo "# watching dport=$PORT every ${INTERVAL}s (Ctrl-C to stop)"
  while true; do
    printf '\n--- %s ---\n' "$(date '+%H:%M:%S')"
    snapshot
    sleep "$INTERVAL"
  done
fi
