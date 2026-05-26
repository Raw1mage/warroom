#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PORT = int(os.environ.get("WARROOM_DLP_FILE_COLLECTOR_PORT", "8010"))
LOKI_URL = os.environ.get("LOKI_PUSH_URL", "http://loki:3100/loki/api/v1/push")
SOURCES = [item.strip() for item in os.environ.get("WARROOM_DLP_COLLECTOR_SOURCES", "file_station_remote").split(",") if item.strip()]
INTERVAL_SECONDS = max(1, int(os.environ.get("WARROOM_DLP_COLLECTOR_INTERVAL_SECONDS", "30")))
GEOIP_MMDB_PATH = os.environ.get("WARROOM_GEOIP_MMDB_PATH", "").strip()
NAS_TARGETS_CONFIG = os.environ.get("WARROOM_NAS_TARGETS_CONFIG", "/config/nas-targets.json").strip()
SERVER_ROOTS_DIR = os.environ.get("WARROOM_SERVER_ROOTS_DIR", "").strip()
TOOLS_DIR = Path(os.environ.get("WARROOM_DLP_TOOLS_DIR", "/tools"))
if not TOOLS_DIR.exists():
    TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import dlp_event_collector  # noqa: E402


STATE = {
    "up": 1,
    "cycles_total": 0,
    "events_pushed_total": 0,
    "capability_gaps_total": 0,
    "collection_failures_total": 0,
    "last_success_timestamp": 0,
}
REMOTE_SEEN_EVENT_IDS: set[str] = set()
STATE_LOCK = threading.Lock()

SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "file_station_remote": {
        "source_app": "file_station",
        "source_channel": "file_station_transfer_db",
        "capability": "file_transfer_evidence",
        "handler": None,
    },
    "drive_remote": {
        "source_app": "synology_drive",
        "source_channel": "drive_activity_db",
        "capability": "drive_activity_evidence",
        "handler": None,
    },
    "nas_home_log_remote": {
        "source_app": "nas_file_service",
        "source_channel": "nas_home_log",
        "capability": "home_scope_file_activity",
        "handler": None,
    },
    "host_health_remote": {
        "source_app": "nas_host_health",
        "source_channel": "host_health",
        "capability": "host_health_metrics",
        "handler": None,
    },
    "nas_system_log_remote": {
        "source_app": "nas_system_log",
        "source_channel": "nas_system_log",
        "capability": "nas_system_events",
        "handler": None,
    },
    "auth_log_remote": {
        "source_app": "nas_auth",
        "source_channel": "auth_log",
        "capability": "authentication_events",
        "handler": None,
    },
    "network_socket_remote": {
        "source_app": "nas_network",
        "source_channel": "network_socket",
        "capability": "network_socket_snapshot",
        "handler": None,
    },
    "docker_service_remote": {
        "source_app": "host_docker",
        "source_channel": "docker_service",
        "capability": "docker_service_health",
        "handler": None,
    },
}

FIELD_COVERAGE_KEYS = [
    "actor",
    "source_ip",
    "source_country",
    "source_region",
    "file_name",
    "folder_path",
    "display_path",
    "size_bytes",
    "network_protocol",
]


def _metric_line(name: str, value: int | float) -> str:
    return f"{name} {value}"


def metrics_payload() -> str:
    with STATE_LOCK:
        snapshot = dict(STATE)
    lines = [
        "# HELP warroom_dlp_file_collector_up DLP file collector health.",
        "# TYPE warroom_dlp_file_collector_up gauge",
        _metric_line("warroom_dlp_file_collector_up", snapshot["up"]),
        "# HELP warroom_dlp_file_collector_cycles_total Completed collection cycles.",
        "# TYPE warroom_dlp_file_collector_cycles_total counter",
        _metric_line("warroom_dlp_file_collector_cycles_total", snapshot["cycles_total"]),
        "# HELP warroom_dlp_file_collector_events_pushed_total Events successfully pushed to Loki.",
        "# TYPE warroom_dlp_file_collector_events_pushed_total counter",
        _metric_line("warroom_dlp_file_collector_events_pushed_total", snapshot["events_pushed_total"]),
        "# HELP warroom_dlp_file_collector_capability_gaps_total Capability-gap events emitted by collector.",
        "# TYPE warroom_dlp_file_collector_capability_gaps_total counter",
        _metric_line("warroom_dlp_file_collector_capability_gaps_total", snapshot["capability_gaps_total"]),
        "# HELP warroom_dlp_file_collector_collection_failures_total Collection or Loki push failures.",
        "# TYPE warroom_dlp_file_collector_collection_failures_total counter",
        _metric_line("warroom_dlp_file_collector_collection_failures_total", snapshot["collection_failures_total"]),
        "# HELP warroom_dlp_file_collector_last_success_timestamp Last successful Loki push Unix timestamp.",
        "# TYPE warroom_dlp_file_collector_last_success_timestamp gauge",
        _metric_line("warroom_dlp_file_collector_last_success_timestamp", snapshot["last_success_timestamp"]),
    ]
    return "\n".join(lines) + "\n"


