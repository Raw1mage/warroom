#!/usr/bin/env bash
# Revert dsm-access-log-enable.sh fully.
set -euo pipefail
CONF_PATH=/etc/nginx/conf.d/http.warroom-access-log.conf
RP_PATH=/etc/nginx/sites-enabled/server.ReverseProxy.conf

ssh -o BatchMode=yes -i "$HOME/.ssh/id_ed25519" yeatsluo@192.168.100.40 "
set -e
[ -f $CONF_PATH ] && sudo rm -f $CONF_PATH && echo '[disable] removed $CONF_PATH'
sudo python3 <<'PY'
p = '$RP_PATH'
with open(p) as f: txt = f.read()
new = '\n'.join(line for line in txt.split('\n') if 'warroom-access.log warroom_combined' not in line)
if new != txt:
    with open(p,'w') as f: f.write(new)
    print('[disable] removed access_log lines from server.ReverseProxy.conf')
else:
    print('[disable] no access_log lines present')
PY
sudo nginx -t 2>&1 | tail -3 && sudo nginx -s reload 2>&1 | grep -vE 'warn|conflicting|low address' || true
"
