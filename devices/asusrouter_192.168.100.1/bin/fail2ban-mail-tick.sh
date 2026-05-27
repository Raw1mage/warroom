#!/usr/bin/env bash
# One cron tick: scan recent Loki rawdb-mail events, ban brute-force IPs,
# expire old bans. Shares the same router-side raw/PREROUTING DROP infra
# as fail2ban-tick.sh — bans are mutually deduplicated via state/banned.json.
#
# Two attack signals counted toward the same threshold:
#   - dovecot   `auth failed`     IMAP/POP3 brute force, source IP = rip=...
#   - postscreen REJECT/HANGUP/PREGREET/BARE NEWLINE/COMMAND PIPELINING
#                                 pre-greet bot detection, source IP = from [...]
#
# Cron entry:
#   * * * * *  /home/pkcs12/projects/warroom/devices/asusrouter_192.168.100.1/bin/fail2ban-mail-tick.sh >> ~/.local/state/warroom-fail2ban-mail.log 2>&1
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"
source "$(dirname "$0")/../lib/whitelist.sh"

LOKI_URL="${LOKI_URL:-http://localhost:3100}"
STATE="$DEVICE_DIR/state/banned.json"
WINDOW_SEC="${WINDOW_SEC:-600}"
THRESHOLD="${THRESHOLD:-5}"
TTL_SEC="${TTL_SEC:-3600}"

mkdir -p "$(dirname "$STATE")"
[ -f "$STATE" ] || echo '{}' > "$STATE"

# 1) Expire old bans + stale grace entries (shared with ssh fail2ban)
NOW=$(date +%s)
expired=$(jq -r --argjson now "$NOW" \
  'to_entries[] | select(.value.expires_at and (.value.expires_at <= $now) and (.value.suppressed | not)) | .key' "$STATE")
for ip in $expired; do
  echo "[$(date '+%F %T')] expiring ban: $ip"
  "$DEVICE_DIR/bin/ban-unset.sh" "$ip" || true
done
stale_grace=$(jq -r --argjson now "$NOW" \
  'to_entries[] | select(.value.suppressed == true and .value.grace_until <= $now) | .key' "$STATE")
for ip in $stale_grace; do
  echo "[$(date '+%F %T')] clearing grace: $ip"
  tmp="$(mktemp)"; jq --arg ip "$ip" 'del(.[$ip])' "$STATE" > "$tmp" && mv "$tmp" "$STATE"
done

# 2) Tally offenders via LogQL.
# Dovecot brute force: parse rip=<ip>
dove_resp=$(curl -s -G "$LOKI_URL/loki/api/v1/query" --data-urlencode "query=topk(50, sum by (client_ip) (count_over_time({job=\"rawdb-mail\", program=\"dovecot\"} |= \`auth failed\` | regexp \`rip=(?P<client_ip>[\\d.]+)\` [${WINDOW_SEC}s])))" 2>/dev/null)
# Postscreen rejects: parse from [<ip>]
post_resp=$(curl -s -G "$LOKI_URL/loki/api/v1/query" --data-urlencode "query=topk(50, sum by (client_ip) (count_over_time({job=\"rawdb-mail\", program=\"postfix/postscreen\"} |~ \`HANGUP|PREGREET|BARE NEWLINE|COMMAND PIPELINING\` | regexp \`from \\[(?P<client_ip>[\\d.]+)\\]\` [${WINDOW_SEC}s])))" 2>/dev/null)

declare -A counts
add_counts() {
  local resp="$1"
  while read -r line; do
    [ -z "$line" ] && continue
    cnt=$(echo "$line" | awk '{print $1}')
    ip=$(echo "$line"  | awk '{print $2}')
    [ -z "$ip" ] && continue
    counts[$ip]=$((${counts[$ip]:-0} + cnt))
  done < <(echo "$resp" | jq -r '.data.result[]? | "\(.value[1]) \(.metric.client_ip)"' 2>/dev/null)
}
add_counts "$dove_resp"
add_counts "$post_resp"

# 3) Ban any offender over threshold not already banned (and not whitelisted)
for ip in "${!counts[@]}"; do
  cnt=${counts[$ip]}
  if is_whitelisted "$ip"; then continue; fi
  if [ "$cnt" -lt "$THRESHOLD" ]; then continue; fi
  if jq -e --arg ip "$ip" '.[$ip]' "$STATE" >/dev/null 2>&1; then continue; fi
  echo "[$(date '+%F %T')] ban: $ip ($cnt mail events in ${WINDOW_SEC}s)"
  BAN_REASON="mail" TTL_SEC="$TTL_SEC" "$DEVICE_DIR/bin/ban-set.sh" "$ip" || true
done