def _bump(key: str, amount: int = 1) -> None:
    with STATE_LOCK:
        STATE[key] += amount


def _set_metric(key: str, value: int) -> None:
    with STATE_LOCK:
        STATE[key] = value


def _source_contract(source_key: str) -> dict[str, Any]:
    return SOURCE_REGISTRY.get(
        source_key,
        {
            "source_app": "collector",
            "source_channel": source_key,
            "capability": "unknown_source",
            "handler": None,
        },
    )


def _capability_gap(source_key: str, stage: str, detail: str, nas_host: str | None = None) -> dict[str, Any]:
    _bump("capability_gaps_total")
    contract = _source_contract(source_key)
    event = {
        "event_id": f"capability-gap-{source_key}-{stage}-{int(time.time())}",
        "action": "capability_gap",
        "source_key": source_key,
        "source_channel": "collector_capability_gap",
        "source_app": "collector",
        "affected_source_channel": contract["source_channel"],
        "affected_source_app": contract["source_app"],
        "affected_capability": contract["capability"],
        "confidence": 1.0,
        "observed_at": int(time.time()),
        "collector": "warroom-dlp-file-collector",
        "gap_stage": stage,
        "gap_detail": detail[:240],
        "policy_notes": [
            "Configured source could not be collected; no fixture fallback was used.",
            "Collector does not read file contents, cookies, sessions, or raw credential-bearing URLs.",
        ],
    }
    if nas_host:
        event["nas_host"] = nas_host
    return event


def _source_coverage_event(source_key: str, source_events: list[dict[str, Any]], nas_host: str, observed_at: int) -> dict[str, Any]:
    contract = _source_contract(source_key)
    gap_count = sum(1 for event in source_events if event.get("action") == "capability_gap")
    evidence_count = sum(1 for event in source_events if event.get("action") != "capability_gap")
    if evidence_count > 0:
        coverage_status = "active"
        coverage_value = 1
    elif gap_count > 0:
        coverage_status = "gap"
        coverage_value = -1
    else:
        coverage_status = "no_events"
        coverage_value = 0

    return {
        "event_id": f"coverage-{nas_host}-{source_key}-{observed_at}",
        "action": "coverage_status",
        "source_channel": "collector_coverage",
        "source_app": "collector",
        "nas_host": nas_host,
        "source_key": source_key,
        "covered_source_app": contract["source_app"],
        "covered_source_channel": contract["source_channel"],
        "covered_capability": contract["capability"],
        "coverage_status": coverage_status,
        "coverage_value": coverage_value,
        "event_count": evidence_count,
        "gap_count": gap_count,
        "confidence": 1.0,
        "observed_at": observed_at,
        "policy_notes": [
            "This is collector source coverage/status only; it does not infer user activity.",
            "No fixture fallback or synthetic file/drive/download activity was generated.",
        ],
    }


def _field_coverage_events(events: list[dict[str, Any]], nas_host: str, observed_at: int) -> list[dict[str, Any]]:
    evidence = [event for event in events if event.get("action") not in {"capability_gap", "coverage_status", "field_coverage_status"}]
    event_count = len(evidence)
    coverage_events = []
    for field_name in FIELD_COVERAGE_KEYS:
        present_count = sum(1 for event in evidence if event.get(field_name) not in (None, "", []))
        coverage_status = "active" if present_count > 0 else "no_events"
        coverage_events.append(
            {
                "event_id": f"field-coverage-{nas_host}-{field_name}-{observed_at}",
                "action": "field_coverage_status",
                "source_channel": "collector_coverage",
                "source_app": "collector",
                "nas_host": nas_host,
                "field_name": field_name,
                "coverage_status": coverage_status,
                "coverage_value": 1 if coverage_status == "active" else 0,
                "present_count": present_count,
                "event_count": event_count,
                "confidence": 1.0,
                "observed_at": observed_at,
                "policy_notes": [
                    "This is field coverage/status only; missing fields remain missing instead of being guessed.",
                    "No fallback values were generated for empty evidence fields.",
                ],
            }
        )
    return coverage_events


