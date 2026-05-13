#!/usr/bin/env bash
# is_whitelisted <ip> -> returns 0 if whitelisted, 1 otherwise.
# Sourced by ban-set.sh and fail2ban-tick.sh.
# Depends on config.env having been sourced (provides WHITELIST_RE,
# WHITELIST_EXTRA).
is_whitelisted() {
  local ip="$1"
  [ -z "$ip" ] && return 1
  if [ -n "${WHITELIST_RE:-}" ] && printf '%s' "$ip" | grep -qE "$WHITELIST_RE"; then
    return 0
  fi
  local x
  for x in ${WHITELIST_EXTRA:-}; do
    [ "$ip" = "$x" ] && return 0
  done
  return 1
}
