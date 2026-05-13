"""
Warroom: Synology Security Advisor → Prometheus exporter.

On each /metrics scrape, ssh to rawdb and read:
  /var/lib/securityscan/securityscanResult.json   (per-rule findings)
  /var/lib/securityscan/systemResult.json         (overall system status)

Emits:
  synology_security_check_status{rule_id, severity, category, status, str_id}  gauge=1
  synology_security_check_total{severity, status}                              gauge (count)
  synology_security_system_status{nas_host}                                    gauge ("ok"=0, "warning"=1, "danger"=2)
  synology_security_scan_lastupdate_seconds                                    gauge (max(update))

Env:
  ROUTER_HOST       default 192.168.100.40
  ROUTER_USER       default yeatsluo
  ROUTER_SSH_KEY    default /id_ed25519
  LISTEN_PORT       default 9119
"""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = os.environ.get("RAWDB_HOST", "192.168.100.40")
USER = os.environ.get("RAWDB_USER", "yeatsluo")
KEY = os.environ.get("RAWDB_SSH_KEY", "/id_ed25519")
PORT = int(os.environ.get("SECURITY_LISTEN_PORT", "9119"))
NAS_HOST = os.environ.get("NAS_HOST", "rawdb")

REMOTE_CMD = r"""
echo '## scanResult.json'
sudo cat /var/lib/securityscan/securityscanResult.json 2>/dev/null
echo
echo '## systemResult.json'
sudo cat /var/lib/securityscan/systemResult.json 2>/dev/null
"""

SYS_STATUS_MAP = {"ok": 0, "info": 0, "outOfDate": 1, "warning": 1, "risk": 2, "danger": 3}


def fetch():
    return subprocess.run(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=5",
            "-o", "UserKnownHostsFile=/dev/null",
            "-i", KEY,
            f"{USER}@{HOST}",
            REMOTE_CMD,
        ],
        capture_output=True, text=True, timeout=10,
    ).stdout


def parse(raw):
    parts = raw.split("## ")
    rules, sys_ = {}, {}
    for p in parts[1:]:
        name, _, body = p.partition("\n")
        body = body.strip()
        if not body:
            continue
        try:
            obj = json.loads(body)
        except Exception:
            continue
        if name.strip().startswith("scanResult"):
            rules = obj
        elif name.strip().startswith("systemResult"):
            sys_ = obj
    return rules, sys_


def _esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def render(rules, sys_):
    lines = ["# HELP synology_security_check_status Per-rule status (gauge=1 with labels).",
             "# TYPE synology_security_check_status gauge"]
    counts = {}  # (severity, status) -> n
    last_update = 0
    for rule_id, rec in rules.items():
        if not isinstance(rec, dict):
            continue
        sev = rec.get("severity", "")
        st = rec.get("status", "")
        cat = rec.get("category", "")
        sid = rec.get("strId", "")
        try:
            ts = int(rec.get("update", 0))
        except (TypeError, ValueError):
            ts = 0
        if ts > last_update:
            last_update = ts
        counts[(sev, st)] = counts.get((sev, st), 0) + 1
        lines.append(
            f'synology_security_check_status{{nas_host="{_esc(NAS_HOST)}",rule_id="{_esc(rule_id)}",'
            f'severity="{_esc(sev)}",category="{_esc(cat)}",status="{_esc(st)}",str_id="{_esc(sid)}"}} 1'
        )

    lines.append("# HELP synology_security_check_total Count by severity × status.")
    lines.append("# TYPE synology_security_check_total gauge")
    for (sev, st), n in counts.items():
        lines.append(f'synology_security_check_total{{nas_host="{_esc(NAS_HOST)}",severity="{_esc(sev)}",status="{_esc(st)}"}} {n}')

    lines.append("# HELP synology_security_system_status Overall system status (0=ok 1=warning 2=risk 3=danger).")
    lines.append("# TYPE synology_security_system_status gauge")
    overall = sys_.get("sysStatus", "")
    lines.append(f'synology_security_system_status{{nas_host="{_esc(NAS_HOST)}",label="{_esc(overall)}"}} {SYS_STATUS_MAP.get(overall, 0)}')

    if isinstance(sys_.get("items"), dict):
        lines.append("# HELP synology_security_category_fail Per-category fail count by severity.")
        lines.append("# TYPE synology_security_category_fail gauge")
        for cat, blob in sys_["items"].items():
            fails = blob.get("fail") or {}
            for sev, n in fails.items():
                try:
                    lines.append(f'synology_security_category_fail{{nas_host="{_esc(NAS_HOST)}",category="{_esc(cat)}",severity="{_esc(sev)}"}} {int(n)}')
                except (TypeError, ValueError):
                    pass

    lines.append("# HELP synology_security_scan_lastupdate_seconds Latest per-rule update timestamp (epoch).")
    lines.append("# TYPE synology_security_scan_lastupdate_seconds gauge")
    lines.append(f'synology_security_scan_lastupdate_seconds{{nas_host="{_esc(NAS_HOST)}"}} {last_update}')

    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        try:
            raw = fetch()
            rules, sys_ = parse(raw)
            body = render(rules, sys_).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"scrape failed: {e}\n".encode())

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"warroom-securityscan-exporter listening :{PORT}, target {USER}@{HOST}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
