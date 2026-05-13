"""
Warroom: ASUS router Prometheus exporter.

On each /metrics scrape, ssh into the router and read a fixed set of /proc
files. Parse and emit Prometheus exposition format. Zero-install on the
router; pure read-only.

Env:
  ROUTER_HOST        default 192.168.100.1
  ROUTER_USER        default admin
  ROUTER_SSH_KEY     default /id_ed25519 (mounted in container)
  LISTEN_PORT        default 9117
  SSH_TIMEOUT        default 5
"""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = os.environ.get("ROUTER_HOST", "192.168.100.1")
USER = os.environ.get("ROUTER_USER", "admin")
KEY = os.environ.get("ROUTER_SSH_KEY", "/id_ed25519")
PORT = int(os.environ.get("ROUTER_LISTEN_PORT", "9117"))
TIMEOUT = int(os.environ.get("SSH_TIMEOUT", "5"))
BANS_FILE = os.environ.get("BANS_FILE", "/state/banned.json")

# Single multiplexed remote command. /proc files read cheap and atomic-ish.
REMOTE_CMD = r"""
echo '## /proc/uptime'; cat /proc/uptime
echo '## /proc/loadavg'; cat /proc/loadavg
echo '## /proc/meminfo'; cat /proc/meminfo
echo '## /proc/stat'; head -n 1 /proc/stat
echo '## /proc/net/dev'; cat /proc/net/dev
echo '## /proc/net/snmp'; cat /proc/net/snmp 2>/dev/null
echo '## conntrack_count'; cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null
echo '## conntrack_max'; cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null
echo '## wan_ip'; nvram get wan0_ipaddr
echo '## productid'; nvram get productid
echo '## fw'; nvram get firmver
echo '## buildno'; nvram get buildno
echo '## ban_count'; iptables -t raw -L PREROUTING -n 2>/dev/null | grep -c '^DROP'
echo '## wslssh_log_pkts'; iptables -t mangle -L PREROUTING -nv 2>/dev/null | awk '/WSLSSH-/ {print $1,$2}'
"""


def fetch():
    return subprocess.run(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={TIMEOUT}",
            "-o", "UserKnownHostsFile=/dev/null",
            "-i", KEY,
            f"{USER}@{HOST}",
            REMOTE_CMD,
        ],
        capture_output=True, text=True, timeout=TIMEOUT + 3,
    ).stdout


def parse(raw):
    sections = {}
    cur = None
    for line in raw.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            sections[cur] = []
        elif cur is not None:
            sections[cur].append(line)
    return sections


