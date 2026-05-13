#!/usr/bin/env bash
# Install a LOG-only iptables rule that logs every SYN to the wslssh
# forwarded port. Protected by safe-apply (snapshot + on-router rollback timer
# + independent verify).
#
# Rule is intentionally non-persistent: router reboot wipes it. Re-run this
# script after reboot if needed.
set -euo pipefail
source "$(dirname "$0")/../lib/safe-apply.sh"

# wslssh = the WAN-side port forward of WSL ssh, see audit.sh output.
PORT=2122
PREFIX="WSLSSH-"          # no space — survives multi-shell quoting

# Rule body. Targets allowed by safe-apply: LOG, DROP (LOG used here).
RULE_BODY="-i $WAN_IFACE -p tcp --dport $PORT -m conntrack --ctstate NEW -j LOG --log-prefix $PREFIX --log-level 6"

apply_router_rule_with_rollback mangle PREROUTING -I "$RULE_BODY" "log-wslssh"
