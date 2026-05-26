#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional, Union


PORT = int(os.environ.get("WARROOM_AI_ANOMALY_SCORER_PORT", "8020"))
LOKI_QUERY_URL = os.environ.get("WARROOM_AI_LOKI_QUERY_URL", "http://loki:3100/loki/api/v1/query")
LOKI_PUSH_URL = os.environ.get("WARROOM_AI_LOKI_PUSH_URL", "http://loki:3100/loki/api/v1/push")
NAS_HOST = os.environ.get("WARROOM_AI_NAS_HOST", "thesmart")
INTERVAL_SECONDS = max(10, int(os.environ.get("WARROOM_AI_SCORER_INTERVAL_SECONDS", "60")))
LLM_ENABLED = os.environ.get("WARROOM_AI_LLM_ENABLED", "true").lower() in {"1", "true", "yes"}
LLM_PROVIDER = os.environ.get("WARROOM_AI_LLM_PROVIDER", "openai_compatible")
LLM_PROVIDER_ID = os.environ.get("WARROOM_AI_LLM_PROVIDER_ID", "rawbase")
LLM_BASE_URL = os.environ.get("WARROOM_AI_LLM_BASE_URL", "http://host.docker.internal:7731/v1").rstrip("/")
LLM_CHAT_COMPLETIONS_PATH = os.environ.get("WARROOM_AI_LLM_CHAT_COMPLETIONS_PATH", "/chat/completions")
LLM_MODEL = os.environ.get("WARROOM_AI_LLM_MODEL", "Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf")
LLM_MODEL_SPEC = os.environ.get("WARROOM_AI_LLM_MODEL_SPEC", "rawbase/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf")
LLM_API_KEY = os.environ.get("WARROOM_AI_LLM_API_KEY", "local")
LLM_CONNECT_TIMEOUT_SECONDS = max(1, int(os.environ.get("WARROOM_AI_LLM_CONNECT_TIMEOUT_SECONDS", "5")))
LLM_READ_TIMEOUT_SECONDS = max(1, int(os.environ.get("WARROOM_AI_LLM_READ_TIMEOUT_SECONDS", "45")))
LLM_TEMPERATURE = float(os.environ.get("WARROOM_AI_LLM_TEMPERATURE", "0.1"))
LLM_MAX_EVIDENCE_EVENTS = max(1, int(os.environ.get("WARROOM_AI_LLM_MAX_EVIDENCE_EVENTS", "20")))
LLM_RESPONSE_FORMAT = os.environ.get("WARROOM_AI_LLM_RESPONSE_FORMAT", "json_object")
ENTITY_HASH_SALT = os.environ.get("WARROOM_AI_ENTITY_HASH_SALT", os.environ.get("ENTITY_HASH_SALT", "warroom-ai-anomaly"))
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
    "llm_unavailable": 0,
    "llm_last_success_timestamp": 0,
}
METRIC_LOCK = threading.Lock()
LABELED_COUNTERS: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
LLM_DURATION_BUCKETS = [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
LLM_DURATION_COUNTS: dict[tuple[str, str], dict[float, int]] = {}
LLM_DURATION_SUMS: dict[tuple[str, str], float] = {}
LAST_EMITTED: dict[str, int] = {}


def _bump(key: str, amount: int = 1) -> None:
    with STATE_LOCK:
        STATE[key] = int(STATE.get(key, 0)) + amount


def _set_metric(key: str, value: Union[int, float]) -> None:
    with STATE_LOCK:
        STATE[key] = value


def _labels(**labels: str) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value) for key, value in labels.items()))


def _inc_labeled(metric: str, amount: int = 1, **labels: str) -> None:
    key = (metric, _labels(**labels))
    with METRIC_LOCK:
        LABELED_COUNTERS[key] = LABELED_COUNTERS.get(key, 0) + amount


def _observe_llm_duration(duration_seconds: float) -> None:
    key = (LLM_PROVIDER_ID, LLM_MODEL)
    with METRIC_LOCK:
        buckets = LLM_DURATION_COUNTS.setdefault(key, {bucket: 0 for bucket in LLM_DURATION_BUCKETS})
        for bucket in LLM_DURATION_BUCKETS:
            if duration_seconds <= bucket:
                buckets[bucket] = buckets.get(bucket, 0) + 1
        LLM_DURATION_SUMS[key] = LLM_DURATION_SUMS.get(key, 0.0) + duration_seconds


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    return "{" + ",".join(f'{key}="{value.replace(chr(92), chr(92) + chr(92)).replace(chr(34), chr(92) + chr(34))}"' for key, value in labels) + "}"


