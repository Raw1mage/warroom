#!/usr/bin/env bash
# One cron tick: scan attackers that show up across multiple Loki channels
# (ssh / nginx / mail) and ban them earlier than any single-channel tick would.
#
# Trigger: any IP with ≥ MIN_PER_CHANNEL *failure* events in ≥ MIN_CHANNELS distinct
# channels inside the last WINDOW_SEC seconds. Default 3/2.
# Each channel query only counts failure/reject events, not all connections.
#
# Cron entry:
#   * * * * *  .../bin/fail2ban-correlation-tick.sh >> $HOME/.local/state/warroom-fail2ban-corr.log 2>&1
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"
source "$(dirname "$0")/../lib/whitelist.sh"

LOKI_URL="${LOKI_URL:-http://localhost:3100}"
STATE="$DEVICE_DIR/state/banned.json"
WINDOW_SEC="${WINDOW_SEC:-1800}"          # 30 min
MIN_PER_CHANNEL="${MIN_PER_CHANNEL:-3}"   # failure events per channel (raised from 2; queries now only count failures)
MIN_CHANNELS="${MIN_CHANNELS:-2}"         # channels hit
TTL_SEC="${TTL_SEC:-14400}"               # 4 hours (longer than per-channel since cross-signal = higher confidence)

mkdir -p "$(dirname "$STATE")"
[ -f "$STATE" ] || echo '{}' > "$STATE"

# Query each channel for top src_ip counts.
fetch() {
  local q="$1"
  curl -s -G "$LOKI_URL/loki/api/v1/query" --data-urlencode "query=$q" 2>/dev/null \
    | jq -r '.data.result[]? | "\(.value[1]) \(.metric.src_ip)"' 2>/dev/null
}

# Each query must only count FAILURE events, not all connections.
# SSH: WSLSSH- kernel log = all SYN attempts — this is fine, SSH SYN flood is the signal.
SSH_Q="sum by (src_ip) (count_over_time({job=\"asus-router\", prog=\"kernel\"} |= \`WSLSSH-\` | regexp \`SRC=(?P<src_ip>[\\d.]+)\` [${WINDOW_SEC}s]))"
# Nginx: only count 4xx/5xx error responses that indicate probing/attacks, not benign 404s.
# Match lines like "access forbidden", "no user/password", "SSL_do_handshake() failed",
# "limiting requests", "directory index of" (dir traversal attempt).
NGINX_Q="sum by (src_ip) (count_over_time({job=\"rawdb-nginx\"} |~ \`(access forbidden|auth.*failed|SSL_do_handshake.*failed|limiting requests|directory index)\` | regexp \`client: (?P<src_ip>[\\d.]+)\` [${WINDOW_SEC}s]))"
# Mail: only auth failures + postscreen rejects — aligned with fail2ban-mail-tick.sh.
MAIL_Q="sum by (src_ip) (count_over_time({job=\"rawdb-mail\"} |~ \`(auth failed|HANGUP|PREGREET|BARE NEWLINE|COMMAND PIPELINING)\` | regexp \`(?:from \\[|rip=)(?P<src_ip>[\\d.]+)\` [${WINDOW_SEC}s]))"

declare -A ssh_cnt nginx_cnt mail_cnt
while read -r c ip; do [ -n "$ip" ] && ssh_cnt[$ip]="$c"; done < <(fetch "$SSH_Q")
while read -r c ip; do [ -n "$ip" ] && nginx_cnt[$ip]="$c"; done < <(fetch "$NGINX_Q")
while read -r c ip; do [ -n "$ip" ] && mail_cnt[$ip]="$c"; done < <(fetch "$MAIL_Q")

# Union of IPs
declare -A all_ips
for ip in "${!ssh_cnt[@]}";   do all_ips[$ip]=1; done
for ip in "${!nginx_cnt[@]}"; do all_ips[$ip]=1; done
for ip in "${!mail_cnt[@]}";  do all_ips[$ip]=1; done

# For each IP, count channels with ≥ MIN_PER_CHANNEL hits
for ip in "${!all_ips[@]}"; do
  # filter out empty / null / non-IPv4 (LogQL `sum by (src_ip)` emits these
  # when the regex did not match; banning them is meaningless)
  [ -z "$ip" ] || [ "$ip" = "null" ] && continue
  case "$ip" in *[!0-9.]*) continue ;; esac
  if is_whitelisted "$ip"; then continue; fi
  channels=0; total=0; reason_parts=()
  for ch_var_name in ssh_cnt nginx_cnt mail_cnt; do
    declare -n ch_map="$ch_var_name"
    v=${ch_map[$ip]:-0}
    total=$((total + v))
    if [ "$v" -ge "$MIN_PER_CHANNEL" ]; then
      channels=$((channels + 1))
      reason_parts+=("${ch_var_name%_cnt}:$v")
    fi
  done
  if [ "$channels" -ge "$MIN_CHANNELS" ]; then
    if jq -e --arg ip "$ip" '.[$ip]' "$STATE" >/dev/null 2>&1; then continue; fi
    reason="cross-channel(${reason_parts[*]})"
    echo "[$(date '+%F %T')] ban: $ip channels=$channels total=$total $reason"
    BAN_REASON="$reason" TTL_SEC="$TTL_SEC" "$DEVICE_DIR/bin/ban-set.sh" "$ip" || true
  fi
done
