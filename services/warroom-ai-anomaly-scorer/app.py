#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional, Union


PORT = int(os.environ.get("WARROOM_AI_ANOMALY_SCORER_PORT", "8020"))
LOKI_QUERY_URL = os.environ.get("WARROOM_AI_LOKI_QUERY_URL", "http://loki:3100/loki/api/v1/query")
LOKI_PUSH_URL = os.environ.get("WARROOM_AI_LOKI_PUSH_URL", "http://loki:3100/loki/api/v1/push")
NAS_HOST = os.environ.get("WARROOM_AI_NAS_HOST", "thesmart")
INTERVAL_SECONDS = max(10, int(os.environ.get("WARROOM_AI_SCORER_INTERVAL_SECONDS", "60")))
OLLAMA_URL = os.environ.get("WARROOM_AI_OLLAMA_URL", "http://host.docker.internal:11434/api/chat")
OLLAMA_MODEL = os.environ.get("WARROOM_AI_OLLAMA_MODEL", "qwen2.5:14b-instruct")
OLLAMA_ENABLED = os.environ.get("WARROOM_AI_OLLAMA_ENABLED", "true").lower() in {"1", "true", "yes"}
OLLAMA_TIMEOUT_SECONDS = max(1, int(os.environ.get("WARROOM_AI_OLLAMA_TIMEOUT_SECONDS", "20")))
MIN_REPEAT_SECONDS = max(60, int(os.environ.get("WARROOM_AI_MIN_REPEAT_SECONDS", "900")))

AUTH_FAILURE_THRESHOLD_5M = int(os.environ.get("WARROOM_AI_AUTH_FAILURE_THRESHOLD_5M", "20"))
TCP_ESTABLISHED_THRESHOLD_5M = int(os.environ.get("WARROOM_AI_TCP_ESTABLISHED_THRESHOLD_5M", "100"))
LARGE_DOWNLOAD_BYTES = int(os.environ.get("WARROOM_AI_LARGE_DOWNLOAD_BYTES", "104857600"))

STATE_LOCK = threading.Lock()
STATE: dict[str, Union[int, float]] = {
    "up": 1,
    "cycles_total": 0,
    "candidates_total": 0,
    "alerts_pushed_total": 0,
    "llm_success_total": 0,
    "llm_failures_total": 0,
    "collection_failures_total": 0,
    "last_success_timestamp": 0,
}
LAST_EMITTED: dict[str, int] = {}


def _bump(key: str, amount: int = 1) -> None:
    with STATE_LOCK:
        STATE[key] = int(STATE.get(key, 0)) + amount


def _set_metric(key: str, value: Union[int, float]) -> None:
    with STATE_LOCK:
        STATE[key] = value


def metrics_payload() -> str:
    with STATE_LOCK:
        snapshot = dict(STATE)
    lines = [
        "# HELP warroom_ai_anomaly_scorer_up AI anomaly scorer health.",
        "# TYPE warroom_ai_anomaly_scorer_up gauge",
        f"warroom_ai_anomaly_scorer_up {snapshot['up']}",
        "# HELP warroom_ai_anomaly_scorer_cycles_total Completed scoring cycles.",
        "# TYPE warroom_ai_anomaly_scorer_cycles_total counter",
        f"warroom_ai_anomaly_scorer_cycles_total {snapshot['cycles_total']}",
        "# HELP warroom_ai_anomaly_scorer_candidates_total Anomaly candidates detected.",
        "# TYPE warroom_ai_anomaly_scorer_candidates_total counter",
        f"warroom_ai_anomaly_scorer_candidates_total {snapshot['candidates_total']}",
        "# HELP warroom_ai_anomaly_scorer_alerts_pushed_total Anomaly alerts pushed to Loki.",
        "# TYPE warroom_ai_anomaly_scorer_alerts_pushed_total counter",
        f"warroom_ai_anomaly_scorer_alerts_pushed_total {snapshot['alerts_pushed_total']}",
        "# HELP warroom_ai_anomaly_scorer_llm_success_total Successful Ollama triage calls.",
        "# TYPE warroom_ai_anomaly_scorer_llm_success_total counter",
        f"warroom_ai_anomaly_scorer_llm_success_total {snapshot['llm_success_total']}",
        "# HELP warroom_ai_anomaly_scorer_llm_failures_total Failed Ollama triage calls.",
        "# TYPE warroom_ai_anomaly_scorer_llm_failures_total counter",
        f"warroom_ai_anomaly_scorer_llm_failures_total {snapshot['llm_failures_total']}",
        "# HELP warroom_ai_anomaly_scorer_collection_failures_total Loki query/push failures.",
        "# TYPE warroom_ai_anomaly_scorer_collection_failures_total counter",
        f"warroom_ai_anomaly_scorer_collection_failures_total {snapshot['collection_failures_total']}",
        "# HELP warroom_ai_anomaly_scorer_last_success_timestamp Last successful scoring timestamp.",
        "# TYPE warroom_ai_anomaly_scorer_last_success_timestamp gauge",
        f"warroom_ai_anomaly_scorer_last_success_timestamp {snapshot['last_success_timestamp']}",
    ]
    return "\n".join(lines) + "\n"


