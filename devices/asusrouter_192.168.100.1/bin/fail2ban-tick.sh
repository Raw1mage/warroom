#!/usr/bin/env bash
# One cron tick: scan recent router log stream, ban offenders, expire old bans.
#
# Cron entry (every minute):
#   * * * * *  /home/pkcs12/projects/warroom/devices/asusrouter_192.168.100.1/bin/fail2ban-tick.sh >> ~/.local/state/warroom-fail2ban.log 2>&1
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"
source "$(dirname "$0")/../lib/whitelist.sh"

STREAM="$DEVICE_DIR/state/router-stream.log"
STATE="$DEVICE_DIR/state/banned.json"
WINDOW_SEC="${WINDOW_SEC:-600}"      # look back 10 min
THRESHOLD="${THRESHOLD:-5}"          # 5 SYNs in window = ban
TTL_SEC="${TTL_SEC:-3600}"           # ban 1 hour

mkdir -p "$(dirname "$STATE")"
[ -f "$STATE" ] || echo '{}' > "$STATE"
[ -f "$STREAM" ] || { echo "no stream file yet"; exit 0; }

NOW=$(date +%s)
SINCE=$((NOW - WINDOW_SEC))

# 1) Expire old bans + stale grace entries
# Active bans past expires_at -> remove rule via ban-unset (which writes a grace)
expired_ips=$(jq -r --argjson now "$NOW" \
  'to_entries[] | select(.value.expires_at and (.value.expires_at <= $now) and (.value.suppressed | not)) | .key' "$STATE")
for ip in $expired_ips; do
  echo "[$(date '+%F %T')] expiring ban: $ip"
  "$DEVICE_DIR/bin/ban-unset.sh" "$ip" || true
done
# Grace entries past grace_until -> fully remove from state (events have aged out)
stale_grace=$(jq -r --argjson now "$NOW" \
  'to_entries[] | select(.value.suppressed == true and .value.grace_until <= $now) | .key' "$STATE")
for ip in $stale_grace; do
  echo "[$(date '+%F %T')] clearing grace: $ip"
  tmp="$(mktemp)"; jq --arg ip "$ip" 'del(.[$ip])' "$STATE" > "$tmp" && mv "$tmp" "$STATE"
done

# 2) Tally WSLSSH- SYNs by SRC in window
#    Stream lines look like:
#    1500|1778678009|kernel|info|WSLSSH-IN=ppp0 ... SRC=213.209.159.225 ... DPT=2122 ... SYN
offenders=$(awk -F'|' -v since="$SINCE" '
  $2 >= since && $3 == "kernel" && $5 ~ /WSLSSH-/ {
    if (match($5, /SRC=[0-9.]+/)) {
      ip = substr($5, RSTART+4, RLENGTH-4)
      cnt[ip]++
    }
  }
  END { for (ip in cnt) print cnt[ip], ip }
' "$STREAM" | sort -rn)

# 3) Issue bans for IPs over threshold not already banned (whitelist-aware)
echo "$offenders" | while read -r count ip; do
  [ -z "$ip" ] && continue
  if is_whitelisted "$ip"; then
    continue
  fi
  if [ "$count" -ge "$THRESHOLD" ]; then
    if jq -e --arg ip "$ip" '.[$ip]' "$STATE" >/dev/null 2>&1; then
      :  # already banned
    else
      echo "[$(date '+%F %T')] ban: $ip ($count SYNs in ${WINDOW_SEC}s)"
      BAN_REASON="ssh" TTL_SEC="$TTL_SEC" "$DEVICE_DIR/bin/ban-set.sh" "$ip" || true
    fi
  fi
done

# 4) State file housekeeping: trim stream file if > 10MB to keep awk fast
size=$(stat -c%s "$STREAM" 2>/dev/null || echo 0)
if [ "$size" -gt 10485760 ]; then
  tail -n 5000 "$STREAM" > "$STREAM.tmp" && mv "$STREAM.tmp" "$STREAM"
fi
