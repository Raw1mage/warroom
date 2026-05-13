# asusrouter_192.168.100.1 — zero-intrusion remote control + fail2ban

ASUS RT-AX86U at `192.168.100.1`. All scripts run **locally on warroom**, SSH
into the router, execute a command, and capture output. Read-only by default;
mutations go through `lib/safe-apply.sh` (snapshot + on-router rollback timer
+ independent verify).

## Layout

```
config.env                  host/user/key, WHITELIST_RE, WHITELIST_EXTRA
lib/
  ssh.sh                    rssh / rssh_script wrappers
  safe-apply.sh             apply_router_rule_with_rollback (LOG / DROP only)
  whitelist.sh              is_whitelisted (RFC1918 + user-extra)
bin/
  audit.sh                  read-only full exposure audit
  portfwd-list.sh           configured port forwards + live counters
  conntrack-port.sh         live src-IP enumeration for a WAN port
  syslog-tail.sh            tail router /tmp/syslog.log, optional grep
  snapshot.sh               full forensic dump -> snapshots/<ts>/

  # fail2ban toolkit
  iptables-log-set.sh       install WSLSSH LOG rule (one-shot)
  iptables-log-unset.sh     remove WSLSSH LOG rule
  persistence-set.sh        install /jffs/scripts/firewall-start (survives reboot)
  persistence-unset.sh      remove   /jffs/scripts/firewall-start
  syslog-stream.sh          run by systemd: poll rawdb DB -> state/router-stream.log
  ban-set.sh   <ip>         ban attacker IP (raw/PREROUTING DROP)
  ban-unset.sh <ip>         unban
  ban-list.sh               state (truth) vs router (reality)
  fail2ban-tick.sh          cron tick: scan stream, ban/expire

state/
  router-stream.log         live syslog stream from rawdb (gitignored)
  last-id                   SQLite poll cursor
  banned.json               truth source for active bans + expiry
snapshots/                  iptables before/after dumps (gitignored)
known_hosts                 pinned host key (gitignored)
```

## fail2ban architecture

```
ASUS router (192.168.100.1)
  ├─ iptables -t mangle -A PREROUTING -i ppp0 ... -j LOG --log-prefix WSLSSH-
  │    (installed by iptables-log-set.sh, persisted via /jffs/scripts/firewall-start)
  ├─ syslogd -R 192.168.100.40:514  (push UDP 514)
  └─ iptables -t raw -A PREROUTING -i ppp0 -s <attacker> -j DROP
       (installed by ban-set.sh, deduplicated by warroom state)
                                  │
                                  ▼  udp 514
rawdb (192.168.100.40)
  └─ Synology Log Center syslog-ng
       └─ SQLite: /volume1/NetBackup/<HOST>/SYNOSYSLOGDB_<HOST>.DB
                                  │
                                  ▼  ssh poll every 2s (systemd unit warroom-asusrouter-tail)
warroom (this dir)
  ├─ state/router-stream.log     pipe-separated rows
  ├─ docker compose asusrouter-log-shipper  alloy parse -> loki
  ├─ cron */1 *  fail2ban-tick.sh
  │    └─ awk window scan -> ban-set.sh / ban-unset.sh via ssh
  └─ grafana dashboard "asusrouter-fail2ban" (uid: asusrouter-fail2ban)
```

## Onboarding (host-side prerequisites)

```bash
# 1. install systemd ssh-poll service
systemctl --user enable --now warroom-asusrouter-tail.service

# 2. install router LOG rule + persistence
bin/iptables-log-set.sh
bin/persistence-set.sh

# 3. bring up alloy shipper to loki
cd ~/projects/warroom && docker compose --profile asusrouter-logs up -d

# 4. install cron (every minute)
crontab -l | grep -v fail2ban-tick; \
( crontab -l 2>/dev/null; echo '* * * * * /home/pkcs12/projects/warroom/devices/asusrouter_192.168.100.1/bin/fail2ban-tick.sh >> $HOME/.local/state/warroom-fail2ban.log 2>&1' ) | crontab -

# 5. dashboard: http://localhost:3000/warroom/d/asusrouter-fail2ban
```

## Tuning

Edit `config.env`:
- `WHITELIST_RE` regex — anything matching is **never** banned (RFC1918 by default)
- `WHITELIST_EXTRA` space-separated exact IPs

Override via env when invoking `fail2ban-tick.sh`:
- `WINDOW_SEC` (default 600) — look-back window for SYN tally
- `THRESHOLD` (default 5) — SYNs in window → ban
- `TTL_SEC` (default 3600) — ban duration

## Conventions

- **Read-only by default.** Any script that mutates router state must be
  named `*-set.sh` / `*-apply.sh` and prompt for confirmation.
- All connection params live in `config.env`. No flags on the command line.
- Scripts source `lib/ssh.sh` to get `rssh` (one-shot) and `rssh_script`
  (heredoc). Never `scp` anything onto the router.
- Output is plain text on stdout — pipe-friendly, no colors, no spinners.

## Usage

```bash
cd ~/projects/warroom/devices/asusrouter_192.168.100.1
bin/audit.sh                          # full exposure audit
bin/portfwd-list.sh                   # forwards + DNAT counters
bin/conntrack-port.sh 2122            # current sessions hitting WAN 2122
bin/conntrack-port.sh 2122 --watch 3  # poll every 3s
bin/syslog-tail.sh 'DROP|wslssh'      # follow router log filtered
bin/snapshot.sh                       # forensic capture for diffing later
```

## Adding a new function

1. New file under `bin/`, `chmod +x`.
2. First two lines:
   ```bash
   set -euo pipefail
   source "$(dirname "$0")/../lib/ssh.sh"
   ```
3. Use `rssh '…'` for one-liners or `rssh_script <<'SH' … SH` for blocks.
4. If it mutates state, name it `*-set.sh`, snapshot before mutating, and
   print a clear diff on exit.
