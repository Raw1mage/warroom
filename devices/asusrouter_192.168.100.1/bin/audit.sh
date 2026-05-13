#!/usr/bin/env bash
# Read-only full exposure audit. Prints to stdout, writes nothing.
set -euo pipefail
source "$(dirname "$0")/../lib/ssh.sh"

rssh_script <<'SH'
echo "===== identity ====="
echo "model:    $(nvram get productid)"
echo "fw:       $(nvram get firmver).$(nvram get buildno)_$(nvram get extendno)"
echo "kernel:   $(uname -srm)"
echo "uptime:   $(uptime)"
echo "wan_ip:   $(nvram get wan0_ipaddr)"
echo "wan_if:   $(nvram get wan0_ifname)  ($(nvram get wan0_proto))"

echo
echo "===== port forwarding (vts_rulelist) ====="
nvram get vts_enable_x | awk '{print "enabled: " $0}'
nvram get vts_rulelist | tr '<' '\n' | awk -F'>' 'NF>=4 {printf "  %-12s ext=%-15s -> %s:%s  proto=%s\n",$1,$2,$3,($4==""?$2:$4),$5}'

echo
echo "===== dmz ====="
dmz="$(nvram get dmz_ip)"
echo "dmz_ip:   ${dmz:-<none>}"

echo
echo "===== upnp ====="
echo "upnp_enable:      $(nvram get upnp_enable)"
echo "miniupnpd_enable: $(nvram get miniupnpd_enable)"
echo "active leases:"
( cat /tmp/upnp.leases 2>/dev/null || cat /var/log/upnp.leases 2>/dev/null ) | sed 's/^/  /'
echo "  (none)" 2>/dev/null

echo
echo "===== router management exposure ====="
echo "misc_http_x (WAN admin):  $(nvram get misc_http_x)"
echo "misc_httpsport_x:         $(nvram get misc_httpsport_x)"
echo "misc_httpport_x:          $(nvram get misc_httpport_x)"
echo "sshd_enable:              $(nvram get sshd_enable)  (0=off 1=LAN 2=LAN+WAN)"
echo "sshd_port:                $(nvram get sshd_port)"
echo "sshd_pass:                $(nvram get sshd_pass)   (1=password auth allowed)"
echo "telnetd_enable:           $(nvram get telnetd_enable)"

echo
echo "===== dropbear listen sockets ====="
netstat -tlnp 2>/dev/null | awk 'NR==1 || /dropbear|:22 / {print}'

echo
echo "===== firewall toggles ====="
echo "fw_enable_x:              $(nvram get fw_enable_x)"
echo "fw_dos_x (AiProtect DoS): $(nvram get fw_dos_x)"
echo "fw_log_x:                 $(nvram get fw_log_x)"

echo
echo "===== INPUT chain (router-bound traffic) ====="
iptables -L INPUT -nv 2>/dev/null | head -25
SH