def _geoip_reader() -> tuple[Any | None, dict[str, Any] | None]:
    if not GEOIP_MMDB_PATH:
        return None, None
    mmdb_path = Path(GEOIP_MMDB_PATH)
    if not mmdb_path.is_file():
        return None, _capability_gap("geoip", "mmdb_missing", f"GeoIP MMDB file not found: {mmdb_path}")
    try:
        import maxminddb  # type: ignore[import-not-found]
    except ImportError:
        return None, _capability_gap("geoip", "library_missing", "maxminddb Python package is not installed")
    try:
        return maxminddb.open_database(str(mmdb_path)), None
    except OSError as exc:
        return None, _capability_gap("geoip", "mmdb_open_failed", exc.__class__.__name__)


def _geoip_values(record: dict[str, Any]) -> tuple[str | None, str | None]:
    country = record.get("country") if isinstance(record.get("country"), dict) else {}
    country_value = country.get("iso_code") or (country.get("names") or {}).get("en")

    subdivisions = record.get("subdivisions") if isinstance(record.get("subdivisions"), list) else []
    region_value = None
    if subdivisions and isinstance(subdivisions[0], dict):
        region = subdivisions[0]
        region_value = region.get("iso_code") or (region.get("names") or {}).get("en")
    return country_value, region_value


