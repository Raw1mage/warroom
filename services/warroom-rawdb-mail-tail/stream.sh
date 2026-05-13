#!/usr/bin/env bash
# Long-running ssh-tail of rawdb's journald for mail-related programs
# (postfix/* and dovecot/*). Writes one line per event to a host file
# that the alloy compose service tails.
set -euo pipefail
DEVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DEVICE_DIR/state/mail-stream.log"
mkdir -p "$(dirname "$OUT")"; touch "$OUT"
# `-f` follow, `-o short-iso` ISO timestamps + identifier, exit-on-error.
# Filter by SYSLOG_IDENTIFIER matching mail components.
exec ssh \
  -o BatchMode=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=accept-new \
  -i "$HOME/.ssh/id_ed25519" \
  yeatsluo@192.168.100.40 \
  "sudo journalctl -f -o short-iso -n 0 \
       SYSLOG_IDENTIFIER=postfix/postscreen \
       SYSLOG_IDENTIFIER=postfix/smtpd \
       SYSLOG_IDENTIFIER=postfix/dnsblog \
       SYSLOG_IDENTIFIER=postfix/tlsmgr \
       SYSLOG_IDENTIFIER=postfix/tlsproxy \
       SYSLOG_IDENTIFIER=postfix/smtp \
       SYSLOG_IDENTIFIER=postfix/cleanup \
       SYSLOG_IDENTIFIER=postfix/qmgr \
       SYSLOG_IDENTIFIER=postfix/pickup \
       SYSLOG_IDENTIFIER=postfix/anvil \
       SYSLOG_IDENTIFIER=postfix/local \
       SYSLOG_IDENTIFIER=dovecot \
       SYSLOG_IDENTIFIER=rspamd" \
  >> "$OUT"