def render(s):
    out = []
    add = out.append
    info_label_parts = []

    # Static info (gauge=1 with labels)
    productid = " ".join(s.get("productid", [""])).strip()
    fw = " ".join(s.get("fw", [""])).strip()
    buildno = " ".join(s.get("buildno", [""])).strip()
    wan_ip = " ".join(s.get("wan_ip", [""])).strip()
    add("# HELP asusrouter_info Static device info as labels (gauge=1).")
    add("# TYPE asusrouter_info gauge")
    add(f'asusrouter_info{{productid="{productid}",firmware="{fw}.{buildno}",wan_ip="{wan_ip}"}} 1')

    # uptime
    if s.get("/proc/uptime"):
        try:
            up = float(s["/proc/uptime"][0].split()[0])
            add("# HELP asusrouter_uptime_seconds Router uptime in seconds.")
            add("# TYPE asusrouter_uptime_seconds gauge")
            add(f"asusrouter_uptime_seconds {up}")
        except Exception:
            pass

    # loadavg: "0.83 0.61 0.83 1/123 12345"
    if s.get("/proc/loadavg"):
        parts = s["/proc/loadavg"][0].split()
        if len(parts) >= 3:
            for win, val in zip(("1m", "5m", "15m"), parts[:3]):
                add("# HELP asusrouter_load_average System load average.")
                add("# TYPE asusrouter_load_average gauge")
                add(f'asusrouter_load_average{{window="{win}"}} {val}')

    # meminfo
    if s.get("/proc/meminfo"):
        wanted = {"MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached", "SwapTotal", "SwapFree"}
        add("# HELP asusrouter_memory_bytes Memory subdivisions in bytes.")
        add("# TYPE asusrouter_memory_bytes gauge")
        for line in s["/proc/meminfo"]:
            try:
                k, rest = line.split(":", 1)
                if k not in wanted:
                    continue
                val_kb = int(rest.strip().split()[0])
                add(f'asusrouter_memory_bytes{{kind="{k.lower()}"}} {val_kb * 1024}')
            except Exception:
                pass

    # /proc/net/dev rx/tx by interface
    if s.get("/proc/net/dev"):
        add("# HELP asusrouter_net_rx_bytes Bytes received per interface (counter).")
        add("# TYPE asusrouter_net_rx_bytes counter")
        add("# HELP asusrouter_net_tx_bytes Bytes transmitted per interface (counter).")
        add("# TYPE asusrouter_net_tx_bytes counter")
        for line in s["/proc/net/dev"]:
            if ":" not in line:
                continue
            iface, stats = line.split(":", 1)
            iface = iface.strip()
            fields = stats.split()
            if len(fields) < 16:
                continue
            rx_bytes, tx_bytes = fields[0], fields[8]
            add(f'asusrouter_net_rx_bytes{{interface="{iface}"}} {rx_bytes}')
            add(f'asusrouter_net_tx_bytes{{interface="{iface}"}} {tx_bytes}')

    # conntrack
    for key, name in (("conntrack_count", "asusrouter_conntrack_count"),
                      ("conntrack_max", "asusrouter_conntrack_max")):
        v = s.get(key)
        if v and v[0].strip().isdigit():
            add(f"# TYPE {name} gauge")
            add(f"{name} {v[0].strip()}")

    # iptables: number of active ban rules
    if s.get("ban_count"):
        bc = s["ban_count"][0].strip()
        if bc.isdigit():
            add("# HELP asusrouter_active_bans Number of DROP rules in raw/PREROUTING.")
            add("# TYPE asusrouter_active_bans gauge")
            add(f"asusrouter_active_bans {bc}")

    # WSLSSH LOG rule packets+bytes
    if s.get("wslssh_log_pkts"):
        try:
            pkts, bytes_ = s["wslssh_log_pkts"][0].split()[:2]
            add("# HELP asusrouter_wslssh_log_pkts_total SYN packets logged by WSLSSH rule (counter).")
            add("# TYPE asusrouter_wslssh_log_pkts_total counter")
            add(f"asusrouter_wslssh_log_pkts_total {pkts}")
            add("# HELP asusrouter_wslssh_log_bytes_total Bytes logged by WSLSSH rule (counter).")
            add("# TYPE asusrouter_wslssh_log_bytes_total counter")
            add(f"asusrouter_wslssh_log_bytes_total {bytes_}")
        except Exception:
            pass

    # Per-IP ban state from warroom state file. Emits TWO metrics with the
    # src_ip label: when each ban was placed and when it expires.
    try:
        with open(BANS_FILE) as f:
            bans = json.load(f)
        add("# HELP asusrouter_ban_banned_at_seconds Unix epoch when this IP was banned.")
        add("# TYPE asusrouter_ban_banned_at_seconds gauge")
        add("# HELP asusrouter_ban_expires_at_seconds Unix epoch when the ban expires.")
        add("# TYPE asusrouter_ban_expires_at_seconds gauge")
        for ip, rec in bans.items():
            safe_ip = ip.replace('"', '')
            add(f'asusrouter_ban_banned_at_seconds{{src_ip="{safe_ip}"}} {rec.get("banned_at", 0)}')
            add(f'asusrouter_ban_expires_at_seconds{{src_ip="{safe_ip}"}} {rec.get("expires_at", 0)}')
    except FileNotFoundError:
        pass
    except Exception as e:
        add(f"# WARN cannot read {BANS_FILE}: {e}")

    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        try:
            raw = fetch()
            body = render(parse(raw))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"scrape failed: {e}\n".encode())

    def log_message(self, fmt, *args):
        # silence default access log
        pass


if __name__ == "__main__":
    print(f"warroom-asusrouter-exporter listening on :{PORT}, target {USER}@{HOST}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