def _enrich_geoip(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reader, gap = _geoip_reader()
    if reader is None:
        return events + ([gap] if gap else [])

    enriched: list[dict[str, Any]] = []
    try:
        for event in events:
            item = dict(event)
            source_ip = str(item.get("source_ip") or "").strip()
            if not source_ip:
                enriched.append(item)
                continue
            try:
                ip = ipaddress.ip_address(source_ip)
            except ValueError:
                enriched.append(item)
                continue
            if not ip.is_global:
                enriched.append(item)
                continue
            record = reader.get(source_ip)
            if isinstance(record, dict):
                country, region = _geoip_values(record)
                if country:
                    item["source_country"] = str(country)
                if region:
                    item["source_region"] = str(region)
            enriched.append(item)
        return enriched
    finally:
        reader.close()


def _network_protocol(event: dict[str, Any]) -> str | None:
    protocol = str(event.get("network_protocol") or event.get("protocol") or "").strip().lower()
    if not protocol:
        return None
    if protocol in {"http", "https", "ftp", "sftp", "smb", "nfs", "webdav", "rsync", "ssh"}:
        return protocol
    if protocol.endswith("_web") or "web" in protocol:
        return "http"
    return protocol


def _enrich_network_protocol(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for event in events:
        item = dict(event)
        network_protocol = _network_protocol(item)
        if network_protocol:
            item["network_protocol"] = network_protocol
        enriched.append(item)
    return enriched


def _fallback_target() -> dict[str, Any]:
    return {
        "id": os.environ.get("WARROOM_FILE_STATION_NAS_HOST", "").strip() or "rawdb",
        "enabled": True,
        "sources": SOURCES,
        "file_station_remote": {
            "host": os.environ.get("WARROOM_FILE_STATION_REMOTE_HOST", "").strip() or "rawdb",
            "user": os.environ.get("WARROOM_FILE_STATION_REMOTE_USER", "").strip(),
            "db_path": os.environ.get("WARROOM_FILE_STATION_DB_PATH", "/volume1/@database/synolog/.DSMFMXFERDB"),
            "limit": int(os.environ.get("WARROOM_FILE_STATION_REMOTE_LIMIT", "50")),
            "timeout_seconds": int(os.environ.get("WARROOM_FILE_STATION_REMOTE_TIMEOUT_SECONDS", "30")),
        },
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json_object_required")
    return payload


def _merge_source_settings(target_payload: dict[str, Any], sources_payload: dict[str, Any], source: str, ssh: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    existing = target_payload.get(source)
    if isinstance(existing, dict):
        merged.update(existing)
    source_settings = sources_payload.get(source)
    if isinstance(source_settings, dict):
        merged.update(source_settings)
    if "host" not in merged and ssh.get("host"):
        merged["host"] = ssh.get("host")
    if "user" not in merged and ssh.get("user"):
        merged["user"] = ssh.get("user")
    return merged


def _load_server_root_target(root: Path) -> dict[str, Any] | None:
    target_path = root / "config" / "target.json"
    sources_path = root / "config" / "sources.json"
    if not target_path.is_file():
        return None
    try:
        target_payload = _load_json_object(target_path)
        sources_payload = _load_json_object(sources_path) if sources_path.is_file() else {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "id": root.name,
            "enabled": True,
            "sources": ["config_error"],
            "config_error": exc.__class__.__name__,
            "data_root": str(root / "data"),
        }

    ssh = target_payload.get("ssh") if isinstance(target_payload.get("ssh"), dict) else {}
    sources = sources_payload.get("sources") if isinstance(sources_payload.get("sources"), list) else target_payload.get("sources")
    if not isinstance(sources, list):
        sources = SOURCES

    target = dict(target_payload)
    target["id"] = str(target.get("id") or root.name)
    target["sources"] = [str(item) for item in sources]
    target["data_root"] = str(root / "data")
    for source in target["sources"]:
        target[source] = _merge_source_settings(target_payload, sources_payload, source, ssh)
    return target


def _load_server_root_targets() -> list[dict[str, Any]]:
    if not SERVER_ROOTS_DIR:
        return []
    roots_dir = Path(SERVER_ROOTS_DIR)
    if not roots_dir.is_dir():
        return []
    targets: list[dict[str, Any]] = []
    for root in sorted(item for item in roots_dir.iterdir() if item.is_dir()):
        target = _load_server_root_target(root)
        if target is not None:
            targets.append(target)
    return targets


def _load_targets() -> list[dict[str, Any]]:
    server_root_targets = _load_server_root_targets()
    if server_root_targets:
        return server_root_targets
    if not NAS_TARGETS_CONFIG:
        return [_fallback_target()]
    config_path = Path(NAS_TARGETS_CONFIG)
    if not config_path.is_file():
        return [_fallback_target()]
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            {
                "id": "config",
                "enabled": True,
                "sources": ["config_error"],
                "config_error": exc.__class__.__name__,
            }
        ]
    targets = payload.get("targets") if isinstance(payload, dict) else None
    if not isinstance(targets, list):
        return [{"id": "config", "enabled": True, "sources": ["config_error"], "config_error": "targets_not_list"}]
    return [target for target in targets if isinstance(target, dict)]


def _file_station_remote_events(target: dict[str, Any]) -> list[dict[str, Any]]:
    settings = target.get("file_station_remote") if isinstance(target.get("file_station_remote"), dict) else {}
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas").strip()
    host = str(settings.get("host") or "").strip()
    user = str(settings.get("user") or "").strip()
    if not host:
        return [_capability_gap("file_station_remote", "remote_config_missing", "remote host must be explicitly configured", nas_host)]

    adapter = TOOLS_DIR / "file_station_transfer_adapter.py"
    limit = str(settings.get("limit") or 50)
    timeout = str(settings.get("timeout_seconds") or 30)
    db_path = str(settings.get("db_path") or "/volume1/@database/synolog/.DSMFMXFERDB")
    command = [
        sys.executable,
        str(adapter),
        "--mode",
        "remote",
        "--host",
        host,
        "--nas-host",
        nas_host,
        "--db-path",
        db_path,
        "--limit",
        limit,
        "--timeout-sec",
        timeout,
    ]
    if user:
        command.extend(["--user", user])
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=int(timeout) + 5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        _bump("collection_failures_total")
        return [_capability_gap("file_station_remote", "adapter_execution_failed", exc.__class__.__name__, nas_host)]
    if proc.returncode != 0:
        _bump("collection_failures_total")
        return [_capability_gap("file_station_remote", "adapter_returned_failure", f"returncode={proc.returncode}", nas_host)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _bump("collection_failures_total")
        return [_capability_gap("file_station_remote", "adapter_invalid_json", "adapter stdout was not valid JSON", nas_host)]
    events = payload.get("events", [])
    if not isinstance(events, list):
        _bump("collection_failures_total")
        return [_capability_gap("file_station_remote", "adapter_events_invalid", "adapter events field was not a list", nas_host)]

    new_events = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "")
        if not event_id or event_id in REMOTE_SEEN_EVENT_IDS:
            continue
        REMOTE_SEEN_EVENT_IDS.add(event_id)
        new_events.append(event)
    return new_events


def _drive_remote_events(target: dict[str, Any]) -> list[dict[str, Any]]:
    settings = target.get("drive_remote") if isinstance(target.get("drive_remote"), dict) else {}
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas").strip()
    host = str(settings.get("host") or "").strip()
    user = str(settings.get("user") or "").strip()
    if not host:
        return [_capability_gap("drive_remote", "remote_config_missing", "remote host must be explicitly configured", nas_host)]

    adapter = TOOLS_DIR / "drive_activity_adapter.py"
    limit = str(settings.get("limit") or 50)
    timeout = str(settings.get("timeout_seconds") or 30)
    sync_root = str(settings.get("sync_root") or "/volume1/@synologydrive/@sync")
    command = [
        sys.executable,
        str(adapter),
        "--mode",
        "remote",
        "--host",
        host,
        "--nas-host",
        nas_host,
        "--sync-root",
        sync_root,
        "--limit",
        limit,
        "--timeout-sec",
        timeout,
    ]
    if user:
        command.extend(["--user", user])
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=int(timeout) + 5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        _bump("collection_failures_total")
        return [_capability_gap("drive_remote", "adapter_execution_failed", exc.__class__.__name__, nas_host)]
    if proc.returncode != 0:
        _bump("collection_failures_total")
        detail = f"returncode={proc.returncode}"
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict):
                detail = str(payload.get("stage") or detail)
        except json.JSONDecodeError:
            pass
        return [_capability_gap("drive_remote", "adapter_returned_failure", detail, nas_host)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _bump("collection_failures_total")
        return [_capability_gap("drive_remote", "adapter_invalid_json", "adapter stdout was not valid JSON", nas_host)]
    events = payload.get("events", [])
    if not isinstance(events, list):
        _bump("collection_failures_total")
        return [_capability_gap("drive_remote", "adapter_events_invalid", "adapter events field was not a list", nas_host)]

    new_events = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "")
        if not event_id or event_id in REMOTE_SEEN_EVENT_IDS:
            continue
        REMOTE_SEEN_EVENT_IDS.add(event_id)
        new_events.append(event)
    return new_events


def _nas_home_log_remote_events(target: dict[str, Any]) -> list[dict[str, Any]]:
    settings = target.get("nas_home_log_remote") if isinstance(target.get("nas_home_log_remote"), dict) else {}
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas").strip()
    host = str(settings.get("host") or "").strip()
    user = str(settings.get("user") or "").strip()
    if not host:
        return [_capability_gap("nas_home_log_remote", "remote_config_missing", "remote host must be explicitly configured", nas_host)]

    adapter = TOOLS_DIR / "nas_home_log_adapter.py"
    limit = str(settings.get("limit") or 50)
    timeout = str(settings.get("timeout_seconds") or 30)
    tail_lines = str(settings.get("tail_lines") or 2000)
    log_paths = settings.get("log_paths") if isinstance(settings.get("log_paths"), list) else []
    command = [
        sys.executable,
        str(adapter),
        "--mode",
        "remote",
        "--host",
        host,
        "--nas-host",
        nas_host,
        "--limit",
        limit,
        "--tail-lines",
        tail_lines,
        "--timeout-sec",
        timeout,
    ]
    for log_path in [str(item) for item in log_paths if str(item).strip()]:
        command.extend(["--log-path", log_path])
    if user:
        command.extend(["--user", user])
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=int(timeout) + 5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        _bump("collection_failures_total")
        return [_capability_gap("nas_home_log_remote", "adapter_execution_failed", exc.__class__.__name__, nas_host)]
    if proc.returncode != 0:
        _bump("collection_failures_total")
        detail = f"returncode={proc.returncode}"
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict):
                detail = str(payload.get("stage") or detail)
        except json.JSONDecodeError:
            pass
        return [_capability_gap("nas_home_log_remote", "adapter_returned_failure", detail, nas_host)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _bump("collection_failures_total")
        return [_capability_gap("nas_home_log_remote", "adapter_invalid_json", "adapter stdout was not valid JSON", nas_host)]
    events = payload.get("events", [])
    if not isinstance(events, list):
        _bump("collection_failures_total")
        return [_capability_gap("nas_home_log_remote", "adapter_events_invalid", "adapter events field was not a list", nas_host)]

    new_events = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "")
        if not event_id or event_id in REMOTE_SEEN_EVENT_IDS:
            continue
        REMOTE_SEEN_EVENT_IDS.add(event_id)
        new_events.append(event)
    return new_events


def _host_health_remote_events(target: dict[str, Any]) -> list[dict[str, Any]]:
    settings = target.get("host_health_remote") if isinstance(target.get("host_health_remote"), dict) else {}
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas").strip()
    host = str(settings.get("host") or "").strip()
    user = str(settings.get("user") or "").strip()
    if not host:
        return [_capability_gap("host_health_remote", "remote_config_missing", "remote host must be explicitly configured", nas_host)]

    adapter = TOOLS_DIR / "host_health_adapter.py"
    timeout = str(settings.get("timeout_seconds") or 30)
    command = [
        sys.executable,
        str(adapter),
        "--mode",
        "remote",
        "--host",
        host,
        "--nas-host",
        nas_host,
        "--timeout-sec",
        timeout,
    ]
    if user:
        command.extend(["--user", user])
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=int(timeout) + 5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        _bump("collection_failures_total")
        return [_capability_gap("host_health_remote", "adapter_execution_failed", exc.__class__.__name__, nas_host)]
    if proc.returncode != 0:
        _bump("collection_failures_total")
        detail = f"returncode={proc.returncode}"
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict):
                detail = str(payload.get("stage") or detail)
        except json.JSONDecodeError:
            pass
        return [_capability_gap("host_health_remote", "adapter_returned_failure", detail, nas_host)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _bump("collection_failures_total")
        return [_capability_gap("host_health_remote", "adapter_invalid_json", "adapter stdout was not valid JSON", nas_host)]
    events = payload.get("events", [])
    if not isinstance(events, list):
        _bump("collection_failures_total")
        return [_capability_gap("host_health_remote", "adapter_events_invalid", "adapter events field was not a list", nas_host)]
    return [event for event in events if isinstance(event, dict)]


def _nas_system_log_remote_events(target: dict[str, Any]) -> list[dict[str, Any]]:
    settings = target.get("nas_system_log_remote") if isinstance(target.get("nas_system_log_remote"), dict) else {}
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas").strip()
    host = str(settings.get("host") or "").strip()
    user = str(settings.get("user") or "").strip()
    if not host:
        return [_capability_gap("nas_system_log_remote", "remote_config_missing", "remote host must be explicitly configured", nas_host)]

    adapter = TOOLS_DIR / "nas_system_log_adapter.py"
    limit = str(settings.get("limit") or 100)
    timeout = str(settings.get("timeout_seconds") or 30)
    tail_lines = str(settings.get("tail_lines") or 2000)
    log_paths = settings.get("log_paths") if isinstance(settings.get("log_paths"), list) else []
    command = [
        sys.executable,
        str(adapter),
        "--mode",
        "remote",
        "--host",
        host,
        "--nas-host",
        nas_host,
        "--limit",
        limit,
        "--tail-lines",
        tail_lines,
        "--timeout-sec",
        timeout,
    ]
    for log_path in [str(item) for item in log_paths if str(item).strip()]:
        command.extend(["--log-path", log_path])
    if user:
        command.extend(["--user", user])
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=int(timeout) + 5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        _bump("collection_failures_total")
        return [_capability_gap("nas_system_log_remote", "adapter_execution_failed", exc.__class__.__name__, nas_host)]
    if proc.returncode != 0:
        _bump("collection_failures_total")
        detail = f"returncode={proc.returncode}"
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict):
                detail = str(payload.get("stage") or detail)
        except json.JSONDecodeError:
            pass
        return [_capability_gap("nas_system_log_remote", "adapter_returned_failure", detail, nas_host)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _bump("collection_failures_total")
        return [_capability_gap("nas_system_log_remote", "adapter_invalid_json", "adapter stdout was not valid JSON", nas_host)]
    events = payload.get("events", [])
    if not isinstance(events, list):
        _bump("collection_failures_total")
        return [_capability_gap("nas_system_log_remote", "adapter_events_invalid", "adapter events field was not a list", nas_host)]

    new_events = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "")
        if not event_id or event_id in REMOTE_SEEN_EVENT_IDS:
            continue
        REMOTE_SEEN_EVENT_IDS.add(event_id)
        new_events.append(event)
    return new_events


