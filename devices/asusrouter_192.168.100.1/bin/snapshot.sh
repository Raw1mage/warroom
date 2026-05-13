#!/usr/bin/env bash
# Capture a forensic snapshot of router state to snapshots/<UTC-ts>/.
# Read-only on the router; writes only locally.
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEVICE_DIR/snapshots/$TS"
mkdir -p "$OUT"
echo "# capturing to $OUT"

rssh 'nvram show 2>/dev/null'                        > "$OUT/nvram.txt"
rssh 'iptables-save 2>/dev/null'                     > "$OUT/iptables.rules"
rssh 'iptables -t nat -L -nv --line-numbers'         > "$OUT/iptables-nat.txt"
rssh 'iptables -L -nv --line-numbers'                > "$OUT/iptables-filter.txt"
rssh 'netstat -tlnp 2>/dev/null'                     > "$OUT/listen-sockets.txt"
rssh 'cat /proc/net/nf_conntrack 2>/dev/null || cat /proc/net/ip_conntrack 2>/dev/null' > "$OUT/conntrack.txt"
rssh 'tail -n 500 /tmp/syslog.log 2>/dev/null'       > "$OUT/syslog.tail.txt"

echo "# done. size:"
du -sh "$OUT"
