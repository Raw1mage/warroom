#!/usr/bin/env python3
"""Collect basic NAS host health metadata as Warroom events.

The adapter is read-only and supports SSH stdin payload execution. It does not
install a persistent agent on the NAS and does not read file contents.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


SERVICE_CANDIDATES = {
    "ssh": ["sshd", "ssh"],
    "smb": ["smbd", "samba", "pkg-synosamba-smbd"],
    "nginx": ["nginx"],
    "httpd": ["httpd", "apache2"],
    "dsm": ["nginx", "synoscgi", "synoindexd"],
}

PACKAGE_CANDIDATES = ["DSM", "FileStation", "SynologyDrive", "SMBService", "WebStation"]


def _run(command: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _uptime() -> dict[str, Any]:
    uptime_text = _read_text(Path("/proc/uptime"))
    load_text = _read_text(Path("/proc/loadavg"))
    payload: dict[str, Any] = {}
    if uptime_text:
        try:
            payload["uptime_seconds"] = float(uptime_text.split()[0])
        except (IndexError, ValueError):
            payload["uptime_error"] = "parse_failed"
    if load_text:
        parts = load_text.split()
        try:
            payload["load1"] = float(parts[0])
            payload["load5"] = float(parts[1])
            payload["load15"] = float(parts[2])
        except (IndexError, ValueError):
            payload["load_error"] = "parse_failed"
    return payload


def _memory() -> dict[str, int]:
    meminfo = _read_text(Path("/proc/meminfo")) or ""
    result: dict[str, int] = {}
    wanted = {
        "MemTotal": "memory_total_kb",
        "MemAvailable": "memory_available_kb",
        "MemFree": "memory_free_kb",
        "Buffers": "memory_buffers_kb",
        "Cached": "memory_cached_kb",
        "SwapTotal": "swap_total_kb",
        "SwapFree": "swap_free_kb",
    }
    for line in meminfo.splitlines():
        key, _, rest = line.partition(":")
        if key not in wanted:
            continue
        value = rest.strip().split()[0] if rest.strip() else ""
        if value.isdigit():
            result[wanted[key]] = int(value)
    return result


def _cpu() -> dict[str, Any]:
    stat = _read_text(Path("/proc/stat")) or ""
    first = next((line for line in stat.splitlines() if line.startswith("cpu ")), "")
    values: list[int] = []
    for item in first.split()[1:]:
        if item.isdigit():
            values.append(int(item))
    if not values:
        return {}
    total = sum(values)
    idle = values[3] if len(values) > 3 else 0
    busy_percent = round(((total - idle) / total) * 100, 2) if total > 0 else None
    return {
        "cpu_busy_percent": busy_percent,
        "cpu_jiffies": {
            "user": values[0] if len(values) > 0 else 0,
            "nice": values[1] if len(values) > 1 else 0,
            "system": values[2] if len(values) > 2 else 0,
            "idle": values[3] if len(values) > 3 else 0,
            "iowait": values[4] if len(values) > 4 else 0,
            "irq": values[5] if len(values) > 5 else 0,
            "softirq": values[6] if len(values) > 6 else 0,
        }
    }


def _disk() -> list[dict[str, Any]]:
    proc = _run(["df", "-P", "-k"], timeout=10)
    if proc.returncode != 0:
        return []
    entries: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        filesystem, total, used, available, use_percent, mountpoint = parts[:6]
        if not total.isdigit() or not used.isdigit() or not available.isdigit():
            continue
        entries.append(
            {
                "filesystem": filesystem,
                "mountpoint": mountpoint,
                "total_kb": int(total),
                "used_kb": int(used),
                "available_kb": int(available),
                "use_percent": int(use_percent.rstrip("%")) if use_percent.rstrip("%").isdigit() else None,
            }
        )
    return entries


def _disk_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        return {}
    usable = [entry for entry in entries if isinstance(entry.get("use_percent"), int)]
    max_entry = max(usable, key=lambda item: item["use_percent"], default=None)
    volume1 = next((entry for entry in usable if entry.get("mountpoint") == "/volume1"), None)
    root = next((entry for entry in usable if entry.get("mountpoint") == "/"), None)
    summary: dict[str, Any] = {
        "disk_filesystem_count": len(entries),
    }
    if max_entry:
        summary["disk_max_use_percent"] = max_entry["use_percent"]
        summary["disk_max_mountpoint"] = max_entry.get("mountpoint")
    if volume1:
        summary["disk_volume1_use_percent"] = volume1["use_percent"]
        summary["disk_volume1_available_kb"] = volume1.get("available_kb")
        summary["disk_volume1_total_kb"] = volume1.get("total_kb")
    if root:
        summary["disk_root_use_percent"] = root["use_percent"]
    return summary


def _sys_class_net_value(interface: str, name: str) -> str | int | None:
    text = _read_text(Path("/sys/class/net") / interface / name)
    if text is None:
        return None
    value = text.strip()
    if not value:
        return None
    return int(value) if value.lstrip("-").isdigit() else value


def _network() -> list[dict[str, Any]]:
    netdev = _read_text(Path("/proc/net/dev")) or ""
    entries: list[dict[str, Any]] = []
    for line in netdev.splitlines()[2:]:
        if ":" not in line:
            continue
        name, values_text = line.split(":", 1)
        interface = name.strip()
        if not interface or interface == "lo":
            continue
        values = values_text.split()
        if len(values) < 16 or not all(item.isdigit() for item in values[:16]):
            continue
        entry: dict[str, Any] = {
            "interface": interface,
            "rx_bytes": int(values[0]),
            "rx_packets": int(values[1]),
            "rx_errors": int(values[2]),
            "rx_drops": int(values[3]),
            "tx_bytes": int(values[8]),
            "tx_packets": int(values[9]),
            "tx_errors": int(values[10]),
            "tx_drops": int(values[11]),
        }
        for field in ["operstate", "carrier", "speed", "mtu"]:
            value = _sys_class_net_value(interface, field)
            if value is not None:
                entry[field] = value
        entries.append(entry)
    return entries


def _network_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        return {}
    up_count = 0
    for entry in entries:
        if entry.get("operstate") == "up" or entry.get("carrier") == 1:
            up_count += 1
    return {
        "network_interface_count": len(entries),
        "network_up_interface_count": up_count,
        "network_total_rx_bytes": sum(int(entry.get("rx_bytes") or 0) for entry in entries),
        "network_total_tx_bytes": sum(int(entry.get("tx_bytes") or 0) for entry in entries),
        "network_total_rx_packets": sum(int(entry.get("rx_packets") or 0) for entry in entries),
        "network_total_tx_packets": sum(int(entry.get("tx_packets") or 0) for entry in entries),
        "network_total_rx_errors": sum(int(entry.get("rx_errors") or 0) for entry in entries),
        "network_total_tx_errors": sum(int(entry.get("tx_errors") or 0) for entry in entries),
        "network_total_rx_drops": sum(int(entry.get("rx_drops") or 0) for entry in entries),
        "network_total_tx_drops": sum(int(entry.get("tx_drops") or 0) for entry in entries),
    }


def _process_count() -> int | None:
    proc = _run(["ps", "-e"], timeout=10)
    if proc.returncode == 0:
        return max(0, len(proc.stdout.splitlines()) - 1)
    proc_dirs = [path for path in Path("/proc").iterdir() if path.name.isdigit()]
    return len(proc_dirs)


def _command_exists(command: str) -> bool:
    return _run(["sh", "-c", f"command -v {command} >/dev/null 2>&1"], timeout=5).returncode == 0


def _pgrep_status(names: list[str]) -> dict[str, Any]:
    matches: list[str] = []
    for name in names:
        proc = _run(["pgrep", "-x", name], timeout=5) if _command_exists("pgrep") else _run(["sh", "-c", f"ps -e | grep -w {name} | grep -v grep"], timeout=5)
        if proc.returncode == 0 and proc.stdout.strip():
            matches.append(name)
    return {"running": bool(matches), "matches": sorted(set(matches))}


def _systemctl_status(name: str) -> str | None:
    if not _command_exists("systemctl"):
        return None
    proc = _run(["systemctl", "is-active", name], timeout=5)
    if proc.returncode in {0, 3} and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def _synopkg_status(package: str) -> str | None:
    if not _command_exists("synopkg"):
        return None
    proc = _run(["synopkg", "status", package], timeout=10)
    text = (proc.stdout + "\n" + proc.stderr).strip()
    if not text:
        return None
    if "Status: Running" in text or "status=running" in text.lower() or "is running" in text.lower():
        return "running"
    if "Status: Stopped" in text or "status=stopped" in text.lower() or "is stopped" in text.lower():
        return "stopped"
    if proc.returncode == 0:
        return "available"
    return None


def _services() -> dict[str, Any]:
    services: dict[str, Any] = {}
    for service, candidates in SERVICE_CANDIDATES.items():
        systemctl = next((status for name in candidates if (status := _systemctl_status(name))), None)
        process = _pgrep_status(candidates)
        services[service] = {
            "running": process["running"] or systemctl == "active",
            "process_matches": process["matches"],
            "systemctl": systemctl,
        }
    packages: dict[str, str] = {}
    for package in PACKAGE_CANDIDATES:
        status = _synopkg_status(package)
        if status:
            packages[package] = status
    if packages:
        services["synology_packages"] = packages
    return services


def _service_summary(services: dict[str, Any]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for name, payload in services.items():
        if not isinstance(payload, dict) or name == "synology_packages":
            continue
        summary[f"service_{name}_up"] = 1 if payload.get("running") else 0
    return summary


def collect_host_health(nas_host: str) -> dict[str, Any]:
    observed_at = int(time.time())
    uptime = _uptime()
    memory = _memory()
    cpu = _cpu()
    disk = _disk()
    network = _network()
    services = _services()
    memory_total = memory.get("memory_total_kb") or 0
    memory_available = memory.get("memory_available_kb") or 0
    swap_total = memory.get("swap_total_kb") or 0
    swap_free = memory.get("swap_free_kb") or 0
    memory_used_percent = round(((memory_total - memory_available) / memory_total) * 100, 2) if memory_total else None
    swap_used_percent = round(((swap_total - swap_free) / swap_total) * 100, 2) if swap_total else None
    scalar_fields: dict[str, Any] = {
        "uptime_seconds": uptime.get("uptime_seconds"),
        "load1": uptime.get("load1"),
        "load5": uptime.get("load5"),
        "load15": uptime.get("load15"),
        "memory_used_percent": memory_used_percent,
        "swap_used_percent": swap_used_percent,
        "cpu_busy_percent": cpu.get("cpu_busy_percent"),
        "process_count": _process_count(),
    }
    scalar_fields.update(_disk_summary(disk))
    scalar_fields.update(_network_summary(network))
    scalar_fields.update(_service_summary(services))
    event = {
        "event_id": f"host-health-{nas_host}-{observed_at}",
        "action": "host_health_snapshot",
        "nas_host": nas_host,
        "source_channel": "host_health",
        "source_app": "nas_host_health",
        "source_surface": "ssh_transient_payload",
        "confidence": 0.95,
        "observed_at": observed_at,
        "uptime": uptime,
        "memory": memory,
        "cpu": cpu,
        "disk": disk,
        "network": network,
        "services": services,
        "policy_notes": [
            "Host health adapter reads operating-system metadata only.",
            "No file contents, credentials, cookies, or session tokens are collected.",
        ],
    }
    event.update({key: value for key, value in scalar_fields.items() if value is not None})
    return {"found": True, "stage": "host_health_snapshot", "events": [event]}


def _run_remote(args: argparse.Namespace) -> dict[str, Any]:
    script_source = Path(__file__).read_text(encoding="utf-8")
    remote = f"{args.user}@{args.host}" if args.user else args.host
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={min(args.timeout_sec, 30)}",
    ]
    identity_file = os.environ.get("WARROOM_SSH_IDENTITY_FILE", "").strip()
    if identity_file:
        command.extend(["-o", f"IdentityFile={identity_file}", "-o", "IdentitiesOnly=yes"])
    command.extend([remote, "sudo", "-n", "python3", "-", "--mode", "local", "--nas-host", args.nas_host])
    proc = subprocess.run(command, input=script_source, text=True, capture_output=True, timeout=args.timeout_sec, check=False)
    if proc.returncode != 0:
        return {
            "found": False,
            "stage": "remote_host_health_adapter_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip()[-1000:],
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "found": False,
            "stage": "remote_host_health_adapter_invalid_json",
            "error": str(exc),
            "stdout_sample": proc.stdout[:1000],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--nas-host", default="demo-nas")
    parser.add_argument("--host", default="nas.example.local", help="SSH host alias or address for --mode remote")
    parser.add_argument("--user", default="", help="SSH user for --mode remote; empty uses ssh config or current user")
    parser.add_argument("--timeout-sec", type=int, default=30)
    args = parser.parse_args()

    if args.timeout_sec < 1:
        result = {"found": False, "stage": "invalid_timeout", "events": []}
    elif args.mode == "remote":
        result = _run_remote(args)
    else:
        result = collect_host_health(args.nas_host)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
