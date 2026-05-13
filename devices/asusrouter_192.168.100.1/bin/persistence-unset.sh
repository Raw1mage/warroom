#!/usr/bin/env bash
# Remove the warroom-managed /jffs/scripts/firewall-start.
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

rssh '
  if [ -f /jffs/scripts/firewall-start ]; then
    rm -f /jffs/scripts/firewall-start && echo "[persistence-unset] removed"
  else
    echo "[persistence-unset] not present"
  fi
'
