#!/usr/bin/env bash
# Tail router syslog. Optional grep filter.
# Usage: syslog-tail.sh [pattern]
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

PATTERN="${1:-.}"
rssh "tail -F /tmp/syslog.log 2>/dev/null | grep --line-buffered -E '$PATTERN'"