def _auth_log_remote_events(target: dict[str, Any]) -> list[dict[str, Any]]:
    settings = target.get("auth_log_remote") if isinstance(target.get("auth_log_remote"), dict) else {}
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas").strip()
    host = str(settings.get("host") or "").strip()
    user = str(settings.get("user") or "").strip()
    if not host:
        return [_capability_gap("auth_log_remote", "remote_config_missing", "remote host must be explicitly configured", nas_host)]

    adapter = TOOLS_DIR / "auth_log_adapter.py"
    limit = str(settings.get("limit") or 100)
    timeout = str(settings.get("timeout_seconds") or 30)
    tail_lines = str(settings.get("tail_lines") or 2000)
    log_paths = settings.get("log_paths") if isinstance(settings.get("log_paths"), list) else []
    command = [
        sys.executable,
        str(adapter),
        "--mode",
        "remote",
        "--host",
        host,
        "--nas-host",
        nas_host,
        "--limit",
        limit,
        "--tail-lines",
        tail_lines,
        "--timeout-sec",
        timeout,
    ]
    for log_path in [str(item) for item in log_paths if str(item).strip()]:
        command.extend(["--log-path", log_path])
    if user:
        command.extend(["--user", user])
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=int(timeout) + 5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        _bump("collection_failures_total")
        return [_capability_gap("auth_log_remote", "adapter_execution_failed", exc.__class__.__name__, nas_host)]
    if proc.returncode != 0:
        _bump("collection_failures_total")
        detail = f"returncode={proc.returncode}"
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict):
                detail = str(payload.get("stage") or detail)
        except json.JSONDecodeError:
            pass
        return [_capability_gap("auth_log_remote", "adapter_returned_failure", detail, nas_host)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _bump("collection_failures_total")
        return [_capability_gap("auth_log_remote", "adapter_invalid_json", "adapter stdout was not valid JSON", nas_host)]
    events = payload.get("events", [])
    if not isinstance(events, list):
        _bump("collection_failures_total")
        return [_capability_gap("auth_log_remote", "adapter_events_invalid", "adapter events field was not a list", nas_host)]
    return [event for event in events if isinstance(event, dict)]


def _network_socket_remote_events(target: dict[str, Any]) -> list[dict[str, Any]]:
    settings = target.get("network_socket_remote") if isinstance(target.get("network_socket_remote"), dict) else {}
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas").strip()
    host = str(settings.get("host") or "").strip()
    user = str(settings.get("user") or "").strip()
    if not host:
        return [_capability_gap("network_socket_remote", "remote_config_missing", "remote host must be explicitly configured", nas_host)]

    adapter = TOOLS_DIR / "network_socket_adapter.py"
    timeout = str(settings.get("timeout_seconds") or 30)
    top_limit = str(settings.get("top_limit") or 10)
    command = [
        sys.executable,
        str(adapter),
        "--mode",
        "remote",
        "--host",
        host,
        "--nas-host",
        nas_host,
        "--top-limit",
        top_limit,
        "--timeout-sec",
        timeout,
    ]
    if user:
        command.extend(["--user", user])
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=int(timeout) + 5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        _bump("collection_failures_total")
        return [_capability_gap("network_socket_remote", "adapter_execution_failed", exc.__class__.__name__, nas_host)]
    if proc.returncode != 0:
        _bump("collection_failures_total")
        detail = f"returncode={proc.returncode}"
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict):
                detail = str(payload.get("stage") or detail)
        except json.JSONDecodeError:
            pass
        return [_capability_gap("network_socket_remote", "adapter_returned_failure", detail, nas_host)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _bump("collection_failures_total")
        return [_capability_gap("network_socket_remote", "adapter_invalid_json", "adapter stdout was not valid JSON", nas_host)]
    events = payload.get("events", [])
    if not isinstance(events, list):
        _bump("collection_failures_total")
        return [_capability_gap("network_socket_remote", "adapter_events_invalid", "adapter events field was not a list", nas_host)]
    return [event for event in events if isinstance(event, dict)]


def _docker_service_remote_events(target: dict[str, Any]) -> list[dict[str, Any]]:
    settings = target.get("docker_service_remote") if isinstance(target.get("docker_service_remote"), dict) else {}
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas").strip()
    host = str(settings.get("host") or "").strip()
    user = str(settings.get("user") or "").strip()
    if not host:
        return [_capability_gap("docker_service_remote", "remote_config_missing", "remote host must be explicitly configured", nas_host)]

    adapter = TOOLS_DIR / "docker_service_adapter.py"
    timeout = str(settings.get("timeout_seconds") or 30)
    limit = str(settings.get("limit") or 100)
    command = [
        sys.executable,
        str(adapter),
        "--mode",
        "remote",
        "--host",
        host,
        "--nas-host",
        nas_host,
        "--limit",
        limit,
        "--timeout-sec",
        timeout,
    ]
    if user:
        command.extend(["--user", user])
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=int(timeout) + 5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        _bump("collection_failures_total")
        return [_capability_gap("docker_service_remote", "adapter_execution_failed", exc.__class__.__name__, nas_host)]
    if proc.returncode != 0:
        _bump("collection_failures_total")
        detail = f"returncode={proc.returncode}"
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict):
                detail = str(payload.get("stage") or detail)
        except json.JSONDecodeError:
            pass
        return [_capability_gap("docker_service_remote", "adapter_returned_failure", detail, nas_host)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _bump("collection_failures_total")
        return [_capability_gap("docker_service_remote", "adapter_invalid_json", "adapter stdout was not valid JSON", nas_host)]
    events = payload.get("events", [])
    if not isinstance(events, list):
        _bump("collection_failures_total")
        return [_capability_gap("docker_service_remote", "adapter_events_invalid", "adapter events field was not a list", nas_host)]
    return [event for event in events if isinstance(event, dict)]


def _collect_target(target: dict[str, Any]) -> list[dict[str, Any]]:
    nas_host = str(target.get("id") or target.get("nas_host") or "configured-nas")
    events: list[dict[str, Any]] = []
    observed_at = int(time.time())
    if target.get("enabled") is False:
        return events
    sources = target.get("sources") if isinstance(target.get("sources"), list) else SOURCES
    for source in [str(item) for item in sources]:
        contract = SOURCE_REGISTRY.get(source)
        handler = contract.get("handler") if contract else None
        if not callable(handler):
            events.append(_capability_gap(source, "unsupported_source", "source mode is not supported by this collector", nas_host))
            continue
        source_events = handler(target)
        for event in source_events:
            if isinstance(event, dict) and event.get("action") != "capability_gap":
                event.setdefault("source_key", source)
        events.extend(source_events)
        events.append(_source_coverage_event(source, [event for event in source_events if isinstance(event, dict)], nas_host, observed_at))
    for event in events:
        event.setdefault("nas_host", nas_host)
    events.extend(_field_coverage_events(events, nas_host, observed_at))
    return events


SOURCE_REGISTRY["file_station_remote"]["handler"] = _file_station_remote_events
SOURCE_REGISTRY["drive_remote"]["handler"] = _drive_remote_events
SOURCE_REGISTRY["nas_home_log_remote"]["handler"] = _nas_home_log_remote_events
SOURCE_REGISTRY["host_health_remote"]["handler"] = _host_health_remote_events
SOURCE_REGISTRY["nas_system_log_remote"]["handler"] = _nas_system_log_remote_events
SOURCE_REGISTRY["auth_log_remote"]["handler"] = _auth_log_remote_events
SOURCE_REGISTRY["network_socket_remote"]["handler"] = _network_socket_remote_events
SOURCE_REGISTRY["docker_service_remote"]["handler"] = _docker_service_remote_events


def _append_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _spool_target_events(target: dict[str, Any], events: list[dict[str, Any]]) -> None:
    data_root_value = str(target.get("data_root") or "").strip()
    if not data_root_value:
        return
    data_root = Path(data_root_value)
    now = int(time.time())
    nas_host = str(target.get("id") or target.get("nas_host") or data_root.parent.name)
    gaps = [event for event in events if event.get("action") == "capability_gap"]
    _append_jsonl(data_root / "normalized" / "events.jsonl", events)
    _append_jsonl(data_root / "normalized" / "capability_gaps.jsonl", gaps)
    _write_json(
        data_root / "state" / "last_run.json",
        {
            "nas_host": nas_host,
            "observed_at": now,
            "event_count": len(events),
            "capability_gap_count": len(gaps),
            "sources": target.get("sources") if isinstance(target.get("sources"), list) else SOURCES,
        },
    )


def collect_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for target in _load_targets():
        target_events = _collect_target(target)
        _spool_target_events(target, target_events)
        events.extend(target_events)
    return _enrich_geoip(_enrich_network_protocol(events))


def push_events(events: list[dict[str, Any]], dry_run: bool) -> int:
    if not events:
        return 0
    if dry_run:
        for event in events:
            print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)
        return len(events)
    dlp_event_collector.push_loki(LOKI_URL, events, 5)
    return len(events)


def run_cycle(dry_run: bool = False) -> int:
    _bump("cycles_total")
    events = collect_events()
    try:
        pushed = push_events(events, dry_run)
    except dlp_event_collector.CollectorError as exc:
        _bump("collection_failures_total")
        print(json.dumps({"ok": False, "stage": exc.stage, "error": exc.message}, sort_keys=True), flush=True)
        return 1
    if pushed:
        _bump("events_pushed_total", pushed)
        _set_metric("last_success_timestamp", int(time.time()))
    return 0


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
    parser = argparse.ArgumentParser(description="Continuous Warroom DLP file evidence collector")
    parser.add_argument("--once", action="store_true", help="Run one collection cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print events instead of pushing to Loki")
    args = parser.parse_args()
    if args.once:
        return run_cycle(args.dry_run)
    thread = threading.Thread(target=event_loop, daemon=True)
    thread.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
