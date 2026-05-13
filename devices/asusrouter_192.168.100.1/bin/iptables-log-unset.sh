#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/safe-apply.sh"

PORT=2122
PREFIX="WSLSSH-"
RULE_BODY="-i $WAN_IFACE -p tcp --dport $PORT -m conntrack --ctstate NEW -j LOG --log-prefix $PREFIX --log-level 6"

remove_router_rule mangle PREROUTING "$RULE_BODY" "log-wslssh"