def _http_json(url: str, payload: Optional[dict[str, Any]] = None, timeout: int = 10) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def loki_query(query: str) -> list[dict[str, Any]]:
    url = LOKI_QUERY_URL + "?" + urllib.parse.urlencode({"query": query})
    payload = _http_json(url, timeout=10)
    return payload.get("data", {}).get("result", []) if payload.get("status") == "success" else []


def first_value(query: str) -> float:
    result = loki_query(query)
    if not result:
        return 0.0
    value = result[0].get("value")
    if not isinstance(value, list) or len(value) < 2:
        return 0.0
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return 0.0


def _entity_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def build_candidate(rule_id: str, severity: str, score: float, summary: str, evidence: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    entity = str(evidence.get("entity") or rule_id)
    return {
        "event_id": f"anomaly-{NAS_HOST}-{rule_id.lower()}-{now}",
        "alert_id": f"ai-{NAS_HOST}-{rule_id.lower()}-{now}",
        "action": "anomaly_alert",
        "nas_host": NAS_HOST,
        "source_app": "warroom_ai",
        "source_channel": "ai_anomaly_alert",
        "source_key": "warroom_ai_anomaly_scorer",
        "rule_id": rule_id,
        "severity": severity,
        "status": "active",
        "score": round(score, 4),
        "model_family": "rule+baseline+llm_triage",
        "entity_type": str(evidence.get("entity_type") or "rule"),
        "entity_value_hash": _entity_hash(entity),
        "summary": summary,
        "evidence": evidence,
        "observed_at": now,
        "llm_status": "not_requested",
        "triage_summary": "",
        "recommended_action": "Review the Grafana alert and the related Loki evidence before taking action.",
        "policy_notes": [
            "AI scorer emits bounded-label anomaly signals only.",
            "Grafana Alerting owns alert lifecycle and notification.",
            "No automatic blocking or destructive response is allowed.",
        ],
    }


def collect_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    auth_failures = first_value(
        f'sum(count_over_time({{nas_host="{NAS_HOST}", source_channel="auth_log", action="auth_failure"}}[5m]))'
    )
    if auth_failures > AUTH_FAILURE_THRESHOLD_5M:
        candidates.append(
            build_candidate(
                "AUTH_FAILURE_SPIKE_V1",
                "high",
                min(1.0, auth_failures / max(AUTH_FAILURE_THRESHOLD_5M * 2, 1)),
                f"Auth failures exceeded {AUTH_FAILURE_THRESHOLD_5M} in 5 minutes.",
                {"window": "5m", "count": auth_failures, "threshold": AUTH_FAILURE_THRESHOLD_5M, "entity": "all_auth", "entity_type": "nas_host"},
            )
        )

    active_gaps = first_value(
        f'sum(count_over_time({{nas_host="{NAS_HOST}", source_channel="collector_capability_gap", action="capability_gap"}}[2m]))'
    )
    if active_gaps > 0:
        candidates.append(
            build_candidate(
                "COLLECTOR_ACTIVE_GAP_V1",
                "high",
                1.0,
                "Active evidence collection capability gaps were observed.",
                {"window": "2m", "count": active_gaps, "threshold": 0, "entity": "collector", "entity_type": "source_key"},
            )
        )

    tcp_established = first_value(
        f'max_over_time({{nas_host="{NAS_HOST}", source_channel="network_socket"}} | json | __error__="" | unwrap tcp_established_count [5m])'
    )
    if tcp_established > TCP_ESTABLISHED_THRESHOLD_5M:
        candidates.append(
            build_candidate(
                "NETWORK_CONNECTION_SPIKE_V1",
                "medium",
                min(1.0, tcp_established / max(TCP_ESTABLISHED_THRESHOLD_5M * 2, 1)),
                f"TCP established connection count exceeded {TCP_ESTABLISHED_THRESHOLD_5M}.",
                {"window": "5m", "value": tcp_established, "threshold": TCP_ESTABLISHED_THRESHOLD_5M, "entity": "tcp_established", "entity_type": "metric"},
            )
        )

    large_downloads = first_value(
        f'sum(count_over_time({{nas_host="{NAS_HOST}", source_app="file_station", action="webapp_file_download"}} | json | size_bytes >= {LARGE_DOWNLOAD_BYTES} [5m]))'
    )
    if large_downloads > 0:
        candidates.append(
            build_candidate(
                "DOWNLOAD_LARGE_FILE_INGESTED_V1",
                "medium",
                0.7,
                "Large File Station download evidence was ingested.",
                {
                    "window": "5m",
                    "count": large_downloads,
                    "threshold_bytes": LARGE_DOWNLOAD_BYTES,
                    "entity": "file_station_download",
                    "entity_type": "source_app",
                    "freshness_guard": "pending_observed_at_cursor",
                },
            )
        )
    return candidates


def should_emit(candidate: dict[str, Any]) -> bool:
    key = f"{candidate.get('rule_id')}:{candidate.get('entity_value_hash')}"
    now = int(time.time())
    previous = LAST_EMITTED.get(key, 0)
    if now - previous < MIN_REPEAT_SECONDS:
        return False
    LAST_EMITTED[key] = now
    return True


def ollama_triage(candidate: dict[str, Any]) -> dict[str, Any]:
    if not OLLAMA_ENABLED:
        return {"llm_status": "disabled"}
    prompt = {
        "instruction": "You are a defensive security triage assistant. Return strict JSON only. Do not invent root cause. Do not recommend destructive action.",
        "allowed_output_schema": {
            "triage_summary": "string",
            "confidence": "low|medium|high",
            "recommended_next_steps": ["string"],
            "needs_human_review": True,
        },
        "alert": {k: candidate.get(k) for k in ["rule_id", "severity", "score", "summary", "evidence"]},
    }
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "options": {"temperature": 0.1, "top_p": 0.9, "num_ctx": 4096},
        "messages": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, sort_keys=True)},
        ],
    }
    try:
        response = _http_json(OLLAMA_URL, payload, timeout=OLLAMA_TIMEOUT_SECONDS)
        content = str((response.get("message") or {}).get("content") or "").strip()
        parsed = json.loads(content)
        _bump("llm_success_total")
        return {
            "llm_status": "ok",
            "llm_model": OLLAMA_MODEL,
            "triage_summary": str(parsed.get("triage_summary") or "")[:1000],
            "llm_confidence": str(parsed.get("confidence") or "unknown")[:32],
            "recommended_next_steps": parsed.get("recommended_next_steps") if isinstance(parsed.get("recommended_next_steps"), list) else [],
            "needs_human_review": bool(parsed.get("needs_human_review", True)),
        }
    except Exception as exc:
        _bump("llm_failures_total")
        return {"llm_status": "unavailable", "llm_error": exc.__class__.__name__, "llm_model": OLLAMA_MODEL}