def _append_labeled_counter(lines: list[str], metric: str, help_text: str) -> None:
    lines.extend([f"# HELP {metric} {help_text}", f"# TYPE {metric} counter"])
    with METRIC_LOCK:
        items = [(labels, value) for (name, labels), value in LABELED_COUNTERS.items() if name == metric]
    for labels, value in sorted(items):
        lines.append(f"{metric}{_format_labels(labels)} {value}")


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
        "# HELP warroom_ai_anomaly_scorer_llm_success_total Successful LLM triage calls.",
        "# TYPE warroom_ai_anomaly_scorer_llm_success_total counter",
        f"warroom_ai_anomaly_scorer_llm_success_total {snapshot['llm_success_total']}",
        "# HELP warroom_ai_anomaly_scorer_llm_failures_total Failed LLM triage calls.",
        "# TYPE warroom_ai_anomaly_scorer_llm_failures_total counter",
        f"warroom_ai_anomaly_scorer_llm_failures_total {snapshot['llm_failures_total']}",
        "# HELP warroom_ai_anomaly_scorer_collection_failures_total Loki query/push failures.",
        "# TYPE warroom_ai_anomaly_scorer_collection_failures_total counter",
        f"warroom_ai_anomaly_scorer_collection_failures_total {snapshot['collection_failures_total']}",
        "# HELP warroom_ai_anomaly_scorer_last_success_timestamp Last successful scoring timestamp.",
        "# TYPE warroom_ai_anomaly_scorer_last_success_timestamp gauge",
        f"warroom_ai_anomaly_scorer_last_success_timestamp {snapshot['last_success_timestamp']}",
    ]
    _append_labeled_counter(lines, "warroom_ai_anomaly_candidates_total", "Anomaly candidates by NAS, rule, and severity.")
    _append_labeled_counter(lines, "warroom_ai_anomaly_alerts_total", "Anomaly alerts by NAS, rule, severity, and LLM status.")
    _append_labeled_counter(lines, "warroom_ai_llm_requests_total", "LLM requests by provider, model, and status.")
    _append_labeled_counter(lines, "warroom_ai_llm_json_parse_failures_total", "LLM JSON parse failures by provider and model.")
    duration_labels = _labels(provider_id=LLM_PROVIDER_ID, model=LLM_MODEL)
    lines.extend([
        "# HELP warroom_ai_llm_request_duration_seconds LLM request duration seconds.",
        "# TYPE warroom_ai_llm_request_duration_seconds histogram",
    ])
    with METRIC_LOCK:
        duration_counts = dict(LLM_DURATION_COUNTS.get((LLM_PROVIDER_ID, LLM_MODEL), {}))
        duration_sum = LLM_DURATION_SUMS.get((LLM_PROVIDER_ID, LLM_MODEL), 0.0)
    total_count = 0
    for bucket in LLM_DURATION_BUCKETS:
        count = duration_counts.get(bucket, 0)
        total_count = max(total_count, count)
        labels = tuple(sorted(duration_labels + (("le", str(bucket)),)))
        lines.append(f"warroom_ai_llm_request_duration_seconds_bucket{_format_labels(labels)} {count}")
    labels = tuple(sorted(duration_labels + (("le", "+Inf"),)))
    lines.append(f"warroom_ai_llm_request_duration_seconds_bucket{_format_labels(labels)} {total_count}")
    lines.append(f"warroom_ai_llm_request_duration_seconds_sum{_format_labels(duration_labels)} {duration_sum:.6f}")
    lines.append(f"warroom_ai_llm_request_duration_seconds_count{_format_labels(duration_labels)} {total_count}")
    provider_labels = _format_labels(duration_labels)
    lines.extend([
        "# HELP warroom_ai_llm_unavailable Whether the configured LLM provider is currently unavailable.",
        "# TYPE warroom_ai_llm_unavailable gauge",
        f"warroom_ai_llm_unavailable{provider_labels} {snapshot['llm_unavailable']}",
        "# HELP warroom_ai_llm_last_success_timestamp_seconds Last successful LLM response timestamp.",
        "# TYPE warroom_ai_llm_last_success_timestamp_seconds gauge",
        f"warroom_ai_llm_last_success_timestamp_seconds{provider_labels} {snapshot['llm_last_success_timestamp']}",
    ])
    return "\n".join(lines) + "\n"


