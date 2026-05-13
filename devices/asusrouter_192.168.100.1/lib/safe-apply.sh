#!/usr/bin/env bash
# Safe iptables-rule applicator with on-router auto-rollback timer.
#
# Pattern:
#   1) snapshot iptables state to snapshots/<ts>/before.rules
#   2) idempotency check (skip if rule already exists)
#   3) arm a sleep-then-delete background job ON the router (auto-rollback)
#   4) install the rule
#   5) verify the rule exists from an INDEPENDENT ssh session + sanity-check
#      the router is still reachable
#   6) on success, disarm the rollback
#   7) write snapshots/<ts>/after.rules and print unified diff
#
# Worst case (verify fails, our process dies, ssh dies): the rollback fires
# on the router itself after $ROLLBACK_TIMEOUT seconds and the rule is gone
# with zero warroom-side action needed.
#
# This library only EVER applies rules with the targets allowed via the
# ALLOWED_TARGETS allow-list. Anything else aborts.
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ssh.sh"

ROLLBACK_TIMEOUT="${ROLLBACK_TIMEOUT:-120}"
ALLOWED_TARGETS=( LOG DROP )

# is_allowed_target <target>
is_allowed_target() {
  local t="$1"
  for a in "${ALLOWED_TARGETS[@]}"; do [ "$t" = "$a" ] && return 0; done
  return 1
}

# apply_router_rule_with_rollback <table> <chain> <action> <rule_body> [tag]
#   action     : -I (insert at top) or -A (append)
#   rule_body  : everything after "-A CHAIN", e.g. "-i ppp0 -p tcp --dport 2122 -j LOG --log-prefix WSLSSH-"
#                MUST end with "-j <ALLOWED_TARGET> ..."
#   tag        : human label for snapshots dir
apply_router_rule_with_rollback() {
  local table="$1" chain="$2" action="$3" rule_body="$4" tag="${5:-rule}"

  case "$action" in -I|-A) ;; *) echo "action must be -I or -A" >&2; return 2 ;; esac

  # extract -j TARGET for allow-list check
  local target
  target="$(printf '%s\n' "$rule_body" | awk '{for(i=1;i<=NF;i++) if($i=="-j"){print $(i+1); exit}}')"
  if ! is_allowed_target "$target"; then
    echo "[safe-apply] REFUSED: target '$target' not in allow-list (${ALLOWED_TARGETS[*]})" >&2
    return 3
  fi

  local ts; ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local snap="$DEVICE_DIR/snapshots/${ts}_${tag}"
  mkdir -p "$snap"
  echo "[safe-apply] snapshot dir: $snap"
  rssh "iptables-save"  > "$snap/before.rules"

  # idempotency: if rule already exists, no-op
  if rssh "iptables -t $table -C $chain $rule_body" 2>/dev/null; then
    echo "[safe-apply] rule already present, nothing to do"
    cp "$snap/before.rules" "$snap/after.rules"
    return 0
  fi

  echo "[safe-apply] arming on-router rollback timer (${ROLLBACK_TIMEOUT}s) + installing rule"
  # Single round-trip: arm timer then install. If install fails, timer still
  # safely fires a no-op (the -D won't match anything).
  rssh "
    ( sleep $ROLLBACK_TIMEOUT; iptables -t $table -D $chain $rule_body 2>/dev/null ) </dev/null >/dev/null 2>&1 &
    echo \$! > /tmp/warroom-rollback.pid
    iptables -t $table $action $chain $rule_body
  "

  echo "[safe-apply] verifying from a fresh ssh session..."
  local ok=1
  if ! rssh "iptables -t $table -C $chain $rule_body" 2>/dev/null; then
    echo "[safe-apply]   FAIL: rule not present after install" >&2; ok=0
  fi
  if ! rssh "nvram get productid >/dev/null"; then
    echo "[safe-apply]   FAIL: router unresponsive on independent session" >&2; ok=0
  fi

  if [ $ok -eq 1 ]; then
    echo "[safe-apply] verify OK — disarming rollback"
    rssh "kill \$(cat /tmp/warroom-rollback.pid 2>/dev/null) 2>/dev/null; rm -f /tmp/warroom-rollback.pid"
  else
    echo "[safe-apply] verify FAILED — leaving rollback armed; rule will self-destruct within ${ROLLBACK_TIMEOUT}s"
    return 4
  fi

  rssh "iptables-save" > "$snap/after.rules"
  echo "[safe-apply] diff:"
  diff -u "$snap/before.rules" "$snap/after.rules" | sed 's/^/  /' || true
  echo "[safe-apply] done"
}

# remove_router_rule <table> <chain> <rule_body> [tag]
remove_router_rule() {
  local table="$1" chain="$2" rule_body="$3" tag="${4:-rule}"
  local ts; ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local snap="$DEVICE_DIR/snapshots/${ts}_${tag}_unset"
  mkdir -p "$snap"
  rssh "iptables-save" > "$snap/before.rules"
  if ! rssh "iptables -t $table -C $chain $rule_body" 2>/dev/null; then
    echo "[safe-apply] rule not present — nothing to remove"
    return 0
  fi
  rssh "iptables -t $table -D $chain $rule_body"
  rssh "iptables-save" > "$snap/after.rules"
  echo "[safe-apply] removed. diff:"
  diff -u "$snap/before.rules" "$snap/after.rules" | sed 's/^/  /' || true
}