def push_loki(events: list[dict[str, Any]]) -> None:
    if not events:
        return
    now_ns = str(time.time_ns())
    streams: dict[tuple[tuple[str, str], ...], list[list[str]]] = {}
    for event in events:
        labels = {
            "job": "warroom-ai-anomaly-scorer",
            "service_name": "warroom-ai-anomaly-scorer",
            "nas_host": str(event.get("nas_host") or NAS_HOST),
            "source_app": str(event.get("source_app") or "warroom_ai"),
            "source_channel": str(event.get("source_channel") or "ai_anomaly_alert"),
            "action": str(event.get("action") or "anomaly_alert"),
            "severity": str(event.get("severity") or "unknown"),
            "rule_id": str(event.get("rule_id") or "unknown"),
        }
        key = tuple(sorted(labels.items()))
        streams.setdefault(key, []).append([now_ns, json.dumps(event, ensure_ascii=False, sort_keys=True)])
    payload = {"streams": [{"stream": dict(key), "values": values} for key, values in streams.items()]}
    _http_json(LOKI_PUSH_URL, payload, timeout=10)


def run_cycle(dry_run: bool = False) -> int:
    _bump("cycles_total")
    try:
        candidates = [candidate for candidate in collect_candidates() if should_emit(candidate)]
        _bump("candidates_total", len(candidates))
        events = []
        for candidate in candidates:
            enriched = dict(candidate)
            enriched.update(ollama_triage(candidate))
            events.append(enriched)
        if dry_run:
            for event in events:
                print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)
        else:
            push_loki(events)
        _bump("alerts_pushed_total", len(events))
        _set_metric("last_success_timestamp", int(time.time()))
        return 0
    except Exception as exc:
        _bump("collection_failures_total")
        print(json.dumps({"ok": False, "stage": "scoring_cycle_failed", "error": exc.__class__.__name__}, sort_keys=True), flush=True)
        return 1


def event_loop() -> None:
    while True:
        run_cycle(False)
        time.sleep(INTERVAL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            payload = b'{"status":"ok"}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
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

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Warroom AI anomaly scorer")
    parser.add_argument("--once", action="store_true", help="Run one scoring cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print anomaly alerts instead of pushing to Loki")
    args = parser.parse_args()
    if args.once:
        return run_cycle(args.dry_run)
    thread = threading.Thread(target=event_loop, daemon=True)
    thread.start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
