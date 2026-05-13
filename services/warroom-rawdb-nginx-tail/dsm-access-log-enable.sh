#!/usr/bin/env bash
# Enable DSM nginx access logging on the reverse-proxy vhosts.
#
# Two-piece install:
#   1) /etc/nginx/conf.d/http.warroom-access-log.conf
#      Defines the `warroom_combined` log_format at http context.
#      Persists across most DSM operations (conf.d files are not regenerated).
#   2) /etc/nginx/sites-enabled/server.ReverseProxy.conf
#      Inject `access_log ...` at server level after every server_name line.
#      DSM auto-regenerates this file when you edit reverse proxy entries via
#      DSM UI — re-run this script after any such edit. (See -reapply mode.)
#
# Idempotent.  Revert via dsm-access-log-disable.sh.
set -euo pipefail

CONF_PATH=/etc/nginx/conf.d/http.warroom-access-log.conf
RP_PATH=/etc/nginx/sites-enabled/server.ReverseProxy.conf
LOG_PATH=/var/log/nginx/warroom-access.log

LOG_FORMAT=$(cat <<'NGX'
# Warroom: log_format used by server-level access_log directives injected
# into server.ReverseProxy.conf. The log file itself is owned http:http so
# nginx workers can write it.

log_format warroom_combined
    '$remote_addr - $remote_user [$time_local] '
    '"$request" $status $body_bytes_sent '
    '"$http_referer" "$http_user_agent" '
    '"$http_x_forwarded_for" '
    'rt=$request_time uct=$upstream_connect_time uht=$upstream_header_time urt=$upstream_response_time '
    'host=$host';
NGX
)

ssh -o BatchMode=yes -i "$HOME/.ssh/id_ed25519" yeatsluo@192.168.100.40 "
set -e

echo '[enable] (1/3) write log_format conf'
printf '%s\n' \"\$(cat <<'CONF_EOF'
$LOG_FORMAT
CONF_EOF
)\" | sudo tee $CONF_PATH >/dev/null
sudo chmod 644 $CONF_PATH

echo '[enable] (2/3) ensure log file exists, owned http:http'
sudo touch $LOG_PATH
sudo chown http:http $LOG_PATH
sudo chmod 640 $LOG_PATH

echo '[enable] (3/3) inject server-level access_log into ReverseProxy.conf (idempotent)'
sudo cp $RP_PATH ${RP_PATH}.bak-warroom-pre-enable-\$(date +%Y%m%d-%H%M%S)
sudo python3 <<'PY'
import re
p = '$RP_PATH'
with open(p) as f: txt = f.read()
inject = '    access_log /var/log/nginx/warroom-access.log warroom_combined;'
if inject in txt:
    print('  already injected')
else:
    # Add access_log line immediately after every \"server_name X.Y.Z ;\" line.
    pattern = re.compile(r'(server_name [^;]+;)')
    new = pattern.sub(r'\\1\n' + inject, txt)
    with open(p,'w') as f: f.write(new)
    print('  added to', new.count('warroom-access'), 'server blocks')
PY

echo '[enable] nginx -t + graceful reload'
sudo nginx -t 2>&1 | grep -vE 'warn|conflicting|low address' | tail -3
sudo nginx -s reload 2>&1 | grep -vE 'warn|conflicting|low address' || true

echo '[enable] done. log file:'
sudo ls -la $LOG_PATH
"
