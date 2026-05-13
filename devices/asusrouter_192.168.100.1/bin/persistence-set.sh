#!/usr/bin/env bash
# Install /jffs/scripts/firewall-start on the router so the WSLSSH LOG rule
# survives reboot. The script is idempotent (uses iptables -C before -I), so
# it's safe to be triggered repeatedly by every firewall-restart event.
#
# Upload uses openssl base64 round-trip (no scp; nothing else written).
# Pair: persistence-unset.sh removes the file.
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

read -r -d '' SCRIPT_CONTENT <<'EOF' || true
#!/bin/sh
# Managed by warroom: do not edit by hand.
# Re-installs the WSLSSH log rule on every firewall (re)apply.
RULE='-i ppp0 -p tcp --dport 2122 -m conntrack --ctstate NEW -j LOG --log-prefix WSLSSH- --log-level 6'
iptables -t mangle -C PREROUTING $RULE 2>/dev/null || iptables -t mangle -I PREROUTING $RULE
EOF

B64="$(printf '%s\n' "$SCRIPT_CONTENT" | openssl base64 -A)"

rssh "
  echo $B64 | openssl base64 -A -d > /jffs/scripts/firewall-start &&
  chmod 755 /jffs/scripts/firewall-start &&
  echo '--- /jffs/scripts/firewall-start now is: ---' &&
  cat /jffs/scripts/firewall-start
"

echo
echo "[persistence-set] installed. Trigger now to verify hook runs cleanly:"
rssh "/jffs/scripts/firewall-start && iptables -t mangle -L PREROUTING -nv | grep WSLSSH"
