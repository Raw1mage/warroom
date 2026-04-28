import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PORT = int(os.environ.get("WARROOM_PLACEHOLDER_PORT", "8000"))
LOKI_URL = os.environ.get("LOKI_PUSH_URL", "http://loki:3100/loki/api/v1/push")
FOLDER = os.environ.get("WARROOM_SYNTHETIC_FOLDER", "~Raw1mage")
HOST = os.environ.get("WARROOM_SYNTHETIC_NAS", "demo-nas")

STARTED_AT = time.time()
STATE = {
    "events_total": 0,
    "incidents_total": 0,
    "capability_gaps_total": 0,
    "loki_push_failures_total": 0,
    "last_event_timestamp": 0,
}

SCENARIOS = [
    {
        "rule_id": "RULE_MASS_DELETE_RENAME_MODIFY",
        "action": "rename",
        "severity": "high",
        "recommendation": "investigate",
    },
    {
        "rule_id": "RULE_FAILED_LOGIN_THEN_SUCCESS",
        "action": "login_success",
        "severity": "medium",
        "recommendation": "notify_owner",
    },
    {
        "rule_id": "RULE_PERMISSION_BROADENING",
        "action": "permission_change",
        "severity": "high",
        "recommendation": "require_approval",
    },
    {
        "rule_id": "CAPABILITY_GAP_LOG_BLOCKED",
        "action": "capability_gap",
        "severity": "low",
        "recommendation": "observe",
    },
]


def metric_line(name, value, labels=None):
    labels = labels or {}
    label_text = ""
    if labels:
        pairs = [f'{key}="{value}"' for key, value in sorted(labels.items())]
        label_text = "{" + ",".join(pairs) + "}"
    return f"{name}{label_text} {value}"


def metrics_payload():
    uptime = max(0, int(time.time() - STARTED_AT))
    lines = [
        "# HELP warroom_placeholder_up Synthetic Warroom placeholder service health.",
        "# TYPE warroom_placeholder_up gauge",
        metric_line("warroom_placeholder_up", 1, {"job": "warroom-placeholder", "service": "warroom-placeholder"}),
        "# HELP warroom_synthetic_dlp_events_total Synthetic DLP-like events emitted by placeholder service.",
        "# TYPE warroom_synthetic_dlp_events_total counter",
        metric_line("warroom_synthetic_dlp_events_total", STATE["events_total"], {"folder": FOLDER, "nas_host": HOST}),
        "# HELP warroom_synthetic_incidents_total Synthetic incidents emitted by placeholder service.",
        "# TYPE warroom_synthetic_incidents_total counter",
        metric_line("warroom_synthetic_incidents_total", STATE["incidents_total"], {"folder": FOLDER, "nas_host": HOST}),
        "# HELP warroom_synthetic_capability_gaps_total Synthetic capability gaps emitted by placeholder service.",
        "# TYPE warroom_synthetic_capability_gaps_total counter",
        metric_line("warroom_synthetic_capability_gaps_total", STATE["capability_gaps_total"], {"folder": FOLDER, "nas_host": HOST}),
        "# HELP warroom_placeholder_loki_push_failures_total Failed synthetic Loki pushes.",
        "# TYPE warroom_placeholder_loki_push_failures_total counter",
        metric_line("warroom_placeholder_loki_push_failures_total", STATE["loki_push_failures_total"]),
        "# HELP warroom_placeholder_uptime_seconds Placeholder service uptime.",
        "# TYPE warroom_placeholder_uptime_seconds gauge",
        metric_line("warroom_placeholder_uptime_seconds", uptime),
    ]
    return "\n".join(lines) + "\n"


def push_loki(event):
    timestamp_ns = str(time.time_ns())
    payload = {
        "streams": [
            {
                "stream": {
                    "job": "warroom-placeholder",
                    "service": "warroom-placeholder",
                    "nas_host": HOST,
                    "folder": FOLDER,
                    "synthetic": "true",
                },
                "values": [[timestamp_ns, json.dumps(event, separators=(",", ":"))]],
            }
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        LOKI_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        STATE["loki_push_failures_total"] += 1


def event_loop():
    while True:
        scenario = random.choice(SCENARIOS)
        STATE["events_total"] += 1
        if scenario["rule_id"].startswith("RULE_"):
            STATE["incidents_total"] += 1
        if scenario["action"] == "capability_gap":
            STATE["capability_gaps_total"] += 1
        STATE["last_event_timestamp"] = int(time.time())

        event = {
            "event_id": f"synthetic-{STATE['events_total']}",
            "observed_at": int(time.time()),
            "nas_host": HOST,
            "folder": FOLDER,
            "source_channel": "synthetic_fixture",
            "action": scenario["action"],
            "rule_id": scenario["rule_id"],
            "severity": scenario["severity"],
            "recommended_response": scenario["recommendation"],
            "destructive_action_authorized": False,
            "synthetic": True,
        }
        print(json.dumps(event, sort_keys=True), flush=True)
        push_loki(event)
        time.sleep(10)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}\n')
            return
        if self.path == "/metrics":
            payload = metrics_payload().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def main():
    thread = threading.Thread(target=event_loop, daemon=True)
    thread.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