def _http_json(url: str, payload: Optional[dict[str, Any]] = None, timeout: int = 10) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        # Loki's push endpoint replies 204 with empty body on success.
        # Treat any non-JSON / empty body as "ok, nothing to parse".
        if not body.strip():
            return {}
        return json.loads(body)


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
    salted = f"{ENTITY_HASH_SALT}:{value}"
    return "sha256:" + hashlib.sha256(salted.encode("utf-8")).hexdigest()[:24]


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

    auth_successes_10m = first_value(
        f'sum(count_over_time({{nas_host="{NAS_HOST}", source_channel="auth_log", action="auth_success"}}[10m]))'
    )
    auth_failures_10m = first_value(
        f'sum(count_over_time({{nas_host="{NAS_HOST}", source_channel="auth_log", action="auth_failure"}}[10m]))'
    )
    if auth_successes_10m > 0 and auth_failures_10m > AUTH_FAILURE_THRESHOLD_5M:
        candidates.append(
            build_candidate(
                "AUTH_SUCCESS_AFTER_FAILURE_V1",
                "high",
                0.85,
                "Auth success occurred after an auth failure burst window.",
                {
                    "window": "10m",
                    "count": auth_successes_10m,
                    "failure_count": auth_failures_10m,
                    "threshold": AUTH_FAILURE_THRESHOLD_5M,
                    "entity": "auth_success_after_failure",
                    "entity_type": "auth_pattern",
                    "observation_basis": "aggregate_success_count_with_failure_threshold",
                },
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
                    "freshness_guard": "observed_at_within_query_window",
                    "cursor_guard": "event_id_dedup_and_min_repeat_seconds",
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


def llm_safe_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
    safe: dict[str, Any] = {
        "rule_id": candidate.get("rule_id"),
        "severity": candidate.get("severity"),
        "deterministic_score": candidate.get("score"),
        "summary": candidate.get("summary"),
        "entity_type": candidate.get("entity_type"),
        "entity_value_hash": candidate.get("entity_value_hash"),
        "evidence_event_limit": LLM_MAX_EVIDENCE_EVENTS,
    }
    for key in ["window", "count", "failure_count", "value", "threshold", "threshold_bytes", "freshness_guard", "cursor_guard", "observation_basis"]:
        if key in evidence:
            safe[key] = evidence[key]
    return safe


def _llm_result(status: str, **fields: Any) -> dict[str, Any]:
    if status == "ok":
        _bump("llm_success_total")
        _set_metric("llm_unavailable", 0)
        _set_metric("llm_last_success_timestamp", int(time.time()))
    elif status != "disabled":
        _bump("llm_failures_total")
        _set_metric("llm_unavailable", 1 if status in {"unavailable", "timeout", "transport_error"} else 0)
    _inc_labeled("warroom_ai_llm_requests_total", provider_id=LLM_PROVIDER_ID, model=LLM_MODEL, status=status)
    if status == "invalid_json":
        _inc_labeled("warroom_ai_llm_json_parse_failures_total", provider_id=LLM_PROVIDER_ID, model=LLM_MODEL)
    result = {"llm_status": status, "llm_provider_id": LLM_PROVIDER_ID, "llm_model": LLM_MODEL, "llm_model_spec": LLM_MODEL_SPEC}
    result.update(fields)
    return result


def _parse_llm_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing_choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("missing_message")
    return str(message.get("content") or "").strip()


def _post_llm_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise urllib.error.URLError("unsupported_llm_url")
    connection_class = http.client.HTTPSConnection if parsed_url.scheme == "https" else http.client.HTTPConnection
    path = parsed_url.path or "/"
    if parsed_url.query:
        path += "?" + parsed_url.query
    body = json.dumps(payload).encode("utf-8")
    connection = connection_class(parsed_url.hostname, parsed_url.port, timeout=LLM_CONNECT_TIMEOUT_SECONDS)
    try:
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        if response.status >= 400:
            raise urllib.error.HTTPError(url, response.status, response.reason, response.headers, None)
        if response.fp and getattr(response.fp, "raw", None) and getattr(response.fp.raw, "_sock", None):
            response.fp.raw._sock.settimeout(LLM_READ_TIMEOUT_SECONDS)
        response_body = response.read().decode("utf-8")
        return json.loads(response_body)
    finally:
        connection.close()


def _validate_llm_json(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("response_not_object")
    confidence = parsed.get("confidence")
    if isinstance(confidence, (int, float)):
        confidence_value = max(0.0, min(1.0, float(confidence)))
    elif confidence in {"low", "medium", "high"}:
        confidence_value = {"low": 0.33, "medium": 0.66, "high": 0.9}[str(confidence)]
    else:
        raise ValueError("invalid_confidence")
    is_anomaly = parsed.get("is_anomaly", parsed.get("needs_human_review", True))
    if not isinstance(is_anomaly, bool):
        raise ValueError("invalid_is_anomaly")
    actions = parsed.get("recommended_actions", parsed.get("recommended_next_steps"))
    if actions is None:
        actions = []
    if not isinstance(actions, list) or not all(isinstance(item, str) for item in actions[:5]):
        raise ValueError("invalid_actions")
    return {
        "triage_summary": str(parsed.get("triage_summary") or parsed.get("reason") or "")[:1000],
        "llm_provider": LLM_PROVIDER,
        "llm_confidence": confidence_value,
        "llm_is_anomaly": is_anomaly,
        "llm_reason": str(parsed.get("reason") or parsed.get("triage_summary") or "")[:1000],
        "recommended_actions": actions[:5],
        "recommended_next_steps": actions[:5],
        "needs_human_review": bool(parsed.get("needs_human_review", True)),
    }


def llm_triage(candidate: dict[str, Any]) -> dict[str, Any]:
    if not LLM_ENABLED:
        return _llm_result("disabled")
    if LLM_PROVIDER != "openai_compatible":
        return _llm_result("unavailable", llm_error="unsupported_provider")
    prompt = {
        "instruction": "You are a defensive security triage assistant. Return strict JSON only. Do not invent root cause. Do not recommend destructive action.",
        "allowed_output_schema": {
            "triage_summary": "string",
            "reason": "string",
            "confidence": "number 0..1",
            "is_anomaly": True,
            "recommended_actions": ["string"],
            "needs_human_review": True,
        },
        "alert": llm_safe_evidence(candidate),
    }
    payload = {
        "model": LLM_MODEL,
        "temperature": LLM_TEMPERATURE,
        "messages": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, sort_keys=True)},
        ],
    }
    if LLM_RESPONSE_FORMAT == "json_object":
        payload["response_format"] = {"type": "json_object"}
    url = LLM_BASE_URL + LLM_CHAT_COMPLETIONS_PATH
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}"}
    previous_timeout = socket.getdefaulttimeout()
    started = time.monotonic()
    try:
        socket.setdefaulttimeout(LLM_READ_TIMEOUT_SECONDS)
        response_json = _post_llm_json(url, payload, headers)
        _observe_llm_duration(time.monotonic() - started)
        content = _parse_llm_content(response_json)
        parsed = json.loads(content)
        return _llm_result("ok", **_validate_llm_json(parsed))
    except json.JSONDecodeError as exc:
        _observe_llm_duration(time.monotonic() - started)
        return _llm_result("invalid_json", llm_error=exc.__class__.__name__)
    except ValueError as exc:
        _observe_llm_duration(time.monotonic() - started)
        return _llm_result("schema_error", llm_error=str(exc)[:80])
    except socket.timeout as exc:
        _observe_llm_duration(time.monotonic() - started)
        return _llm_result("timeout", llm_error=exc.__class__.__name__)
    except urllib.error.HTTPError as exc:
        _observe_llm_duration(time.monotonic() - started)
        status = "unavailable" if exc.code in {429, 500, 502, 503, 504} else "transport_error"
        return _llm_result(status, llm_error=f"HTTPError:{exc.code}")
    except urllib.error.URLError as exc:
        _observe_llm_duration(time.monotonic() - started)
        reason = getattr(exc, "reason", None)
        status = "timeout" if isinstance(reason, socket.timeout) else "transport_error"
        return _llm_result(status, llm_error=exc.__class__.__name__)
    except OSError as exc:
        _observe_llm_duration(time.monotonic() - started)
        return _llm_result("transport_error", llm_error=exc.__class__.__name__)
    finally:
        socket.setdefaulttimeout(previous_timeout)


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
            "llm_status": str(event.get("llm_status") or "unknown"),
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
            _inc_labeled(
                "warroom_ai_anomaly_candidates_total",
                nas_host=str(candidate.get("nas_host") or NAS_HOST),
                rule_id=str(candidate.get("rule_id") or "unknown"),
                severity=str(candidate.get("severity") or "unknown"),
            )
            enriched = dict(candidate)
            enriched.update(llm_triage(candidate))
            _inc_labeled(
                "warroom_ai_anomaly_alerts_total",
                nas_host=str(enriched.get("nas_host") or NAS_HOST),
                rule_id=str(enriched.get("rule_id") or "unknown"),
                severity=str(enriched.get("severity") or "unknown"),
                llm_status=str(enriched.get("llm_status") or "unknown"),
            )
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
